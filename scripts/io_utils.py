"""io_utils: 路径、配置、日志、parquet/json 读写、schema 校验。

所有脚本共享的底层工具。无任何 akshare 依赖，可离线导入与单测。
安装方式：run_all.py 会把 scripts/ 加入 sys.path，模块统一用 `from io_utils import ...`。
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# ---- 路径 ----
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
CONFIG_DIR = PROJECT_ROOT / "config"
DIST_DIR = PROJECT_ROOT / "dist"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
ASSETS_DIR = PROJECT_ROOT / "assets"

for d in (RAW_DIR, PROCESSED_DIR, SNAPSHOT_DIR, DIST_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ---- 日志 ----
def get_logger(name: str = "ashare") -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=False,
    )
    return logging.getLogger(name)


log = get_logger()


# ---- 配置 ----
def load_settings() -> dict:
    path = CONFIG_DIR / "settings.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_config(name: str) -> dict:
    path = CONFIG_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---- parquet / json ----
def write_parquet(df: pd.DataFrame, name: str, subdir: str = "") -> Path:
    base = RAW_DIR if subdir.startswith("raw") else (PROCESSED_DIR if subdir.startswith("proc") else RAW_DIR)
    target = (RAW_DIR / subdir) if subdir and not subdir.startswith("proc") else (PROCESSED_DIR / subdir.lstrip("proc/") if subdir.startswith("proc") else RAW_DIR)
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    df.to_parquet(path, index=False)
    return path


def read_parquet(name: str, subdir: str = "") -> pd.DataFrame:
    if subdir.startswith("proc"):
        target = PROCESSED_DIR / subdir.lstrip("proc/")
    elif subdir:
        target = RAW_DIR / subdir
    else:
        target = RAW_DIR
    return pd.read_parquet(target / name)


def write_json(obj: Any, name: str) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=_default)
    return path


def read_json(name: str) -> Any:
    path = PROCESSED_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _default(o):
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, (pd.Timedelta,)):
        return str(o)
    return str(o)


# ---- schema 校验 ----
def schema_check(df: pd.DataFrame, required_cols: list[str], name: str) -> pd.DataFrame:
    """校验 akshare 返回列是否漂移；缺失则抛错由上层兜底。"""
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"[schema_check] {name} 缺失列: {missing}；实际列: {list(df.columns)}")
    return df


def safe_div(a: float, b: float) -> float:
    try:
        return a / b if b else 0.0
    except Exception:
        return 0.0
