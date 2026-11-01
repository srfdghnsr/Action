"""mock: 离线合成原始数据，用于本地预览与单测（不调用 akshare）。

生成确定性的伪行情/估值/分红/财务/筹码/板块数据，覆盖约 24 只标的与 8 个板块，
使各模块均有可渲染内容。仅用于演示与验证，非真实行情。
"""
from __future__ import annotations

import datetime as dt
import zlib
import numpy as np
import pandas as pd
from io_utils import RAW_DIR, log

SYMBOLS = [
    ("600519", "贵州茅台", "白酒", 21000e8, "2001-08-27", "up"),
    ("000858", "五粮液", "白酒", 5200e8, "1998-04-27", "up"),
    ("601318", "中国平安", "金融", 8800e8, "2007-03-01", "side"),
    ("600036", "招商银行", "银行", 9200e8, "2002-04-09", "up"),
    ("000333", "美的集团", "家电", 4900e8, "2013-09-18", "up"),
    ("600276", "恒瑞医药", "医药", 2900e8, "2000-10-18", "down"),
    ("002594", "比亚迪", "汽车", 6800e8, "2011-06-30", "up"),
    ("601012", "隆基绿能", "新能源", 1300e8, "2012-04-11", "down"),
    ("300750", "宁德时代", "新能源", 9100e8, "2018-06-11", "side"),
    ("600900", "长江电力", "能源", 7000e8, "2003-11-18", "up"),
    ("000651", "格力电器", "家电", 800e8, "1996-11-18", "up"),
    ("601888", "中国中免", "旅游", 900e8, "2009-10-15", "up"),
    ("600887", "伊利股份", "食品", 1800e8, "1996-03-12", "up"),
    ("603288", "海天味业", "食品", 700e8, "2014-02-11", "up"),
    ("000001", "平安银行", "银行", 2200e8, "1991-04-03", "side"),
    ("600030", "中信证券", "金融", 3100e8, "2003-01-06", "side"),
    ("601398", "工商银行", "银行", 19000e8, "2006-10-27", "up"),
    ("002415", "海康威视", "科技", 950e8, "2010-05-28", "up"),
    ("600309", "万华化学", "化工", 600e8, "2001-01-05", "up"),
    ("601899", "紫金矿业", "有色", 850e8, "2008-04-25", "up"),
    ("600585", "海螺水泥", "建材", 450e8, "2002-02-07", "up"),
    ("603259", "药明康德", "医药", 550e8, "2018-05-08", "up"),
    ("ST 某某", "ST某某", "其它", 30e8, "2015-01-01", "down"),
    ("688981", "中芯国际", "科技", 4200e8, "2020-07-16", "side"),
]

BOARDS = ["白酒", "银行", "家电", "医药", "汽车", "新能源", "食品", "金融"]
BOARD_SYMBOLS = {b: [s[0] for s in SYMBOLS if s[2] == b][:4] or [SYMBOLS[0][0]] for b in BOARDS}


def _seed(seed: str) -> int:
    return zlib.crc32(seed.encode("utf-8")) % (2 ** 32)


def _rng(seed: str) -> np.random.Generator:
    return np.random.default_rng(_seed(seed))


def _trading_days(n: int, end: dt.date = dt.date(2026, 10, 30)):
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(days))


def _make_daily(sym, profile, n=1500):
    rng = _rng(sym + "d")
    days = _trading_days(n)
    t = np.arange(n)
    drift = {"up": 0.00045, "down": -0.0004, "side": 0.0}[profile]
    vol = 0.013
    logp = np.cumsum(rng.normal(drift, vol, n))
    # 叠加周期成分，且按标错开相位：制造反复的 RSI 上穿 50，使不同标的不同时点触发
    phase = (zlib.crc32(sym.encode("utf-8")) % 360) / 360.0 * 2 * np.pi
    if profile == "up":
        logp += 0.12 * np.sin(2 * np.pi * t / 120 + phase)
    elif profile == "down":
        logp += 0.11 * np.sin(2 * np.pi * t / 90 + phase)
    else:
        logp += 0.09 * np.sin(2 * np.pi * t / 150 + phase)
    price = 20.0 * np.exp(logp)
    price = np.maximum(price, 1.0)
    open_ = price * (1 + rng.normal(0, 0.005, n))
    high = np.maximum(open_, price) * (1 + np.abs(rng.normal(0, 0.008, n)))
    low = np.minimum(open_, price) * (1 - np.abs(rng.normal(0, 0.008, n)))
    vol_ = rng.integers(1e6, 5e7, n).astype(float)
    df = pd.DataFrame({
        "date": [d.isoformat() for d in days],
        "open": open_.round(2), "close": price.round(2), "high": high.round(2),
        "low": low.round(2), "volume": vol_, "amount": (vol_ * price).round(0),
        "pct_change": (pd.Series(price).pct_change().fillna(0) * 100).round(2),
    })
    return df


def _monthly(daily):
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date").resample("ME").agg({
        "open": "first", "close": "last", "high": "max", "low": "min",
        "volume": "sum", "amount": "sum",
    }).reset_index()
    d["date"] = d["date"].dt.strftime("%Y-%m")
    d["pct_change"] = (d["close"].pct_change().fillna(0) * 100).round(2)
    return d


def _valuation(sym, profile, n=600):
    rng = _rng(sym + "v")
    days = _trading_days(n)
    pe = np.maximum(rng.normal(25 if profile != "down" else 35, 8, n), 5)
    pb = np.maximum(rng.normal(4, 1.5, n), 0.5)
    dy = np.maximum(rng.normal(2.0, 1.0, n), 0.1)
    return pd.DataFrame({
        "symbol": sym, "date": [d.isoformat() for d in days],
        "pe_ttm": pe.round(2), "pb": pb.round(2), "div_yield": dy.round(3),
    })


def _dividend(sym, profile):
    years = [2021, 2022, 2023, 2024, 2025]
    rng = _rng(sym + "div")
    rows = []
    base = 1.5 if profile != "down" else 0.3
    for y in years:
        dps = max(0.0, round(base + rng.normal(0, 0.3), 2))
        rows.append({
            "symbol": sym, "year": y, "ex_date": f"{y+1}-06-10",
            "dividend_text": f"10派{dps*10:.1f}元", "div_per_share": dps,
            "dividend_yield": round(dps / 30 * 100, 2),
            "payout_ratio": round(min(0.8, 0.3 + rng.normal(0, 0.1)), 2),
        })
    return pd.DataFrame(rows)


def _financial(sym, profile):
    rng = _rng(sym + "fin")
    np_ = rng.normal(200e8, 80e8) if profile != "down" else -rng.normal(20e8, 10e8)
    cf_ = np_ * rng.uniform(1.0, 1.6)
    return pd.DataFrame([{
        "symbol": sym, "date": "2025-12-31",
        "net_profit": round(np_, 0), "operate_cashflow": round(cf_, 0),
    }])


def _cyq(sym, profile, n=250):
    rng = _rng(sym + "cyq")
    days = _trading_days(n)
    if profile == "up":
        pr = np.linspace(40, 92, n) + rng.normal(0, 3, n)
    elif profile == "down":
        pr = np.linspace(80, 8, n) + rng.normal(0, 3, n)
    else:
        pr = rng.uniform(45, 70, n)
    pr = np.clip(pr, 1, 99)
    conc = np.clip(rng.normal(12, 5, n), 3, 40)
    avg = np.linspace(20, 35, n)
    df = pd.DataFrame({
        "日期": [d.isoformat() for d in days],
        "获利比例": pr.round(2), "平均成本": avg.round(2),
        "90成本-低": (avg * 0.85).round(2), "90成本-高": (avg * 1.15).round(2),
        "90集中度": conc.round(2), "70成本-低": (avg * 0.9).round(2),
        "70成本-高": (avg * 1.1).round(2), "70集中度": (conc * 0.8).round(2),
    })
    return df


def _cyq_cottle(sym, profile, n=120, nb=20):
    rng = _rng(sym + "cot")
    days = _trading_days(n)
    price = np.linspace(25, 40 if profile == "up" else 18, n)
    rows = []
    for i in range(n):
        # 主峰位置：up→低位锁定(低), down→高位(高)
        peak = max(1, int(nb * (0.2 if profile == "up" else 0.8)))
        w = np.exp(-((np.arange(nb) - peak) ** 2) / (2 * (2.5 + i * 0.02) ** 2))
        w += rng.normal(0, 0.02, nb)
        w = np.clip(w, 0, None)
        w = w / w.sum()
        row = {"日期": days[i].isoformat(), "收盘价": round(price[i], 2),
               "获利比例": round(rng.uniform(40, 90), 2), "平均成本": round(price[i] * 0.9, 2)}
        for k in range(nb):
            row[f"成本分布_{k}"] = round(float(w[k]), 4)
        rows.append(row)
    return pd.DataFrame(rows)


def _benchmark(n=150):
    rng = _rng("bench")
    months = pd.date_range(end="2026-10-01", periods=n, freq="MS")
    price = 3000 * np.exp(np.cumsum(rng.normal(0.005, 0.06, n)))
    return pd.DataFrame({"date": [d.strftime("%Y-%m") for d in months], "close": price.round(2)})


def generate() -> None:
    # 确保原始数据子目录存在
    for sub in ["hist/daily", "hist/monthly", "valuation", "dividend", "financial",
                "cyq", "cyq_cottle", "board_cons", "board_hist", "benchmark"]:
        (RAW_DIR / sub).mkdir(parents=True, exist_ok=True)

    # universe
    uni_rows = []
    info_rows = []
    for sym, name, ind, mcap, ldate, prof in SYMBOLS:
        uni_rows.append({"symbol": sym, "name": name, "price": 30.0, "mcap": mcap,
                         "circ_mcap": mcap * 0.8, "pe": 25.0, "pb": 4.0, "pct_change": 0.0})
        info_rows.append({"symbol": sym, "list_date": ldate, "industry": ind,
                          "total_mcap": mcap, "circ_mcap": mcap * 0.8})
    pd.DataFrame(uni_rows).to_parquet(RAW_DIR / "universe.parquet", index=False)
    pd.DataFrame(info_rows).to_parquet(RAW_DIR / "stock_info.parquet", index=False)
    log.info("mock universe %d", len(uni_rows))

    for sym, name, ind, mcap, ldate, prof in SYMBOLS:
        daily = _make_daily(sym, prof)
        daily["symbol"] = sym
        monthly = _monthly(daily)
        monthly["symbol"] = sym
        daily.to_parquet(RAW_DIR / "hist" / "daily" / f"{sym}.parquet", index=False)
        monthly.to_parquet(RAW_DIR / "hist" / "monthly" / f"{sym}.parquet", index=False)
        _valuation(sym, prof).to_parquet(RAW_DIR / "valuation" / f"{sym}.parquet", index=False)
        _dividend(sym, prof).to_parquet(RAW_DIR / "dividend" / f"{sym}.parquet", index=False)
        _financial(sym, prof).to_parquet(RAW_DIR / "financial" / f"{sym}.parquet", index=False)
        _cyq(sym, prof).to_parquet(RAW_DIR / "cyq" / f"{sym}.parquet", index=False)
        _cyq_cottle(sym, prof).to_parquet(RAW_DIR / "cyq_cottle" / f"{sym}.parquet", index=False)
    log.info("mock 个股数据完成")

    # 板块
    bl = pd.DataFrame({"board_code": [f"B{i:03d}" for i in range(len(BOARDS))], "board_name": BOARDS})
    bl.to_parquet(RAW_DIR / "board_list.parquet", index=False)
    for b in BOARDS:
        name_of = {s[0]: s[1] for s in SYMBOLS}
        cons = pd.DataFrame([{"board_name": b, "symbol": s, "name": name_of[s]} for s in BOARD_SYMBOLS[b]])
        cons.to_parquet(RAW_DIR / "board_cons" / f"{b}.parquet", index=False)
        rng = _rng(b + "h")
        months = [d.strftime("%Y-%m") for d in _trading_days(60)][::21][:60]
        closes = 1000 * np.exp(np.cumsum(rng.normal(0.002, 0.05, len(months))))
        bh = pd.DataFrame({"board_name": b, "date": months, "close": closes.round(2),
                           "pct_change": (pd.Series(closes).pct_change().fillna(0) * 100).round(2)})
        bh.to_parquet(RAW_DIR / "board_hist" / f"{b}.parquet", index=False)
    log.info("mock 板块数据完成")

    # 基准
    _benchmark().to_parquet(RAW_DIR / "benchmark" / "000300.parquet", index=False)
    log.info("mock 全部生成完毕")
