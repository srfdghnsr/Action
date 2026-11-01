"""payback: 模块2c 分红回本年限。

回本年限 = 1 / 股息率（股息率以小数计）；股息率缺失时用 每股分红/现价 估算。
标注 20 年回本线，输出排序列表与中位数（诚实统计）。
"""
from __future__ import annotations

import datetime as dt
import pandas as pd
from io_utils import log, read_parquet, write_json, RAW_DIR, safe_div


def estimate(symbol, name, div_df, price) -> dict | None:
    if div_df is None or len(div_df) == 0:
        return None
    d = div_df.copy()
    if "year" in d.columns:
        d = d.dropna(subset=["year"]).sort_values("year")
    latest = d.iloc[-1]
    dy = latest.get("dividend_yield")
    dps = latest.get("div_per_share")
    try:
        dy = float(dy) if dy is not None and not pd.isna(dy) else 0.0
    except Exception:
        dy = 0.0
    # 股息率(%) 转小数
    dy_frac = dy / 100.0 if dy > 1 else dy
    if dy_frac <= 0:
        # 用 每股分红 / 现价 兜底
        try:
            if dps and price:
                dy_frac = float(dps) / float(price)
        except Exception:
            dy_frac = 0.0
    payback = safe_div(1.0, dy_frac) if dy_frac > 0 else None
    return {
        "symbol": symbol,
        "name": name,
        "dividend_yield": round(dy, 3),
        "div_per_share": round(float(dps), 4) if dps else None,
        "payback_years": round(payback, 1) if payback else None,
    }


def collect(settings, name_map: dict, price_map: dict) -> dict:
    div_dir = RAW_DIR / "dividend"
    items = []
    if div_dir.exists():
        for f in sorted(div_dir.glob("*.parquet")):
            sym = f.stem
            div_df = pd.read_parquet(f)
            price = price_map.get(sym)
            r = estimate(sym, name_map.get(sym, sym), div_df, price)
            if r:
                items.append(r)
    items = [x for x in items if x["payback_years"] is not None]
    items.sort(key=lambda x: x["payback_years"])
    valid = [x["payback_years"] for x in items]
    median = float(pd.Series(valid).median()) if valid else None
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": {"payback_line_years": 20},
        "median_payback_years": round(median, 1) if median else None,
        "count": len(items),
        "items": items,
    }
    write_json(out, "payback.json")
    log.info("payback: %d 条，中位 %.1f 年", len(items), median or 0)
    return out
