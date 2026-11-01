"""board: 行业板块列表 / 成分 / 月度行情（季节性、性价比用）。

换源说明：东财 `stock_board_industry_name_em` 境外被断连，改为
**同花顺（THS）为主 → 新浪行业板块 → 东财** 逐级降级。
任一层失败只影响季节性地基，不阻断主流程。
"""
from __future__ import annotations

import pandas as pd

from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

NAME_COLUMNS = ["board_code", "board_name"]
CONS_COLUMNS = ["board_name", "symbol", "name"]
HIST_COLUMNS = ["board_name", "date", "close", "pct_change"]


def _try(fns, label):
    """依次尝试多个 (名称, 可调用) 组合，返回第一个非空结果。"""
    for name, fn in fns:
        try:
            df = fn()
            if df is not None and len(df) > 0:
                log.info("board[%s] 使用 %s，%d 行", label, name, len(df))
                return df
        except Exception as e:  # noqa: BLE401
            log.warning("board[%s] %s 失败: %s", label, name, e)
    return None


def _pick(df, *names, default=None):
    for n in names:
        if n in df.columns:
            return df[n]
    return default if default is not None else pd.Series([pd.NA] * len(df), index=df.index)


def fetch_board_list() -> pd.DataFrame:
    import akshare as ak

    def ths():
        df = with_retry(ak.stock_board_industry_name_ths)
        return pd.DataFrame({
            "board_code": _pick(df, "code", "板块代码", "name").astype(str),
            "board_name": _pick(df, "name", "板块名称").astype(str),
        })

    def sina():
        df = with_retry(ak.stock_sector_spot, indicator="行业")
        return pd.DataFrame({
            "board_code": _pick(df, "label", "板块代码").astype(str),
            "board_name": _pick(df, "板块", "板块名称").astype(str),
        })

    def em():
        df = with_retry(ak.stock_board_industry_name_em)
        return pd.DataFrame({
            "board_code": _pick(df, "板块代码").astype(str),
            "board_name": _pick(df, "板块名称").astype(str),
        })

    out = _try([("ths", ths), ("sina", sina), ("em", em)], "list")
    if out is None:
        return pd.DataFrame(columns=NAME_COLUMNS)
    return out.dropna(subset=["board_name"]).drop_duplicates(subset=["board_name"])[NAME_COLUMNS]


def fetch_board_cons(board_name: str, board_code: str | None = None) -> pd.DataFrame:
    import akshare as ak

    def ths():
        df = with_retry(ak.stock_board_industry_cons_ths, symbol=board_name)
        return pd.DataFrame({
            "symbol": _pick(df, "代码", "code").astype(str).str.zfill(6),
            "name": _pick(df, "名称", "name").astype(str),
        })

    def sina():
        if not board_code:
            raise ValueError("缺 board_code")
        df = with_retry(ak.stock_sector_detail, sector=board_code)
        return pd.DataFrame({
            "symbol": _pick(df, "code", "代码").astype(str).str.zfill(6),
            "name": _pick(df, "名称", "name").astype(str),
        })

    out = _try([("ths", ths), ("sina", sina)], f"cons/{board_name}")
    if out is None:
        return pd.DataFrame(columns=CONS_COLUMNS)
    out = out[out["symbol"].str.len() == 6]
    out["board_name"] = board_name
    return out[CONS_COLUMNS]


def fetch_board_hist(board_name: str, period: str = "月k",
                     start_date: str = "20200101",
                     end_date: str = "20500101") -> pd.DataFrame:
    import akshare as ak

    def ths():
        df = with_retry(ak.stock_board_industry_index_ths, symbol=board_name,
                        start_date=start_date, end_date=end_date)
        close = _pick(df, "收盘价", "收盘", "close")
        dates = pd.to_datetime(_pick(df, "日期", "date"))
        out = pd.DataFrame({"date": dates, "close": pd.to_numeric(close, errors="coerce")})
        return out.dropna()

    def em():
        df = with_retry(ak.stock_board_industry_hist_em, symbol=board_name, period=period,
                        start_date=start_date, end_date=end_date)
        out = pd.DataFrame({"date": pd.to_datetime(_pick(df, "日期", "date")),
                            "close": pd.to_numeric(_pick(df, "收盘", "close"), errors="coerce")})
        return out.dropna()

    out = _try([("ths", ths), ("em", em)], f"hist/{board_name}")
    if out is None or len(out) == 0:
        return pd.DataFrame(columns=HIST_COLUMNS)
    m = out.set_index("date")["close"].resample("ME").last().dropna()
    res = pd.DataFrame({"date": m.index.strftime("%Y-%m"), "close": m.values,
                        "pct_change": (m.pct_change() * 100).values})
    res["board_name"] = board_name
    return res[HIST_COLUMNS]


def save_board_list(df: pd.DataFrame) -> None:
    write_parquet(df, "board_list.parquet")


def save_board_cons(board_name: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "board_cons"
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{board_name}.parquet", index=False)


def save_board_hist(board_name: str, df: pd.DataFrame) -> None:
    sub = RAW_DIR / "board_hist"
    sub.mkdir(parents=True, exist_ok=True)
    df.to_parquet(sub / f"{board_name}.parquet", index=False)
    log.info("board_hist %s %d 行", board_name, len(df))
