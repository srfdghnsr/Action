"""selectors 5 条件边界单测。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compute.selectors import evaluate

CFG = {
    "selector": {
        "rsi_window": 14, "m250_window": 250, "mcap_min": 5e9, "mcap_max": 1e11,
        "min_listed_days": 3500, "exclude_st": True, "exclude_delisted": True,
    }
}


def _daily(up=True):
    import pandas as pd
    n = 300
    base = list(range(50, 50 + n)) if up else list(range(300, 300 - n, -1))
    return pd.DataFrame({"date": pd.date_range("2015-01-01", periods=n), "close": base})


def _monthly(cross=True):
    import pandas as pd
    if cross:
        # 先跌后，最后 3 个月急涨，使 RSI 在最近窗口内上穿 50
        base = list(range(100, 50, -1)) + [60, 72, 88]
    else:
        base = list(range(50, 110))  # 单调上行，RSI 始终在上沿，无"下穿上"金叉
    return pd.DataFrame({"date": pd.date_range("2015-01-01", periods=len(base), freq="ME"), "close": base})


def test_pass_case():
    rec = evaluate("600519", "贵州茅台", {"mcap": 5e10, "name": "贵州茅台"},
                   {"list_date": "2001-08-27"}, _daily(True), _monthly(True), CFG)
    assert rec["pass"] is True, rec["signals"]
    print("test_pass_case OK")


def test_st_fail():
    rec = evaluate("600xxx", "ST某某", {"mcap": 5e10, "name": "ST某某"},
                   {"list_date": "2001-08-27"}, _daily(True), _monthly(True), CFG)
    assert rec["pass"] is False
    assert rec["signals"]["not_st"] is False
    print("test_st_fail OK")


def test_mcap_out_of_range():
    rec = evaluate("600yyy", "小市值", {"mcap": 1e8, "name": "小市值"},
                   {"list_date": "2001-08-27"}, _daily(True), _monthly(True), CFG)
    assert rec["signals"]["mcap_ok"] is False
    print("test_mcap_out_of_range OK")


if __name__ == "__main__":
    test_pass_case()
    test_st_fail()
    test_mcap_out_of_range()
    print("ALL SELECTOR TESTS PASSED")
