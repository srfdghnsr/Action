"""history: 个股日线 / 月线（前复权）。

换源说明：东财 `stock_zh_a_hist` 在境外偶发断连，改为
**sina `stock_zh_a_daily`（qfq）为主 → 腾讯 `stock_zh_a_hist_tx` → 东财** 三级降级；
月线由日线重采样，避免重复请求。
"""
from __future__ import annotations

import pandas as pd

from io_utils import log, RAW_DIR
from ._http import with_retry
from .universe import market_prefix

COLUMNS = ["date", "open", "close", "high", "low", "volume", "amount", "pct_change"]

_OHLC_MAP = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
             "最低": "low", "成交量": "volume", "成交额": "amount", "涨跌幅": "pct_change"}


def _norm(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    df = df.rename(columns=_OHLC_MAP)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open", "close", "high", "low", "volume", "amount", "pct_change"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["symbol"] = symbol
    return df[COLUMNS + ["symbol"]].sort_values("date").reset_index(drop=True)


def _fetch_sina(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    import akshare as ak
    code = market_prefix(symbol) + str(symbol).zfill(6)
    return with_retry(ak.stock_zh_a_daily, symbol=code, start_date=start_date,
                      end_date=end_date, adjust="qfq")


def _fetch_tx(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    import akshare as ak
    code = market_prefix(symbol) + str(symbol).zfill(6)
    return with_retry(ak.stock_zh_a_hist_tx, symbol=code, start_date=start_date,
                      end_date=end_date, adjust="qfq")


def _fetch_em(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    import akshare as ak
    return with_retry(ak.stock_zh_a_hist, symbol=symbol, period="daily",
                      start_date=start_date, end_date=end_date, adjust="qfq")


def fetch_daily(symbol: str, start_date: str = "20100101",
                end_date: str = "20500101") -> pd.DataFrame:
    """日线（前复权），sina → 腾讯 → 东财 三级降级。"""
    last = None
    for name, fn in (("sina", _fetch_sina), ("tx", _fetch_tx), ("em", _fetch_em)):
        try:
            raw = fn(symbol, start_date, end_date)
            if raw is None or len(raw) == 0:
                raise ValueError("空数据")
            return _norm(raw, symbol)
        except Exception as e:  # noqa: BLE401
            last = e
            log.warning("hist[%s] %s 失败: %s", symbol, name, e)
    raise RuntimeError(f"hist[{symbol}] 全部数据源失败: {last}")


def to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """日线重采样为月线：date=YYYY-MM，开高低收 + 成交量/成交额累计。"""
    if daily is None or len(daily) == 0:
        return pd.DataFrame(columns=COLUMNS + ["symbol"])
    d = daily.copy()
    d["dt"] = pd.to_datetime(d["date"])
    d = d.set_index("dt").sort_index()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    for c in ("volume", "amount"):
        if c in d.columns:
            agg[c] = "sum"
    m = d.resample("ME").agg(agg).dropna(subset=["close"])
    if m.empty:
        return pd.DataFrame(columns=COLUMNS + ["symbol"])
    m["date"] = m.index.strftime("%Y-%m")
    m["pct_change"] = m["close"].pct_change() * 100
    m["symbol"] = daily["symbol"].iloc[0] if "symbol" in daily.columns else ""
    out = m.reset_index(drop=True)
    for c in COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA
    return out[COLUMNS + ["symbol"]]


def fetch_hist(symbol: str, period: str = "daily", start_date: str = "20100101",
               end_date: str = "20500101") -> pd.DataFrame:
    """兼容旧签名：period=monthly 时返回重采样月线。"""
    daily = fetch_daily(symbol, start_date, end_date)
    return daily if period == "daily" else to_monthly(daily)


def save(symbol: str, period: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "hist" / period
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{symbol}.parquet", index=False)
    log.info("hist[%s/%s] %s %d 行", symbol, period, symbol, len(df))
