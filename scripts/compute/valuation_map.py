"""valuation_map: 模块2b 估值分位地图（PE便宜分位 × 股息率 气泡图）。

对每个有估值序列的标的：当前 PE 在自身历史中的「便宜分位」(1-分位秩)，
当前股息率，市值（气泡大小）。输出散点数组供前端气泡图。
"""
from __future__ import annotations

import datetime as dt
import pandas as pd
from io_utils import log, read_parquet, write_json, RAW_DIR, safe_div

from .indicators import cheap_percentile


def point(symbol, name, val_df, mcap) -> dict | None:
    if val_df is None or len(val_df) < 20:
        return None
    cur = val_df.dropna(subset=["pe_ttm"]).iloc[-1]
    pe_ts = val_df["pe_ttm"].dropna()
    if len(pe_ts) < 20 or pd.isna(cur["pe_ttm"]):
        return None
    pe_cheap = cheap_percentile(pe_ts, cur["pe_ttm"])
    dy = cur.get("div_yield")
    try:
        dy = float(dy) if dy is not None and not pd.isna(dy) else 0.0
    except Exception:
        dy = 0.0
    return {
        "symbol": symbol,
        "name": name,
        "pe": round(float(cur["pe_ttm"]), 2),
        "pe_cheap_pct": round(pe_cheap, 3),
        "div_yield": round(dy, 3),
        "mcap": round(float(mcap), 2) if mcap else None,
    }


def collect(settings, name_map: dict, mcap_map: dict) -> dict:
    val_dir = RAW_DIR / "valuation"
    points = []
    if val_dir.exists():
        for f in sorted(val_dir.glob("*.parquet")):
            sym = f.stem
            val_df = pd.read_parquet(f)
            name = name_map.get(sym, sym)
            mcap = mcap_map.get(sym)
            p = point(sym, name, val_df, mcap)
            if p:
                points.append(p)
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": settings["valuation"],
        "count": len(points),
        "points": points,
    }
    write_json(out, "valuation_map.json")
    log.info("valuation_map: %d 点", len(points))
    return out
