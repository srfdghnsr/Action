"""build_site: 把 data/processed/*.json + assets + templates/index.html 组装为 dist/。

dist/ 为纯静态站点，可直接由 GitHub Pages 托管。无 akshare 依赖。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from io_utils import log, PROCESSED_DIR, DIST_DIR, ASSETS_DIR, TEMPLATES_DIR, PROJECT_ROOT

PAGE_TITLE = "AlphaMaster 量化因子挖掘中心"


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

    # 复制首页模板（并把 <title> 统一替换为 PAGE_TITLE，品牌名只在一处维护）
    html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<title>.*?</title>", f"<title>{PAGE_TITLE}</title>", html, count=1, flags=re.S)
    (DIST_DIR / "index.html").write_text(html, encoding="utf-8")

    log.info("build_site: 复制 %d 个数据文件 -> %s", copied, DIST_DIR / "data")
    log.info("build_site: 站点已生成于 %s", DIST_DIR)


def main():
    build()


if __name__ == "__main__":
    main()
