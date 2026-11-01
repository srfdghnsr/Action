"""selectors: 模块1 优质牛股评估体系（5 条件打分）。

条件：①月线RSI金叉 ②股价>m250 ③市值50-1000亿 ④上市>3500天 ⑤剔除ST。
全部满足才入选。输出入选列表 + 各维度打分。
"""
from __future__ import annotations

import datetime as dt
import pandas as pd
from io_utils import log, read_parquet, write_json, RAW_DIR, safe_div

from .indicators import rsi, ma, monthly_rsi_golden_cross, above_ma


def _get(obj, key, default=None):
    """兼容 dict / pandas Series 的取值。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj.get(key, default)
    except Exception:
        return default


def _days_listed(list_date) -> int:
    if list_date is None:
        return 0
    try:
        d = pd.Timestamp(list_date)
        return (pd.Timestamp.now().normalize() - d).days
    except Exception:
        return 0


def evaluate(symbol, name, spot, info, daily, monthly, cfg) -> dict:
    s = cfg["selector"]
    rec = {"symbol": symbol, "name": name, "pass": False,
           "scores": {}, "signals": {}}
    # 市值
    mcap = _get(spot, "mcap")
    try:
        mcap = float(mcap)
    except Exception:
        mcap = None
    mcap_ok = bool(mcap is not None and s["mcap_min"] < mcap < s["mcap_max"])
    rec["scores"]["mcap"] = mcap
    rec["signals"]["mcap_ok"] = mcap_ok

    # ST / 退市
    nm = str(name or "")
    not_st = (s.get("exclude_st", True) and ("ST" not in nm and "退" not in nm))
    rec["signals"]["not_st"] = not_st

    # 上市天数
    listed_days = _days_listed(_get(info, "list_date"))
    age_ok = listed_days > s["min_listed_days"]
    rec["scores"]["listed_days"] = listed_days
    rec["signals"]["age_ok"] = age_ok

    # 股价 > m250 （日线）
    above = False
    if daily is not None and len(daily) >= s["m250_window"]:
        above = above_ma(daily["close"].reset_index(drop=True), s["m250_window"])
    rec["signals"]["above_m250"] = above

    # 月线 RSI 金叉
    cross = False
    if monthly is not None and len(monthly) >= s["rsi_window"] + 2:
        cross = monthly_rsi_golden_cross(monthly["close"].reset_index(drop=True), s["rsi_window"])
    rec["signals"]["rsi_cross"] = cross

    rec["pass"] = all([mcap_ok, not_st, age_ok, above, cross])
    return rec


def collect(settings) -> dict:
    cfg = settings
    try:
        universe = read_parquet("universe.parquet")
    except Exception as e:  # noqa: BLE001
        log.warning("selectors: 无 universe (%s)，跳过", e)
        universe = pd.DataFrame()
    try:
        info = read_parquet("stock_info.parquet")
    except Exception:
        info = pd.DataFrame()

    info_map = {r["symbol"]: r for _, r in info.iterrows()} if len(info) else {}
    uni_map = {}
    if len(universe):
        for _, r in universe.iterrows():
            uni_map[str(r.get("symbol"))] = r.to_dict()

    daily_dir = RAW_DIR / "hist" / "daily"
    monthly_dir = RAW_DIR / "hist" / "monthly"
    symbols = sorted(set(info_map) | set(uni_map))
    selected, scanned = [], 0
    for sym in symbols:
        if sym in ("None", "nan", ""):
            continue
        spot = uni_map.get(sym, {})
        inf = info_map.get(sym, {})
        if hasattr(inf, "to_dict"):
            inf = inf.to_dict()
        name = spot.get("name") or inf.get("industry") or sym
        d_path = daily_dir / f"{sym}.parquet"
        m_path = monthly_dir / f"{sym}.parquet"
        daily = pd.read_parquet(d_path) if d_path.exists() else None
        monthly = pd.read_parquet(m_path) if m_path.exists() else None
        if daily is not None:
            daily = daily.sort_values("date")
        if monthly is not None:
            monthly = monthly.sort_values("date")
        rec = evaluate(sym, name, spot, inf, daily, monthly, cfg)
        scanned += 1
        if rec["pass"]:
            selected.append(rec)

    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": cfg["selector"],
        "total_scanned": scanned,
        "selected_count": len(selected),
        "selected": selected,
    }
    write_json(out, "selectors.json")
    log.info("selectors: 扫描 %d，入选 %d", scanned, len(selected))
    return out
