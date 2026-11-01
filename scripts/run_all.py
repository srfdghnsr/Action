"""run_all: 总编排。

用法：
  python scripts/run_all.py --seed-mock            # 生成离线示例数据并构建（本地预览/单测）
  python scripts/run_all.py                         # 抓取→计算→构建（GitHub Actions 主路径）
  python scripts/run_all.py --use-cache --banner "..."  # 复用已算数据重建（兜底）
  python scripts/run_all.py --push-cache           # 构建后把 processed 推到 data-cache 分支

设计：实时抓取失败不影响部署——主步骤失败由调用方（Actions）捕捉后改走 --use-cache。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

# 把 scripts/ 加入路径
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from io_utils import (  # noqa: E402
    log, load_settings, load_json_config, write_json, RAW_DIR, PROCESSED_DIR,
)
from compute.run_compute import run_compute  # noqa: E402
from build_site import build  # noqa: E402


def write_meta(generated_at, status, ok, banner, is_mock):
    meta = {
        "generated_at": generated_at,
        "status": status,
        "ok": ok,
        "banner": banner or "",
        "version": load_settings().get("version", "1.0.0"),
        "is_mock": is_mock,
    }
    write_json(meta, "meta.json")
    return meta


def is_trade_day() -> bool:
    """轻量交易日判断：周末跳过；若可访问 sina 交易日历则进一步校验。"""
    now = dt.datetime.now()
    if now.weekday() >= 5:
        return False
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        today = now.strftime("%Y-%m-%d")
        return today in list(cal.astype(str))
    except Exception:
        return True  # 无法校验时默认视为交易日


def fetch_universe_candidates(settings):
    from fetch import universe as U
    from fetch import info as I
    from fetch import history as H
    from fetch import valuation as V
    from fetch import fundamental as F
    from fetch import cyq as C
    from fetch import board as B
    from io_utils import safe_div

    cfg = settings["selector"]
    uni = U.fetch_universe()
    U.save(uni)
    log.info("universe %d 行", len(uni))

    uni["mcap"] = uni["mcap"].astype(float)
    cand = uni[(uni["mcap"] > cfg["mcap_min"]) & (uni["mcap"] < cfg["mcap_max"])].copy()
    cand = cand[~cand["name"].astype(str).str.contains("ST|退", na=False)]
    max_scan = settings.get("pipeline", {}).get("max_scan", 600)
    cand = cand.sort_values("mcap", ascending=False).head(max_scan)
    log.info("候选 %d 只（市值区间 + 非ST，上限 %d）", len(cand), max_scan)

    watch = load_json_config("watchlist.json").get("watchlist", [])
    watch_set = set(watch)
    cyq_cap = settings["cyq"]["max_symbols"]
    # 优先 watchlist + 候选前段进入 cyq 预算
    cyq_symbols = list(dict.fromkeys(list(watch_set) + list(cand["symbol"].astype(str))))

    info_records = []
    for _, r in cand.iterrows():
        sym = str(r["symbol"])
        try:
            inf = I.fetch_info(sym)
            info_records.append(inf)
            d = H.fetch_hist(sym, "daily", "20100101")
            H.save(sym, "daily", d)
            m = H.fetch_hist(sym, "monthly", "20100101")
            H.save(sym, "monthly", m)
            V.save(sym, V.fetch_all(sym))
            F.save_dividend(sym, F.fetch_dividend(sym))
            F.save_financial(sym, F.fetch_financial(sym))
        except Exception as e:  # noqa: BLE001
            log.warning("候选 %s 抓取失败: %s", sym, e)
    I.save(info_records)

    # 筹码：仅预算内
    for i, sym in enumerate(cyq_symbols[:cyq_cap]):
        try:
            C.save_cyq(sym, C.fetch_cyq(sym))
            C.save_cottle(sym, C.fetch_cyq_cottle(sym))
        except Exception as e:  # noqa: BLE401
            log.warning("cyq %s 失败: %s", sym, e)

    # 板块
    try:
        bl = B.fetch_board_list()
        B.save_board_list(bl)
        for _, br in bl.iterrows():
            bn = br["board_name"]
            try:
                B.save_board_cons(bn, B.fetch_board_cons(bn))
                B.save_board_hist(bn, B.fetch_board_hist(bn))
            except Exception as e:  # noqa: BLE401
                log.warning("板块 %s 失败: %s", bn, e)
    except Exception as e:  # noqa: BLE401
        log.warning("板块列表失败: %s", e)

    # 基准指数
    try:
        import akshare as ak
        import pandas as pd
        from io_utils import RAW_DIR
        bench_dir = RAW_DIR / "benchmark"
        bench_dir.mkdir(parents=True, exist_ok=True)
        for code in settings.get("benchmarks", []):
            df = ak.index_zh_a_hist(symbol=code, period="monthly", start_date="20100101", end_date="20500101")
            df = df.rename(columns={"日期": "date", "收盘": "close"})[["date", "close"]]
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
            df.to_parquet(bench_dir / f"{code}.parquet", index=False)
    except Exception as e:  # noqa: BLE401
        log.warning("基准指数失败: %s", e)


def pd_to_month(s):
    import pandas as pd
    return pd.to_datetime(s).dt.strftime("%Y-%m")


def push_cache():
    """把 data/processed 推送到 data-cache 分支（兜底数据）。"""
    try:
        import shutil
        repo_root = Path(__file__).resolve().parents[1]
        dst = repo_root / "data" / "processed"  # 与 Actions 兜底 checkout 路径一致
        subprocess.run(["git", "config", "user.email", "bot@ashare.local"], check=False)
        subprocess.run(["git", "config", "user.name", "ashare-bot"], check=False)
        subprocess.run(["git", "fetch", "origin", "data-cache", "--quiet"], check=False)
        r = subprocess.run(["git", "rev-parse", "--verify", "data-cache"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode != 0:
            subprocess.run(["git", "checkout", "--orphan", "data-cache"], check=False)
            subprocess.run(["git", "rm", "-rf", "."], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["git", "checkout", "data-cache", "--quiet"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(PROCESSED_DIR, dst)
        subprocess.run(["git", "add", "-A"], check=False)
        subprocess.run(["git", "commit", "-m", "cache: " + dt.datetime.now().isoformat(timespec="seconds")],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push", "origin", "data-cache", "--force"], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                               capture_output=True, text=True).stdout.strip() or "main"
        subprocess.run(["git", "checkout", branch], check=False)
        log.info("push_cache 完成")
    except Exception as e:  # noqa: BLE401
        log.warning("push_cache 失败（不影响部署）: %s", e)


def PROJECT_PROCESSED():
    return Path(__file__).resolve().parents[1] / "data" / "processed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-mock", action="store_true", help="生成离线示例数据")
    ap.add_argument("--use-cache", action="store_true", help="复用已有 processed 重建")
    ap.add_argument("--push-cache", action="store_true", help="构建后推送兜底数据分支")
    ap.add_argument("--banner", default="", help="状态横幅文本")
    ap.add_argument("--force", action="store_true", help="忽略交易日校验强制抓取")
    args = ap.parse_args()

    settings = load_settings()
    now = dt.datetime.now().isoformat(timespec="seconds")
    is_mock = False

    if args.seed_mock:
        from fetch import mock
        log.info("== 生成离线示例数据 ==")
        mock.generate()
        is_mock = True
        status, ok, banner = "畅通", True, "示例数据（非实时）：仅用于演示界面与各模块渲染逻辑"
    elif args.use_cache:
        log.info("== 复用缓存重建 ==")
        status, ok = "数据延迟", False
        banner = args.banner or "数据延迟：本次使用最近一次成功快照"
    else:
        if not (args.force or is_trade_day()):
            log.info("非交易日，复用缓存重建")
            status, ok, banner = "数据延迟", False, "非交易日：复用最近成功快照"
            args.use_cache = True
        else:
            log.info("== 实时抓取 ==")
            try:
                fetch_universe_candidates(settings)
                status, ok = "畅通", True
                banner = ""
            except Exception as e:  # noqa: BLE401
                log.error("实时抓取失败: %s；将由调用方改走 --use-cache", e)
                raise

    # 计算 + 构建（缓存模式也跑，保证页面有内容）
    log.info("== 指标计算 ==")
    run_compute(settings)
    # meta 必须在 build 之前写入，才能被复制进 dist/data/
    write_meta(now, status, ok, banner, is_mock)
    log.info("== 构建站点 ==")
    build(version=settings.get("version", "1.0.0"))
    log.info("完成。dist/ 已生成。")

    if args.push_cache and not is_mock:
        push_cache()


if __name__ == "__main__":
    main()
