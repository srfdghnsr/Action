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


def _tencent_probe():
    """直接打腾讯批量行情，验证字段位（市值/PE/PB 在第几位）。"""
    import pandas as pd
    import requests

    codes = ["sh600519", "sz000651", "sh601398", "sz300750"]
    r = requests.get("https://qt.gtimg.cn/q=" + ",".join(codes), timeout=12,
                     headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"})
    r.encoding = "gbk"
    rows = []
    for line in r.text.split(";"):
        line = line.strip()
        if not line.startswith("v_") or '="' not in line:
            continue
        payload = line.split('="', 1)[1].rstrip('"')
        f = payload.split("~")
        rows.append({"code": f[2] if len(f) > 2 else "?", "name": f[1] if len(f) > 1 else "?",
                     "price": f[3] if len(f) > 3 else "",
                     "pe_39": f[39] if len(f) > 39 else "",
                     "circ_44": f[44] if len(f) > 44 else "",
                     "mcap_45": f[45] if len(f) > 45 else "",
                     "pb_46": f[46] if len(f) > 46 else "",
                     "fields": len(f)})
    df = pd.DataFrame(rows)
    print("[tencent sample]", rows)
    return df


def main():
    import akshare as ak

    cases = []

    def add(label, fn):
        cases.append((label, fn))

    # --- 第二轮的候选换源方案 ---
    add("tx/qt 批量行情(自写解析)", lambda: _tencent_probe())
    add("ak/stock_info_a_code_name", lambda: ak.stock_info_a_code_name())
    add("sina/sector_spot 行业", lambda: ak.stock_sector_spot(indicator="行业"))
    add("ths/board_industry_name", lambda: ak.stock_board_industry_name_ths())
    add("sina/index_daily sh000300", lambda: ak.stock_zh_index_daily(symbol="sh000300"))
    add("em/cyq 600519", lambda: ak.stock_cyq_em(symbol="600519", adjust=""))

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
