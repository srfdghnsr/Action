"""cyq: 筹码分布。stock_cyq_em 给出获利比例/平均成本/90-集中度；
stock_cyq_cottle 给出各价位成本分布（用于价格级直方图与主峰迁移）。
仅对候选子集 + watchlist（≤ max_cyq）调用，最重。"""
from __future__ import annotations

import pandas as pd
from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

CYQ_COLUMNS = ["日期", "获利比例", "平均成本", "90成本-低", "90成本-高", "90集中度",
               "70成本-低", "70成本-高", "70集中度"]
COTTLE_VAL_PREFIX = "成本分布_"


def fetch_cyq(symbol: str) -> pd.DataFrame:
    import akshare as ak
    df = with_retry(ak.stock_cyq_em, symbol=symbol, adjust="")
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=CYQ_COLUMNS)
    df = df.copy()
    df["symbol"] = symbol
    return df


def fetch_cyq_cottle(symbol: str, start_date: str = "20200101",
                     end_date: str = "20500101") -> pd.DataFrame:
    import akshare as ak
    df = with_retry(ak.stock_cyq_cottle, symbol=symbol,
                    start_date=start_date, end_date=end_date)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["日期", "收盘价", "获利比例", "平均成本"])
    df = df.copy()
    df["symbol"] = symbol
    return df


def save_cyq(symbol: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "cyq"
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{symbol}.parquet", index=False)


def save_cottle(symbol: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "cyq_cottle"
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{symbol}.parquet", index=False)
    log.info("cyq_cottle %s %d 行", symbol, len(df))
