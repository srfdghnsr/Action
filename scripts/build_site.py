"""build_site: 把 data/processed/*.json + assets + templates/index.html 组装为 dist/。

dist/ 为纯静态站点，可直接由 GitHub Pages 托管。无 akshare 依赖。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from io_utils import log, PROCESSED_DIR, DIST_DIR, ASSETS_DIR, TEMPLATES_DIR, PROJECT_ROOT

PAGE_TITLE = "A股全自动看板"


def build(version: str = "1.0.0") -> None:
    # 清理并重建 dist
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    (DIST_DIR / "data").mkdir(parents=True)

    # 复制静态资源
    shutil.copytree(ASSETS_DIR, DIST_DIR / "assets")

    # 复制数据 JSON
    copied = 0
    for f in sorted(PROCESSED_DIR.glob("*.json")):
        shutil.copy2(f, DIST_DIR / "data" / f.name)
        copied += 1

    # 复制首页模板
    shutil.copy2(TEMPLATES_DIR / "index.html", DIST_DIR / "index.html")

    log.info("build_site: 复制 %d 个数据文件 -> %s", copied, DIST_DIR / "data")
    log.info("build_site: 站点已生成于 %s", DIST_DIR)


def main():
    build()


if __name__ == "__main__":
    main()
