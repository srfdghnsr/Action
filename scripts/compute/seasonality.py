"""seasonality: 模块4a 板块×月份 季节性热力图。

对每个行业板块，统计历史各自然月（1-12）上涨占比（pct_change>0 的月份比例）。
用于发现板块的季节性规律。行业名称经 industry_map 标准化聚合。
"""
from __future__ import annotations

import datetime as dt
import pandas as pd
from io_utils import log, read_parquet, write_json, RAW_DIR, load_json_config


def collect(settings) -> dict:
    hist_dir = RAW_DIR / "board_hist"
    ind_map = load_json_config("industry_map.json").get("map", {})
    boards = {}
    if hist_dir.exists():
        for f in sorted(hist_dir.glob("*.parquet")):
            df = pd.read_parquet(f)
            if "date" not in df.columns or "pct_change" not in df.columns:
                continue
            board = df["board_name"].iloc[0] if "board_name" in df.columns else f.stem
            df = df.copy()
            df["month"] = pd.to_datetime(df["date"] + "-01", errors="coerce").dt.month
            df = df.dropna(subset=["month"])
            up = (df["pct_change"] > 0).groupby(df["month"]).mean()
            row = {int(m): round(float(up.get(m, 0.5)) * 100, 1) for m in range(1, 13)}
            industry = ind_map.get(board, board)
            boards[industry] = row
    # 同行业多板块取平均
    out_boards = {}
    for ind, row in boards.items():
        out_boards.setdefault(ind, []).append(row)
    agg = {}
    for ind, rows in out_boards.items():
        agg[ind] = {m: round(float(sum(r.get(m, 50) for r in rows) / len(rows)), 1) for m in range(1, 13)}
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "months": list(range(1, 13)),
        "boards": agg,
    }
    write_json(out, "seasonality.json")
    log.info("seasonality: %d 板块", len(agg))
    return out
