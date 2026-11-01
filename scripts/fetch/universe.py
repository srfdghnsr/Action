"""universe: 全市场 A 股快照（总市值 / PE / PB）。

换源说明：东财 `stock_zh_a_spot_em` 的 push2 域名对境外 IP 直接断连
（2026-11-01 在 GitHub 美国 runner 实测 RemoteDisconnected），因此改为
**腾讯批量行情 qt.gtimg.cn（自带总市值/流通市值/PE/PB）** 为主；
代码表依次尝试 sina 快照 → 东财代码表 → 代码段枚举。
"""
from __future__ import annotations

import pandas as pd
import requests

from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

REQUIRED = ["symbol", "name", "price", "mcap", "circ_mcap", "pe", "pb"]

# 腾讯行情字段位（2026-11-01 实测，88 字段）：1=名称 2=代码 3=现价
# 39=PE(TTM) 44=流通市值(亿) 45=总市值(亿) 46=PB
_TX_URL = "https://qt.gtimg.cn/q="
_TX_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"}
_BATCH = 60

# 仅当所有代码表接口都不可用时才枚举（覆盖沪深主板/创业板/科创板/北交所主段）
_CODE_RANGES = [
    (600000, 606000), (688000, 689100),
    (1, 4000), (300000, 302000),
    (430000, 430900), (830000, 839000), (870000, 879000), (920000, 921000),
]


def market_prefix(symbol: str) -> str:
    s = str(symbol).zfill(6)
    if s[0] == "6":
        return "sh"
    if s[0] in ("4", "8", "9"):
        return "bj"
    return "sz"


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _parse_tx(text: str) -> list[dict]:
    rows = []
    for line in text.split(";"):
        line = line.strip()
        if not line.startswith("v_") or '="' not in line:
            continue
        payload = line.split('="', 1)[1].rstrip('"')
        f = payload.split("~")
        if len(f) < 47 or not f[2]:
            continue
        mcap_yi = _to_float(f[45])
        circ_yi = _to_float(f[44])
        if circ_yi != circ_yi:
            circ_yi = mcap_yi
        rows.append({
            "symbol": f[2].zfill(6),
            "name": f[1],
            "price": _to_float(f[3]),
            "mcap": mcap_yi * 1e8,
            "circ_mcap": circ_yi * 1e8,
            "pe": _to_float(f[39]),
            "pb": _to_float(f[46]),
        })
    return rows


def _tx_quotes(codes: list[str]) -> list[dict]:
    """codes 为带前缀（sh/sz/bj）代码，分批请求腾讯批量行情。"""
    out: list[dict] = []
    for i in range(0, len(codes), _BATCH):
        chunk = codes[i:i + _BATCH]
        try:
            r = requests.get(_TX_URL + ",".join(chunk), timeout=15, headers=_TX_HEADERS)
            r.encoding = "gbk"
            out.extend(_parse_tx(r.text))
        except Exception as e:  # noqa: BLE401
            log.warning("腾讯行情批次 %d 失败: %s", i // _BATCH, e)
    return out


def _codes_from_sina() -> list[str]:
    """新浪全市场快照（约 40s，返回带前缀代码）。"""
    import akshare as ak
    df = with_retry(ak.stock_zh_a_spot)
    col = "代码" if "代码" in df.columns else df.columns[0]
    codes = []
    for v in df[col].astype(str):
        v = v.strip().lower()
        if v.startswith(("sh", "sz", "bj")):
            codes.append(v)
        elif v.isdigit():
            codes.append(market_prefix(v) + v.zfill(6))
    return codes


def _codes_from_em() -> list[str]:
    import akshare as ak
    df = with_retry(ak.stock_info_a_code_name)
    return [market_prefix(s) + str(s).zfill(6) for s in df["code"].astype(str)]


def _codes_bruteforce() -> list[str]:
    codes = []
    for lo, hi in _CODE_RANGES:
        for n in range(lo, hi):
            s = f"{n:06d}"
            codes.append(market_prefix(s) + s)
    return codes


def fetch_universe() -> pd.DataFrame:
    """全市场快照：代码表 + 腾讯批量行情，逐级降级。"""
    codes: list[str] = []
    for name, fn in (("sina快照", _codes_from_sina), ("东财代码表", _codes_from_em),
                     ("代码段枚举", _codes_bruteforce)):
        try:
            codes = fn()
            if codes:
                log.info("代码表来源=%s，共 %d 只", name, len(codes))
                break
        except Exception as e:  # noqa: BLE401
            log.warning("代码表 %s 失败: %s", name, e)

    if not codes:
        raise RuntimeError("无法获取 A 股代码表（sina/东财/枚举 全部失败）")

    df = pd.DataFrame(_tx_quotes(codes)).drop_duplicates(subset=["symbol"])
    if df.empty:
        raise RuntimeError("腾讯批量行情未返回任何数据")

    df = df[df["price"].fillna(0) > 0].copy()
    for c in ("price", "mcap", "circ_mcap", "pe", "pb"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str)

    miss = [c for c in REQUIRED if c not in df.columns]
    if miss:
        raise RuntimeError(f"universe 缺列: {miss}")
    log.info("universe: %d 只有效行情（其中有总市值 %d 只）",
             len(df), int(df["mcap"].notna().sum()))
    return df[REQUIRED]


def save(df: pd.DataFrame) -> None:
    write_parquet(df, "universe.parquet")
    log.info("universe 保存 %d 行 -> %s", len(df), RAW_DIR / "universe.parquet")
