"""indicators: 纯函数技术指标（手算，不依赖 talib，可离线单测）。

所有函数接收 pandas Series / DataFrame，返回同索引结果。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder RSI。"""
    close = close.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(avg_loss != 0, 100.0)  # 无下跌时 RSI=100
    return out


def ma(close: pd.Series, window: int) -> pd.Series:
    return close.astype(float).rolling(window, min_periods=window).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.astype(float).ewm(span=fast, adjust=False).mean()
    ema_slow = close.astype(float).ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = (dif - dea) * 2
    return dif, dea, hist


def pct_rank(series: pd.Series, value: float) -> float:
    """value 在历史序列中的分位（0-1）。越便宜的分位越低。"""
    s = series.dropna().astype(float)
    if len(s) == 0:
        return 0.5
    return float((s < value).mean())


def cheap_percentile(series: pd.Series, value: float) -> float:
    """便宜分位：当前值处于历史越低位置 → 越便宜 → 分位越高。"""
    return 1.0 - pct_rank(series, value)


def monthly_rsi_golden_cross(month_close: pd.Series, window: int = 14,
                             midline: float = 50.0, lookback: int = 3) -> bool:
    """月线 RSI 在最近 lookback 个月内上穿中线（默认 50）视为金叉。"""
    if len(month_close) < window + 2:
        return False
    r = rsi(month_close, window).dropna()
    if len(r) < 2:
        return False
    lo = max(1, len(r) - lookback)
    for i in range(lo, len(r)):
        if r.iloc[i - 1] <= midline < r.iloc[i]:
            return True
    return False


def above_ma(close: pd.Series, window: int) -> bool:
    if len(close) < window:
        return False
    m = ma(close, window).iloc[-1]
    return bool(close.iloc[-1] > m) if not pd.isna(m) else False


def max_drawdown(equity: pd.Series) -> float:
    eq = equity.astype(float)
    if len(eq) == 0:
        return 0.0
    running_max = eq.cummax()
    dd = eq / running_max - 1.0
    return float(dd.min())


def annualized_return(total_return: float, years: float) -> float:
    if years <= 0:
        return 0.0
    return float((1 + total_return) ** (1 / years) - 1)
