"""指标纯函数单测（无 akshare，离线可跑）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pandas as pd
from compute.indicators import rsi, ma, above_ma, monthly_rsi_golden_cross, max_drawdown


def test_rsi_range():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10] * 5, dtype=float)
    r = rsi(s, 14)
    assert r.dropna().between(0, 100).all(), "RSI 应在 0-100"
    print("test_rsi_range OK")


def test_above_ma_true():
    s = pd.Series(range(1, 300), dtype=float)
    assert above_ma(s, 250) is True
    print("test_above_ma_true OK")


def test_monthly_rsi_golden_cross():
    # 先跌（RSI→0），最后 3 个月急涨使 RSI 在最近窗口内上穿 50
    down = pd.Series([100 - i for i in range(50)], dtype=float)
    up = pd.Series([55, 70, 88], dtype=float)
    s = pd.concat([down, up], ignore_index=True)
    assert monthly_rsi_golden_cross(s, 14) is True
    # 纯上涨：RSI 始终在上沿，无"从下穿上"的金叉
    always_up = pd.Series(range(1, 100), dtype=float)
    assert monthly_rsi_golden_cross(always_up, 14) is False
    print("test_monthly_rsi_golden_cross OK")


def test_max_drawdown():
    eq = pd.Series([1.0, 1.2, 0.9, 1.1])
    assert max_drawdown(eq) <= 0
    assert abs(max_drawdown(eq) - (-0.25)) < 1e-6
    print("test_max_drawdown OK")


if __name__ == "__main__":
    test_rsi_range()
    test_above_ma_true()
    test_monthly_rsi_golden_cross()
    test_max_drawdown()
    print("ALL INDICATOR TESTS PASSED")
