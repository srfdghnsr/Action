"""_http: 统一重试 / 超时 / 多源回退封装。

对 akshare 调用做指数退避 + 抖动重试，避免偶发网络抖动导致整个流水线失败。
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable

log = logging.getLogger("ashare")

DEFAULT_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 12.0


def with_retry(
    func: Callable[..., Any],
    *args,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs,
) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt == retries - 1:
                break
            delay = min(max_delay, base_delay * (2 ** attempt)) + random.uniform(0, 0.6)
            log.warning("重试 %d/%d [%s]: %s", attempt + 1, retries, getattr(func, "__name__", "?"), e)
            time.sleep(delay)
    raise last if last else RuntimeError("with_retry: unknown failure")


def safe_call(func: Callable[..., Any], default=None, *args, **kwargs):
    """非关键调用：失败返回 default，不中断流水线。"""
    try:
        return with_retry(func, *args, **kwargs)
    except Exception as e:  # noqa: BLE001
        log.warning("safe_call 跳过 [%s]: %s", getattr(func, "__name__", "?"), e)
        return default
