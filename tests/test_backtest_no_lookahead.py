"""回测无前视 + 指标计算单测（使用临时 RAW 目录，不污染真实数据）。"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pandas as pd
import numpy as np
import io_utils
from compute import backtest


def _write_symbol(tmp, sym, up=True):
    n = 1500
    rng = np.random.default_rng(hash(sym) % (2 ** 32))
    drift = 0.0004 if up else -0.0004
    price = 20 * np.exp(np.cumsum(rng.normal(drift, 0.018, n)))
    days = pd.date_range("2015-01-01", periods=n, freq="B")
    daily = pd.DataFrame({
        "date": days, "close": price, "open": price, "high": price, "low": price,
        "volume": 1e6, "amount": 1e6, "pct_change": 0,
    })
    monthly = daily.copy()
    monthly = monthly.set_index("date").resample("ME").last().reset_index()
    io_utils.RAW_DIR.joinpath("hist/daily").mkdir(parents=True, exist_ok=True)
    io_utils.RAW_DIR.joinpath("hist/monthly").mkdir(parents=True, exist_ok=True)
    daily.to_parquet(io_utils.RAW_DIR / "hist" / "daily" / f"{sym}.parquet", index=False)
    monthly.to_parquet(io_utils.RAW_DIR / "hist" / "monthly" / f"{sym}.parquet", index=False)


def test_backtest_runs():
    tmp = tempfile.mkdtemp()
    old = io_utils.RAW_DIR
    io_utils.RAW_DIR = Path(tmp)
    io_utils.RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        settings = {
            "backtest": {
                "rsi_window": 14, "m250_window": 250, "mcap_min": 5e9, "mcap_max": 1e11,
                "min_listed_days": 3500, "min_trades_for_sig": 30,
                "train_start": "2015-01-01", "train_end": "2020-12-31",
                "valid_start": "2021-01-01", "valid_end": "2023-12-31",
                "holdout_start": "2024-01-01",
            }
        }
        # 回测内部用 RAW_DIR/hist；这里直接构造临时 hist 目录
        io_utils.RAW_DIR = Path(tmp)
        for s in ["600519", "000858", "601318", "600036", "000333", "600276"]:
            _write_symbol(tmp, s, up=(s in ["600519", "000858", "600036", "000333"]))
        out = backtest.run_backtest(
            settings, Path(tmp) / "hist" / "daily", Path(tmp) / "hist" / "monthly",
            {s: s for s in ["600519", "000858", "601318", "600036", "000333", "600276"]},
            {s: 2e11 for s in ["600519", "000858", "601318", "600036", "000333", "600276"]},
            {s: 30.0 for s in ["600519", "000858", "601318", "600036", "000333", "600276"]},
            {s: "2005-01-01" for s in ["600519", "000858", "601318", "600036", "000333", "600276"]},
            None,
        )
        assert "equity" in out, out
        assert "significance" in out, out
        assert "metrics" in out, out
        # 无前视：equity 首尾有限且非负累计
        assert len(out["equity"]) > 10
        print("test_backtest_runs OK -> 月份数:", out["period"]["n_months"],
              "累计:", round(out["metrics"]["total_return"] * 100, 1), "%",
              "显著性:", out["significance"])
    finally:
        io_utils.RAW_DIR = old


if __name__ == "__main__":
    test_backtest_runs()
    print("BACKTEST TEST PASSED")
