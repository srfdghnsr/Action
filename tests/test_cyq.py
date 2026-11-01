"""cyq 判读函数单测。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pandas as pd
from compute.cyq_analysis import judge_band, judge_density, analyze


def test_judge_band():
    assert "底部" in judge_band(3)
    assert "洗盘" in judge_band(20)
    assert "健康" in judge_band(80)
    assert "减仓" in judge_band(97)
    print("test_judge_band OK")


def test_judge_density():
    assert "单峰" in judge_density(8)
    assert "相对集中" in judge_density(12)
    assert "正常发散" in judge_density(20)
    print("test_judge_density OK")


def test_analyze():
    cyq = pd.DataFrame([{
        "日期": "2026-10-30", "获利比例": 88.0, "平均成本": 30.0,
        "90成本-低": 25, "90成本-高": 35, "90集中度": 9.0,
        "70成本-低": 27, "70成本-高": 33, "70集中度": 7.0,
    }])
    cottle = pd.DataFrame([{
        "日期": "2026-10-30", "收盘价": 40.0, "获利比例": 88.0, "平均成本": 30.0,
        "成本分布_0": 0.01, "成本分布_1": 0.02, "成本分布_2": 0.05,
        "成本分布_3": 0.1, "成本分布_4": 0.3, "成本分布_5": 0.3, "成本分布_6": 0.2,
        "成本分布_7": 0.02,
    }])
    r = analyze("600519", "贵州茅台", cyq, cottle)
    assert r["profit_ratio"] == 88.0
    assert r["concentration_90"] == 9.0
    assert "单峰" in r["density"]
    assert r["peak_position"] is not None
    assert r["stop_estimate"] is not None
    print("test_analyze OK ->", r["band"], r["density"], r["peak_migration"])


if __name__ == "__main__":
    test_judge_band()
    test_judge_density()
    test_analyze()
    print("ALL CYQ TESTS PASSED")
