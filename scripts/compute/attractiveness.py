"""attractiveness: 模块4b 权益性价比气泡图。

X = 成本友好分位(PE便宜分位, 越高越便宜)；Y = 账面分位(PB便宜分位)；
大小 = 市值(流动性/规模)；颜色可叠加股息率。
"""
from __future__ import annotations

import datetime as dt
import pandas as pd
from io_utils import log, write_json, RAW_DIR

from .indicators import cheap_percentile


def collect(settings, name_map: dict, mcap_map: dict) -> dict:
    val_dir = RAW_DIR / "valuation"
    points = []
    if val_dir.exists():
        for f in sorted(val_dir.glob("*.parquet")):
            sym = f.stem
            df = pd.read_parquet(f)
            if len(df) < 20:
                continue
            cur = df.dropna(subset=["pe_ttm", "pb"]).iloc[-1] if df.dropna(subset=["pe_ttm", "pb"]).shape[0] else None
            if cur is None:
                continue
            pe_cheap = cheap_percentile(df["pe_ttm"].dropna(), cur["pe_ttm"])
            pb_cheap = cheap_percentile(df["pb"].dropna(), cur["pb"])
            dy = cur.get("div_yield")
            try:
                dy = float(dy) if dy is not None and not pd.isna(dy) else 0.0
            except Exception:
                dy = 0.0
            points.append({
                "symbol": sym,
                "name": name_map.get(sym, sym),
                "cost_friendly_pct": round(pe_cheap, 3),
                "book_pct": round(pb_cheap, 3),
                "div_yield": round(dy / 100.0 if dy > 1 else dy, 4),
                "mcap": round(float(mcap_map.get(sym) or 0), 2),
            })
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": settings["valuation"],
        "count": len(points),
        "points": points,
    }
    write_json(out, "attractiveness.json")
    log.info("attractiveness: %d 点", len(points))
    return out
