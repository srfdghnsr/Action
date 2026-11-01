"""universe: 全市场 A 股实时快照（东方财富）。"""
from __future__ import annotations

import pandas as pd
from io_utils import log, write_parquet, schema_check, RAW_DIR
from ._http import with_retry

REQUIRED = ["代码", "名称", "最新价", "总市值", "流通市值", "市盈率-动态", "市净率"]


def fetch_universe() -> pd.DataFrame:
    import akshare as ak
    df = with_retry(ak.stock_zh_a_spot_em)
    df = schema_check(df, REQUIRED, "stock_zh_a_spot_em")
    # 统一列名
    df = df.rename(columns={"代码": "symbol", "名称": "name", "最新价": "price",
                           "总市值": "mcap", "流通市值": "circ_mcap",
                           "市盈率-动态": "pe", "市净率": "pb", "涨跌幅": "pct_change"})
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    return df


def save(df: pd.DataFrame) -> None:
    write_parquet(df, "universe.parquet")
    log.info("universe 保存 %d 行 -> %s", len(df), RAW_DIR / "universe.parquet")
