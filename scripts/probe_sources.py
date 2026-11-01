"""probe_sources: 在 GitHub Actions（美国 runner）上探测各 A 股数据源可用性。

目的：东财接口在境外被阻断（RemoteDisconnected），需实测哪些源能通，
再决定抓取层用哪套接口。结果同时写入 probe_result.json 并打印到 stdout。
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "probe_result.json")
TIMEOUT = 30


def _run(label, fn):
    t0 = time.time()
    try:
        df = fn()
        n = len(df) if hasattr(df, "__len__") else 0
        cols = list(getattr(df, "columns", []))[:12]
        return {"label": label, "ok": True, "rows": n, "cols": cols,
                "sec": round(time.time() - t0, 1), "err": ""}
    except Exception as e:  # noqa: BLE001
        return {"label": label, "ok": False, "rows": 0, "cols": [],
                "sec": round(time.time() - t0, 1),
                "err": f"{type(e).__name__}: {str(e)[:160]}"}


def main():
    import akshare as ak

    cases = []

    def add(label, fn):
        cases.append((label, fn))

    add("em/spot 全市场快照", lambda: ak.stock_zh_a_spot_em())
    add("sina/spot 全市场快照", lambda: ak.stock_zh_a_spot())
    add("em/hist 600519 日线", lambda: ak.stock_zh_a_hist(
        symbol="600519", period="daily", start_date="20240101", end_date="20240131", adjust=""))
    add("sina/daily sh600519", lambda: ak.stock_zh_a_daily(symbol="sh600519", adjust=""))
    add("tx/hist 600519", lambda: ak.stock_zh_a_hist_tx(symbol="sh600519", start_date="20240101", end_date="20240131"))
    add("em/individual_info 600519", lambda: ak.stock_individual_info_em(symbol="600519"))
    add("em/financial_abstract 600519", lambda: ak.stock_financial_abstract(symbol="600519"))
    add("cninfo/dividend 600519", lambda: ak.stock_dividend_cninfo(symbol="600519"))
    add("em/board_industry_name", lambda: ak.stock_board_industry_name_em())
    add("em/index_zh_a_hist 000300", lambda: ak.index_zh_a_hist(
        symbol="000300", period="daily", start_date="20240101", end_date="20240131"))
    add("sina/index_daily sh000300", lambda: ak.stock_zh_index_daily(symbol="sh000300"))
    add("em/cyq 600519", lambda: ak.stock_cyq_em(symbol="600519", adjust=""))
    add("baidu/valuation 600519", lambda: ak.stock_zh_valuation_baidu(
        symbol="600519", indicator="总市值", period="近一年"))
    add("lg/indicator 600519", lambda: ak.stock_a_indicator_lg(symbol="600519"))

    results = []
    ex = ThreadPoolExecutor(max_workers=14)
    futs = {ex.submit(_run, label, fn): label for label, fn in cases}
    try:
        for fut in as_completed(futs, timeout=TIMEOUT + 10):
            results.append(fut.result())
    except Exception:  # noqa: BLE401
        for f, label in futs.items():
            if not f.done():
                results.append({"label": label, "ok": None, "rows": 0, "cols": [],
                                "sec": TIMEOUT, "err": "未在超时内返回"})
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    order = {label: i for i, (label, _) in enumerate(cases)}
    results.sort(key=lambda r: order.get(r["label"], 99))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("=== PROBE RESULT ===")
    for r in results:
        flag = "OK  " if r["ok"] else ("TIME" if r["ok"] is None else "FAIL")
        print(f"[{flag}] {r['label']:<24} rows={r['rows']:<6} {r['sec']}s  {r['err']}")
    print("=== END ===")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE401
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(1)
