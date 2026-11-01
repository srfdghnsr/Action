"""valuation: 估值时间序列（市盈率TTM / 市净率 / 股息率TTM），来自百度股市通。

每个标的合并为单文件：symbol, date, pe_ttm, pb, div_yield。仅对入选+watchlist 跑。
"""
from __future__ import annotations

import pandas as pd
from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

INDICATORS = {
    "pe_ttm": "市盈率(TTM)",
    "pb": "市净率",
    "div_yield": "股息率(TTM)",
}


def fetch_one(symbol: str, indicator_key: str, period: str = "近十年") -> pd.DataFrame:
    import akshare as ak
    cn = INDICATORS[indicator_key]
    df = with_retry(ak.stock_zh_valuation_baidu, symbol=symbol, indicator=cn, period=period)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date", indicator_key])
    df = df.copy()
    col = [c for c in df.columns if c != "日期"][0] if len(df.columns) >= 2 else None
    df = df.rename(columns={cn: indicator_key, "日期": "date"})
    if indicator_key not in df.columns and col:
        df = df.rename(columns={col: indicator_key})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[["date", indicator_key]].dropna()


def fetch_all(symbol: str, period: str = "近十年") -> pd.DataFrame:
    out = None
    for key in INDICATORS:
        d = fetch_one(symbol, key, period)
        if out is None:
            out = d
        else:
            out = out.merge(d, on="date", how="outer")
    if out is None:
        return pd.DataFrame(columns=["date", "pe_ttm", "pb", "div_yield"])
    out = out.sort_values("date").ffill().bfill()
    out["symbol"] = symbol
    return out[["symbol", "date", "pe_ttm", "pb", "div_yield"]]


def save(symbol: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "valuation"
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{symbol}.parquet", index=False)
    log.info("valuation %s %d 行", symbol, len(df))
