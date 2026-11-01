"""history: 个股日线 / 月线（前复权）。"""
from __future__ import annotations

import pandas as pd
from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

COLUMNS = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "涨跌幅"]


def fetch_hist(symbol: str, period: str = "daily", start_date: str = "20100101",
               end_date: str = "20500101") -> pd.DataFrame:
    import akshare as ak
    df = with_retry(ak.stock_zh_a_hist, symbol=symbol, period=period,
                    start_date=start_date, end_date=end_date, adjust="qfq")
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=COLUMNS + ["symbol"])
    df = df.rename(columns={"日期": "date", "开盘": "open", "收盘": "close",
                            "最高": "high", "最低": "low", "成交量": "volume",
                            "成交额": "amount", "涨跌幅": "pct_change"})
    df["symbol"] = symbol
    return df


def save(symbol: str, period: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "hist" / period
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{symbol}.parquet", index=False)
    log.info("hist[%s/%s] %s %d 行", symbol, period, symbol, len(df))
