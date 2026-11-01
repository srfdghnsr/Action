"""fundamental: 分红历史 + 财务摘要（净利润 / 经营现金流）。

分红用 stock_history_dividend（含历史股息率、分红率、派息额），财务用
stock_financial_abstract 做尽力解析。缺失字段在 compute 层降级处理。
"""
from __future__ import annotations

import re
import pandas as pd
from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

DIV_COLUMNS = ["symbol", "year", "ex_date", "dividend_text", "div_per_share",
               "dividend_yield", "payout_ratio"]
FIN_COLUMNS = ["symbol", "date", "net_profit", "operate_cashflow"]


def _parse_payout(text: str):
    """从分红方案说明解析每 10 股派息额（元）。"""
    if not text:
        return None
    m = re.search(r"派([\d.]+)元", str(text))
    if m:
        return float(m.group(1)) / 10.0
    return None


def fetch_dividend(symbol: str) -> pd.DataFrame:
    import akshare as ak
    try:
        df = with_retry(ak.stock_history_dividend, symbol=symbol, indicator="分红")
    except Exception as e:  # noqa: BLE001
        log.warning("dividend 失败 %s: %s", symbol, e)
        return pd.DataFrame(columns=DIV_COLUMNS + ["symbol"]).assign(symbol=symbol)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=DIV_COLUMNS).assign(symbol=symbol)
    df = df.copy()
    df["symbol"] = symbol
    if "分红方案说明" in df.columns:
        df["dividend_text"] = df["分红方案说明"]
        df["div_per_share"] = df["分红方案说明"].apply(_parse_payout)
    else:
        df["dividend_text"] = None
        df["div_per_share"] = None
    for c in ["年度", "除权除息日", "股息率(%)", "分红率(%)"]:
        if c not in df.columns:
            df[c] = None
    df = df.rename(columns={"年度": "year", "除权除息日": "ex_date",
                            "股息率(%)": "dividend_yield", "分红率(%)": "payout_ratio"})
    keep = [c for c in DIV_COLUMNS if c in df.columns]
    return df[keep]


def fetch_financial(symbol: str) -> pd.DataFrame:
    import akshare as ak
    try:
        df = with_retry(ak.stock_financial_abstract, symbol=symbol)
    except Exception as e:  # noqa: BLE001
        log.warning("financial 失败 %s: %s", symbol, e)
        return pd.DataFrame(columns=FIN_COLUMNS).assign(symbol=symbol)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=FIN_COLUMNS).assign(symbol=symbol)
    df = df.copy()
    df["symbol"] = symbol
    # 尽力解析净利润 / 经营现金流（列名随版本变化）
    net = [c for c in df.columns if "净利润" in c or "归母" in c]
    cf = [c for c in df.columns if "经营现金" in c or "现金流量净额" in c]
    df["net_profit"] = df[net[0]] if net else None
    df["operate_cashflow"] = df[cf[0]] if cf else None
    df["date"] = df.iloc[:, 0] if len(df.columns) else None
    keep = [c for c in FIN_COLUMNS if c in df.columns]
    return df[keep]


def save_dividend(symbol: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "dividend"
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{symbol}.parquet", index=False)


def save_financial(symbol: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "financial"
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{symbol}.parquet", index=False)
