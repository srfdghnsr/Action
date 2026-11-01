"""cyq_analysis: 模块3 筹码分布分析。

数据源：stock_cyq_em（获利比例 / 平均成本 / 90集中度，直接给出）+ 
stock_cyq_cottle（各价位成本分布，用于价格级直方图与主峰迁移）。
输出：获利比例区间判读、集中度判读、主峰位置、主峰迁移形态、止损估算。
注：价格轴由 cottle 的成本分布占比重建，止损位为模型估算（密集区下沿近似）。
"""
from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
from io_utils import log, write_json, RAW_DIR, safe_div


def judge_band(profit_ratio: float) -> str:
    if profit_ratio < 5:
        return "底部必要条件(需叠加缩量)"
    if profit_ratio < 30:
        return "洗盘末端"
    if profit_ratio <= 70:
        return "中性震荡"
    if profit_ratio <= 90:
        return "健康上涨(有获利盘但不多)"
    return "减仓信号(全员获利, 谨防踩踏)"


def judge_density(conc: float) -> str:
    if conc < 10:
        return "高度集中(单峰密集)"
    if conc < 15:
        return "相对集中"
    if conc < 25:
        return "正常发散"
    return "高度发散"


def _peak_label(peak_pos, cottle_df):
    if cottle_df is None or "收盘价" not in cottle_df.columns or len(cottle_df) < 12:
        return "数据不足"
    close = cottle_df["收盘价"].astype(float).reset_index(drop=True)
    price_up = close.iloc[-1] > close.iloc[max(0, len(close) - 12)]
    # 用最近一行的成本分布列判断双峰
    cols = [c for c in cottle_df.columns if c.startswith("成本分布_")]
    if not cols:
        return "数据不足"
    w = cottle_df[cols].iloc[-1].astype(float).values
    w = w / (w.sum() + 1e-9)
    # 局部极大值计数
    maxima = 0
    for i in range(1, len(w) - 1):
        if w[i] > w[i - 1] and w[i] >= w[i + 1] and w[i] > 0.03:
            maxima += 1
    if maxima >= 2:
        return "双峰(中间真空, 亦是阻力)"
    if price_up and peak_pos < 0.45:
        return "下峰锁定(原始筹码没走, 行情未尽)"
    if (not price_up) and peak_pos > 0.55:
        return "上峰不移(套牢盘压制, 反弹有限)"
    if peak_pos > 0.6:
        return "主力派发(筹码换手给散户, 接近尾声)"
    return "筹码交换中"


def analyze(symbol, name, cyq_df, cottle_df) -> dict | None:
    if cyq_df is None or len(cyq_df) == 0:
        return None
    last = cyq_df.iloc[-1]
    try:
        pr = float(last.get("获利比例"))
        conc = float(last.get("90集中度"))
        avg_cost = float(last.get("平均成本"))
    except Exception:
        return None
    rec = {
        "symbol": symbol,
        "name": name,
        "profit_ratio": round(pr, 2),
        "concentration_90": round(conc, 2),
        "avg_cost": round(avg_cost, 2),
        "band": judge_band(pr),
        "density": judge_density(conc),
    }
    peak_pos = None
    if cottle_df is not None and len(cottle_df):
        cols = [c for c in cottle_df.columns if c.startswith("成本分布_")]
        if cols:
            w = cottle_df[cols].iloc[-1].astype(float).values
            w = w / (w.sum() + 1e-9)
            peak_pos = int(np.argmax(w)) / max(1, len(w) - 1)
    rec["peak_position"] = round(peak_pos, 3) if peak_pos is not None else None
    rec["peak_migration"] = _peak_label(peak_pos, cottle_df) if peak_pos is not None else "数据不足"
    rec["stop_estimate"] = round(avg_cost * (1 - 0.5 * conc / 100), 2) if avg_cost else None
    return rec


def collect(settings, name_map: dict) -> dict:
    cyq_dir = RAW_DIR / "cyq"
    cot_dir = RAW_DIR / "cyq_cottle"
    items = []
    if cyq_dir.exists():
        for f in sorted(cyq_dir.glob("*.parquet")):
            sym = f.stem
            cyq_df = pd.read_parquet(f)
            cot_df = pd.read_parquet(cot_dir / f.name) if (cot_dir / f.name).exists() else None
            r = analyze(sym, name_map.get(sym, sym), cyq_df, cot_df)
            if r:
                items.append(r)
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": settings["cyq"],
        "count": len(items),
        "items": items,
    }
    write_json(out, "cyq.json")
    log.info("cyq: %d 条", len(items))
    return out
