"""board: 行业板块列表 / 成分 / 月度行情（季节性、性价比用）。"""
from __future__ import annotations

import pandas as pd
from io_utils import log, write_parquet, RAW_DIR
from ._http import with_retry

NAME_COLUMNS = ["板块代码", "板块名称"]
CONS_COLUMNS = ["代码", "名称"]
HIST_COLUMNS = ["日期", "收盘", "涨跌幅"]


def fetch_board_list() -> pd.DataFrame:
    import akshare as ak
    df = with_retry(ak.stock_board_industry_name_em)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=NAME_COLUMNS)
    df = df.rename(columns={"板块代码": "board_code", "板块名称": "board_name"})
    return df[["board_code", "board_name"]]


def fetch_board_cons(board_name: str) -> pd.DataFrame:
    import akshare as ak
    df = with_retry(ak.stock_board_industry_cons_em, symbol=board_name)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=CONS_COLUMNS)
    df = df.rename(columns={"代码": "symbol", "名称": "name"})
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    df["board_name"] = board_name
    return df[["board_name", "symbol", "name"]]


def fetch_board_hist(board_name: str, period: str = "月k",
                     start_date: str = "20200101",
                     end_date: str = "20500101") -> pd.DataFrame:
    import akshare as ak
    df = with_retry(ak.stock_board_industry_hist_em, symbol=board_name,
                    period=period, start_date=start_date, end_date=end_date)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=HIST_COLUMNS)
    df = df.rename(columns={"日期": "date", "收盘": "close", "涨跌幅": "pct_change"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    df["board_name"] = board_name
    return df[["board_name", "date", "close", "pct_change"]]


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
