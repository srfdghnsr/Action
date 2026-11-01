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
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout

    pipe = settings.get("pipeline", {})
    workers = max(1, int(pipe.get("workers", 6)))
    budget = float(pipe.get("time_budget_min", 55)) * 60
    cyq_budget = float(pipe.get("cyq_budget_min", 12)) * 60
    board_budget = float(pipe.get("board_budget_min", 8)) * 60

    cfg = settings["selector"]
    uni = U.fetch_universe()
    U.save(uni)
    log.info("universe %d 行", len(uni))

    uni["mcap"] = uni["mcap"].astype(float)
    cand = uni[(uni["mcap"] > cfg["mcap_min"]) & (uni["mcap"] < cfg["mcap_max"])].copy()
    cand = cand[~cand["name"].astype(str).str.contains("ST|退", na=False)]
    max_scan = int(pipe.get("max_scan", 600))
    cand = cand.sort_values("mcap", ascending=False).head(max_scan)
    total = len(cand)
    log.info("候选 %d 只（市值区间 + 非ST，上限 %d，并发 %d）", total, max_scan, workers)

    watch = load_json_config("watchlist.json").get("watchlist", [])
    watch_set = set(watch)
    cyq_cap = settings["cyq"]["max_symbols"]
    # 优先 watchlist + 候选前段进入 cyq 预算
    cyq_symbols = list(dict.fromkeys(list(watch_set) + list(cand["symbol"].astype(str))))

    def _one(sym):
        inf = I.fetch_info(sym)
        d = H.fetch_daily(sym, "20100101")      # 只请求一次日线，月线本地重采样
        H.save(sym, "daily", d)
        H.save(sym, "monthly", H.to_monthly(d))
        V.save(sym, V.fetch_all(sym))
        F.save_dividend(sym, F.fetch_dividend(sym))
        F.save_financial(sym, F.fetch_financial(sym))
        return inf

    info_records = []
    ex = ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(_one, str(r["symbol"])): str(r["symbol"]) for _, r in cand.iterrows()}
    try:
        for fut in as_completed(futs, timeout=budget):
            try:
                info_records.append(fut.result())
            except Exception as e:  # noqa: BLE001
                log.warning("候选抓取失败: %s", e)
    except FutTimeout:
        log.warning("候选抓取超出 %.0f 分钟预算，已完成 %d / %d", budget / 60, len(info_records), total)
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    I.save(info_records)
    done = len(info_records)
    if total and done == 0:
        raise RuntimeError(f"候选 {total} 只全部抓取失败（接口不可达或列名变更），改走兜底")

    # 筹码：仅预算内
    t_cyq = time.time()
    for i, sym in enumerate(cyq_symbols[:cyq_cap]):
        if time.time() - t_cyq > cyq_budget:
            log.warning("筹码预算用完：已完成 %d / %d", i, min(cyq_cap, len(cyq_symbols)))
            break
        try:
            C.save_cyq(sym, C.fetch_cyq(sym))
            C.save_cottle(sym, C.fetch_cyq_cottle(sym))
        except Exception as e:  # noqa: BLE401
            log.warning("cyq %s 失败: %s", sym, e)

    # 板块
    t_board = time.time()
    try:
        bl = B.fetch_board_list()
        B.save_board_list(bl)
        for _, br in bl.iterrows():
            if time.time() - t_board > board_budget:
                log.warning("板块预算用完，提前收尾")
                break
            bn = br["board_name"]
            bc = br.get("board_code")
            try:
                B.save_board_cons(bn, B.fetch_board_cons(bn, bc))
                B.save_board_hist(bn, B.fetch_board_hist(bn))
            except Exception as e:  # noqa: BLE401
                log.warning("板块 %s 失败: %s", bn, e)
    except Exception as e:  # noqa: BLE401
        log.warning("板块列表失败: %s", e)

    # 基准指数（东财 index_zh_a_hist 境外被断连，改用 sina stock_zh_index_daily）
    try:
        import akshare as ak
        import pandas as pd
        from io_utils import RAW_DIR
        bench_dir = RAW_DIR / "benchmark"
        bench_dir.mkdir(parents=True, exist_ok=True)
        for code in settings.get("benchmarks", []):
            prefix = "sz" if str(code).startswith("399") else "sh"
            raw = ak.stock_zh_index_daily(symbol=f"{prefix}{code}")
            raw["date"] = pd.to_datetime(raw["date"])
            m = raw.set_index("date")["close"].resample("ME").last().dropna()
            df = pd.DataFrame({"date": m.index.strftime("%Y-%m"), "close": m.values.round(2)})
            df.to_parquet(bench_dir / f"{code}.parquet", index=False)
            log.info("基准 %s: %d 个月", code, len(df))
    except Exception as e:  # noqa: BLE401
        log.warning("基准指数失败: %s", e)

    return done, total


def pd_to_month(s):
    import pandas as pd
    return pd.to_datetime(s).dt.strftime("%Y-%m")


def push_cache():
    """把 data/processed 推到 data-cache 分支（兜底快照）。

    纯 plumbing 实现：临时索引 + read-tree --empty + add --work-tree + write-tree
    + commit-tree + push sha:refs/heads/data-cache。全程不切换分支、不动主工作树。
    旧实现用 checkout --orphan + git rm -rf . 再 checkout HEAD，在 Actions 的
    detached HEAD 下会清空源码树，导致后续 upload-pages-artifact 失败。
    """
    try:
        import tempfile
        repo_root = Path(__file__).resolve().parents[1]
        rel = "data/processed"
        if not (repo_root / rel).exists():
            log.warning("push_cache 跳过：%s 不存在", rel)
            return

        probe = subprocess.run(["git", "ls-remote", "--heads", "origin", "data-cache"],
                               cwd=repo_root, capture_output=True, text=True)
        parent_sha = probe.stdout.split()[0] if probe.stdout.strip() else ""

        def g(args, env=None):
            return subprocess.run(["git", *args], cwd=repo_root, env=env,
                                  capture_output=True, text=True)

        msg = "cache: " + dt.datetime.now().isoformat(timespec="seconds")
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env.update({
                "GIT_INDEX_FILE": str(Path(tmp) / "index"),
                "GIT_WORK_TREE": str(repo_root),
                "GIT_AUTHOR_NAME": "ashare-bot", "GIT_COMMITTER_NAME": "ashare-bot",
                "GIT_AUTHOR_EMAIL": "bot@ashare.local", "GIT_COMMITTER_EMAIL": "bot@ashare.local",
            })
            if g(["read-tree", "--empty"], env).returncode != 0:
                raise RuntimeError("read-tree 失败")
            # 索引为空，-f 忽略 .gitignore，只收 data/processed 这一棵子树
            r = g(["add", "-A", "-f", "--", rel], env)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "").strip()[:300])
            tree = g(["write-tree"], env).stdout.strip()
            if not tree:
                raise RuntimeError("write-tree 返回空")
            args = ["commit-tree", tree, "-m", msg]
            if parent_sha:
                args = ["commit-tree", tree, "-p", parent_sha, "-m", msg]
            commit = g(args, env).stdout.strip()
            if not commit:
                raise RuntimeError("commit-tree 返回空")

        push = g(["push", "origin", f"{commit}:refs/heads/data-cache", "--force"])
        if push.returncode != 0:
            raise RuntimeError((push.stderr or "").strip()[:300])
        log.info("push_cache 完成: %s", commit[:8])
    except Exception as e:  # noqa: BLE401
        log.warning("push_cache 失败（不影响部署）: %s", e)


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
        has_cache = PROCESSED_DIR.exists() and any(PROCESSED_DIR.glob("*.json"))
        trade_day = args.force or is_trade_day()
        if not trade_day and not has_cache:
            log.info("非交易日但无缓存快照 → 改为实时抓取，避免产出空板")
            trade_day = True
        if not trade_day:
            log.info("非交易日，复用缓存重建")
            status, ok, banner = "数据延迟", False, "非交易日：复用最近成功快照"
            args.use_cache = True
        else:
            log.info("== 实时抓取 ==")
            try:
                done, total = fetch_universe_candidates(settings)
                status, ok = "畅通", True
                banner = ""
                if total and done < total:
                    status = "部分数据"
                    ok = False
                    banner = f"数据不完整：本轮完成 {done}/{total} 只（时间预算内提前收尾）"
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
