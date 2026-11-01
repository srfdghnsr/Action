"""backtest: 模块4c 策略回测（无未来函数，诚实优先）。

方法：
- 每个标的的指标（RSI/MA）在全序列上计算后按月末 as-of 取值 —— RSI/MA 均为因果指标，
  在 t 时刻取值只依赖 ≤t 数据，无前视。
- 历史市值用「最新市值 / 最新价 × 历史价」回推股本估算（point-in-time 近似，已知局限）。
- 月末调仓：用 t 时刻信号选出标的，等权持有至下一月末，收益取下一月区间收益。
- 训练/验证/样本外三段切分仅用于报告，样本外结果不用于调参。
- 样本外交易次数 < min_trades_for_sig → 显著字段标注「仅观测」。
"""
from __future__ import annotations

import datetime as dt
import math
import pandas as pd
from io_utils import log, read_parquet, write_json, RAW_DIR, safe_div

from .indicators import rsi, ma

try:
    from scipy import stats as _stats
    HAS_SCIPY = True
except Exception:  # noqa: BLE001
    HAS_SCIPY = False


def _normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _asof(series: pd.Series, date) -> float:
    if series is None or len(series) == 0:
        return float("nan")
    try:
        return float(series.asof(pd.Timestamp(date)))
    except Exception:
        return float("nan")


def run_backtest(settings, daily_dir, monthly_dir, name_map, mcap_latest_map,
                 price_latest_map, list_date_map, bench_monthly=None) -> dict:
    cfg = settings["backtest"]
    sel = settings.get("selector", cfg)  # 选股阈值在 selector 下；测试可退化到 cfg
    sw = sel.get("rsi_window", 14)
    mw = sel.get("m250_window", 250)
    min_mcap, max_mcap = sel.get("mcap_min", 0), sel.get("mcap_max", float("inf"))
    min_days = sel.get("min_listed_days", 0)

    # 预计算每个标的的因果指标
    universe = {}
    for f in sorted(monthly_dir.glob("*.parquet")):
        sym = f.stem
        m = pd.read_parquet(f).sort_values("date")
        d_path = daily_dir / f"{sym}.parquet"
        if not d_path.exists():
            continue
        d = pd.read_parquet(d_path).sort_values("date")
        if len(d) < mw or len(m) < sw + 2:
            continue
        m["_dt"] = pd.to_datetime(m["date"])
        d["_dt"] = pd.to_datetime(d["date"])
        m_close = m.set_index("_dt")["close"].astype(float)
        d_close = d.set_index("_dt")["close"].astype(float)
        m_rsi = rsi(m_close, sw)
        d_ma = ma(d_close, mw)
        price_now = float(d_close.iloc[-1])
        mcap_now = float(mcap_latest_map.get(sym) or 0)
        shares = safe_div(mcap_now, price_now)
        list_d = list_date_map.get(sym)
        universe[sym] = {
            "m_close": m_close, "d_close": d_close, "m_rsi": m_rsi,
            "d_ma": d_ma, "shares": shares, "list_date": list_d,
            "name": name_map.get(sym, sym),
        }

    if not universe:
        log.warning("backtest: 无可用标的")
        return {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                "error": "no_data", "equity": []}

    # 月末序列（取各标的月末并集，限定在训练起点之后）
    start = pd.Timestamp(cfg["train_start"])
    ends = set()
    for info in universe.values():
        for dt_ in info["m_close"].index:
            if pd.Timestamp(dt_) >= start:
                ends.add(pd.Timestamp(dt_).to_period("M").to_timestamp())
    ends = sorted(ends)
    if len(ends) < 2:
        return {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
                "error": "too_few_periods", "equity": []}

    equity = 1.0
    bench_equity = 1.0 if bench_monthly is not None else None
    dates, eq_vals, bench_vals, sel_counts = [], [], [], []
    monthly_rets = []

    for i in range(len(ends) - 1):
        t, t1 = ends[i], ends[i + 1]
        selected = []
        for sym, info in universe.items():
            # 上市满 min_days 天才纳入（无未来函数：仅用历史上市日）
            if info["list_date"]:
                if pd.Timestamp(info["list_date"]) > (t - pd.Timedelta(days=min_days)):
                    continue
            rsi_t = _asof(info["m_rsi"], t)
            rsi_prev = _asof(info["m_rsi"], ends[i - 1] if i > 0 else t)
            cross = (not math.isnan(rsi_prev)) and (not math.isnan(rsi_t)) and (rsi_prev <= 50 < rsi_t)
            close_t = _asof(info["d_close"], t)
            ma_t = _asof(info["d_ma"], t)
            above = (not math.isnan(ma_t)) and (not math.isnan(close_t)) and close_t > ma_t
            mcap_t = info["shares"] * close_t
            mcap_ok = (not math.isnan(mcap_t)) and (min_mcap < mcap_t < max_mcap)
            nm = str(info["name"] or "")
            not_st = ("ST" not in nm) and ("退" not in nm)
            if cross and above and mcap_ok and not_st:
                selected.append(sym)
        if selected:
            rets = []
            for sym in selected:
                c0 = _asof(universe[sym]["d_close"], t)
                c1 = _asof(universe[sym]["d_close"], t1)
                if not math.isnan(c0) and not math.isnan(c1) and c0 > 0:
                    rets.append(c1 / c0 - 1)
            port = float(pd.Series(rets).mean()) if rets else 0.0
        else:
            port = 0.0
        equity *= (1 + port)
        monthly_rets.append(port)
        sel_counts.append(len(selected))
        dates.append(t.strftime("%Y-%m"))
        eq_vals.append(round(equity, 4))
        if bench_equity is not None:
            bc0 = _asof(bench_monthly, t)
            bc1 = _asof(bench_monthly, t1)
            if not math.isnan(bc0) and not math.isnan(bc1) and bc0 > 0:
                bench_equity *= (1 + bc1 / bc0 - 1)
            bench_vals.append(round(bench_equity, 4))

    rets_s = pd.Series(monthly_rets)
    n = len(rets_s)
    total = equity - 1
    years = (ends[-1] - ends[0]).days / 365.25
    ann = ((1 + total) ** (1 / years) - 1) if years > 0 else 0.0
    win = float((rets_s > 0).mean()) if n else 0.0
    eq_series = pd.Series(eq_vals)
    mdd = float((eq_series / eq_series.cummax() - 1).min()) if len(eq_series) else 0.0
    mdd = min(0.0, mdd)
    sharpe = float(rets_s.mean() / rets_s.std() * math.sqrt(12)) if rets_s.std() > 0 else 0.0

    # 显著性（诚实）
    if n >= 2 and rets_s.std() > 0:
        t_stat = rets_s.mean() / (rets_s.std() / math.sqrt(n))
        p_val = 2 * (1 - _normal_cdf(abs(t_stat)))
    else:
        t_stat, p_val = 0.0, 1.0
    significance = "统计显著" if (n >= cfg["min_trades_for_sig"] and p_val < 0.05) else "仅观测，不具统计显著"

    bench_total = (bench_equity - 1) if bench_equity is not None else None

    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "params": cfg,
        "period": {"start": ends[0].strftime("%Y-%m"), "end": ends[-1].strftime("%Y-%m"),
                   "n_months": n},
        "metrics": {
            "total_return": round(total, 4),
            "annualized": round(ann, 4),
            "win_rate": round(win, 4),
            "max_drawdown": round(mdd, 4),
            "sharpe": round(sharpe, 3),
            "benchmark_total_return": round(bench_total, 4) if bench_total is not None else None,
            "excess_return": round(total - bench_total, 4) if bench_total is not None else None,
        },
        "significance": significance,
        "t_stat": round(float(t_stat), 3),
        "p_value": round(float(p_val), 4),
        "avg_selected": round(float(pd.Series(sel_counts).mean()), 1) if sel_counts else 0,
        "equity": [{"date": d, "strategy": e, "benchmark": b}
                   for d, e, b in zip(dates, eq_vals, bench_vals if bench_vals else [None] * len(eq_vals))],
        "config_hash": _hash_cfg(cfg),
    }
    write_json(out, "backtest.json")
    log.info("backtest: %d 月，累计 %.1f%%，显著性=%s", n, total * 100, significance)
    return out


def _hash_cfg(cfg: dict) -> str:
    import hashlib, json
    return hashlib.md5(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:10]
