"""info: 个股基础信息（上市时间 / 行业 / 市值）。

换源说明：东财 `stock_individual_info_em` 在境外被阻断（返回非 JSON，
`Expecting value: line 1 column 1`），180 只候选全部失败。而它提供的信息
大多可从已有数据推导，因此**不再发起逐标的请求**：

- 上市时间 ← 日线最早一根（sina/腾讯全历史）
- 总市值 / 流通市值 ← universe（腾讯批量行情）
- 行业 ← 板块成分表反查（可选，缺省为空；仅作显示兜底）
"""
from __future__ import annotations

import pandas as pd

from io_utils import log, write_parquet
from .universe import market_prefix  # noqa: F401  （保留导出，便于外部按代码判市场）

COLUMNS = ["symbol", "list_date", "industry", "total_mcap", "circ_mcap"]


def build_record(symbol: str, daily: pd.DataFrame | None = None,
                 total_mcap: float | None = None, circ_mcap: float | None = None,
                 industry: str | None = None) -> dict:
    """从日线与快照推导基础信息，不产生网络请求。"""
    list_date = None
    if daily is not None and len(daily) > 0 and "date" in daily.columns:
        try:
            list_date = pd.Timestamp(pd.to_datetime(daily["date"]).min()).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE401
            list_date = None
    return {
        "symbol": symbol,
        "list_date": list_date,
        "industry": industry,
        "total_mcap": float(total_mcap) if total_mcap is not None else None,
        "circ_mcap": float(circ_mcap) if circ_mcap is not None else None,
    }


def fetch_info(symbol: str, **kwargs) -> dict:
    """兼容旧签名（不再请求东财）。"""
    return build_record(symbol, kwargs.get("daily"), kwargs.get("total_mcap"),
                        kwargs.get("circ_mcap"), kwargs.get("industry"))


def build_industry_map(board_cons: dict[str, pd.DataFrame]) -> dict[str, str]:
    """板块成分表 → {symbol: 板块名}，用于填充 industry。"""
    out: dict[str, str] = {}
    for board, df in (board_cons or {}).items():
        if df is None or len(df) == 0 or "symbol" not in df.columns:
            continue
        for s in df["symbol"].astype(str):
            out.setdefault(s.zfill(6), board)
    return out


def save(records: list[dict]) -> None:
    df = pd.DataFrame(records) if records else pd.DataFrame(columns=COLUMNS)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = None
    write_parquet(df[COLUMNS], "stock_info.parquet")
    log.info("stock_info 保存 %d 行", len(df))
