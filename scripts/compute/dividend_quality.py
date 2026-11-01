"""dividend_quality: 模块2a 分红质量预警。

标签：最新年度亏损 / 近N年未分红 / 现金流覆盖不足 / 正常。
覆盖所有有分红数据的标的（入选 + watchlist）。
"""
from __future__ import annotations

import datetime as dt
import pandas as pd
from io_utils import log, read_parquet, write_json, RAW_DIR, safe_div

REQUIRED_DIV = ["symbol", "year", "div_per_share", "dividend_yield", "payout_ratio"]


def _latest(div_df: pd.DataFrame):
    if div_df is None or len(div_df) == 0:
        return None
    d = div_df.copy()
    if "year" in d.columns:
        d = d.dropna(subset=["year"]).sort_values("year")
    return d.iloc[-1] if len(d) else None


def analyze(symbol, name, div_df, fin_df, cfg) -> dict:
    p = cfg["dividend_quality"]
    rec = {"symbol": symbol, "name": name, "tags": []}
    latest = _latest(div_df)
    if latest is None:
        rec["dividend_yield"] = None
        rec["payout_ratio"] = None
        rec["consecutive_years"] = 0
        rec["cashflow_cover"] = None
        rec["tags"].append("无分红数据")
        return rec

    rec["dividend_yield"] = float(latest.get("dividend_yield") or 0)
    rec["payout_ratio"] = float(latest.get("payout_ratio") or 0)

    # 连续分红年数（从最新往前数 div_per_share>0）
    if div_df is not None and "div_per_share" in div_df.columns:
        s = div_df.dropna(subset=["div_per_share"]).sort_values("year") if "year" in div_df.columns else div_df
        consec = 0
        for v in reversed(s["div_per_share"].tolist()):
            if v and float(v) > 0:
                consec += 1
            else:
                break
        rec["consecutive_years"] = consec
    else:
        rec["consecutive_years"] = 0

    # 现金流覆盖
    cover = None
    if fin_df is not None and len(fin_df):
        np_ = fin_df.iloc[-1].get("net_profit")
        cf_ = fin_df.iloc[-1].get("operate_cashflow")
        pr_ = rec["payout_ratio"]
        try:
            if cf_ is not None and np_ is not None and np_ != 0:
                div_paid = pr_ * float(np_)
                cover = safe_div(float(cf_), div_paid) if div_paid else None
        except Exception:
            cover = None
    rec["cashflow_cover"] = round(cover, 2) if cover is not None else None

    # 标签
    if fin_df is not None and len(fin_df):
        np_ = fin_df.iloc[-1].get("net_profit")
        if np_ is not None and float(np_) < 0:
            rec["tags"].append("最新年度亏损")
    if rec["consecutive_years"] < p["min_dividend_years"]:
        rec["tags"].append(f"近{rec['consecutive_years']}年未分红")
    if cover is not None and cover < p["cashflow_cover_min"]:
        rec["tags"].append("现金流覆盖不足")
    if not rec["tags"]:
        rec["tags"].append("正常")
    return rec


def collect(settings, name_map: dict) -> dict:
    div_dir = RAW_DIR / "dividend"
    fin_dir = RAW_DIR / "financial"
    items = []
    if not div_dir.exists():
        log.warning("dividend_quality: 无分红数据目录")
    else:
        for f in sorted(div_dir.glob("*.parquet")):
            sym = f.stem
            div_df = pd.read_parquet(f)
            fin_df = pd.read_parquet(fin_dir / f.name) if (fin_dir / f.name).exists() else None
            name = name_map.get(sym, sym)
            items.append(analyze(sym, name, div_df, fin_df, settings))
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": settings["dividend_quality"],
        "count": len(items),
        "items": items,
    }
    write_json(out, "dividend_quality.json")
    log.info("dividend_quality: %d 条", len(items))
    return out
