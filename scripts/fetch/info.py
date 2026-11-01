"""info: 个股基础信息（上市时间 / 行业 / 市值）。每标的一次请求，仅对候选子集调用。"""
from __future__ import annotations

import datetime as dt
import pandas as pd
from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

COLUMNS = ["symbol", "list_date", "industry", "total_mcap", "circ_mcap"]


def _parse(row_map: dict, key: str):
    return row_map.get(key)


def fetch_info(symbol: str) -> dict:
    import akshare as ak
    df = with_retry(ak.stock_individual_info_em, symbol=symbol)
    if df is None or len(df) == 0:
        return {"symbol": symbol}
    # 返回两列 item/value
    m = dict(zip(df["item"].astype(str), df["value"]))
    list_date = m.get("上市时间")
    industry = m.get("行业")
    total_mcap = m.get("总市值")
    circ_mcap = m.get("流通市值")
    # 上市时间可能是 Timestamp / str
    if isinstance(list_date, (pd.Timestamp, dt.datetime, dt.date)):
        list_date = pd.Timestamp(list_date).strftime("%Y-%m-%d")
    return {
        "symbol": symbol,
        "list_date": str(list_date) if list_date is not None else None,
        "industry": str(industry) if industry is not None else None,
        "total_mcap": float(total_mcap) if total_mcap is not None else None,
        "circ_mcap": float(circ_mcap) if circ_mcap is not None else None,
    }


def save(records: list[dict]) -> None:
    df = pd.DataFrame(records)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    write_parquet(df[COLUMNS], "stock_info.parquet")
    log.info("stock_info 保存 %d 行", len(df))
