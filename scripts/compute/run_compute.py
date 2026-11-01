"""run_compute: 串联所有 compute 模块，生成 data/processed/*.json。

负责从 raw 构建共享映射（名称/市值/价格/上市日），再依次调用各模块 collect()。
"""
from __future__ import annotations

import pandas as pd
from io_utils import log, read_parquet, RAW_DIR

from . import selectors, dividend_quality, valuation_map, payback, cyq_analysis, seasonality, attractiveness, backtest


def _build_maps():
    name_map, mcap_map, price_map, list_date_map = {}, {}, {}, {}
    try:
        uni = read_parquet("universe.parquet")
        for _, r in uni.iterrows():
            s = str(r.get("symbol"))
            name_map[s] = r.get("name")
            mcap_map[s] = r.get("mcap")
            price_map[s] = r.get("price")
    except Exception as e:  # noqa: BLE001
        log.warning("run_compute: 读 universe 失败 %s", e)
    try:
        info = read_parquet("stock_info.parquet")
        for _, r in info.iterrows():
            s = str(r.get("symbol"))
            list_date_map[s] = r.get("list_date")
            if r.get("total_mcap") is not None:
                mcap_map.setdefault(s, r.get("total_mcap"))
    except Exception:
        pass
    return name_map, mcap_map, price_map, list_date_map


def run_compute(settings: dict) -> dict:
    name_map, mcap_map, price_map, list_date_map = _build_maps()
    results = {}
    results["selectors"] = selectors.collect(settings)
    results["dividend_quality"] = dividend_quality.collect(settings, name_map)
    results["valuation_map"] = valuation_map.collect(settings, name_map, mcap_map)
    results["payback"] = payback.collect(settings, name_map, price_map)
    results["cyq"] = cyq_analysis.collect(settings, name_map)
    results["seasonality"] = seasonality.collect(settings)
    results["attractiveness"] = attractiveness.collect(settings, name_map, mcap_map)

    # 回测：基准（取第一个基准指数月度序列，若存在）
    bench_monthly = None
    bench_dir = RAW_DIR / "benchmark"
    if bench_dir.exists():
        for f in sorted(bench_dir.glob("*.parquet")):
            df = pd.read_parquet(f)
            if "close" in df.columns and "date" in df.columns:
                df = df.copy()
                df["date"] = pd.to_datetime(df["date"])
                s = df.set_index("date")["close"].astype(float).sort_index()
                bench_monthly = s
                break
    daily_dir = RAW_DIR / "hist" / "daily"
    monthly_dir = RAW_DIR / "hist" / "monthly"
    results["backtest"] = backtest.run_backtest(
        settings, daily_dir, monthly_dir, name_map, mcap_map, price_map,
        list_date_map, bench_monthly,
    )
    return results
