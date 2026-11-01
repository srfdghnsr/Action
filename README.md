# A股全自动看板 (srfdghnsr/Action)

一个**完全托管在 GitHub、每日收盘后自动更新**的 A 股量化研究看板。GitHub Actions 定时抓取行情/财务/筹码数据 → Python 计算四大模块指标与回测 → 生成纯静态 ECharts 深色站点 → 自动部署 GitHub Pages。

> 本项目为数据驱动的**研究辅助工具**，所有信号/评分/回测均为历史统计，**不构成投资建议**，不涉及真实交易下单。

---

## 功能模块

| 模块 | 内容 | 对应页面 |
|---|---|---|
| **优质牛股评估** | 月线 RSI 金叉 + 股价>m250 + 市值 50–1000 亿 + 上市>3500 天 + 剔除 ST，五条件打分选股 | 行情 · 牛股评估 |
| **分红质量 + 估值分位** | 分红质量预警（股息率/派息率/现金流覆盖/连续分红）、估值分位气泡（PE 便宜分位 × 股息率）、分红回本年限 | 分析 · 分红/筹码 |
| **筹码分布** | 获利比例判读、90% 成本集中度、主峰迁移 4 形态、密集区下沿止损估算 | 分析 · 分红/筹码 |
| **板块季节性 + 性价比 + 回测** | 行业×月份上涨占比热力图、权益性价比气泡、策略 vs 基准收益曲线 | 实战 / 回测 |

左侧导航：总览 / 行情 / 回测 / 分析 / 实战 / 工具箱。顶部显示数据更新时间与状态（畅通 / 数据延迟）。

---

## 技术栈

- **生成端**：Python 3.11 + `akshare==1.18.91`、pandas、numpy、pyarrow（技术指标手算，不依赖 talib）
- **前端**：原生 HTML + ECharts 5（已 vendored 到 `assets/js/echarts.min.js`，无 CDN 依赖）+ 原生 JS，无构建步骤
- **部署**：GitHub Actions（cron UTC 08:30，即北京时间 16:30）+ GitHub Pages

---

## 目录结构

```
.
├── .github/workflows/build-deploy.yml   # 定时抓取→计算→构建→部署（含失败兜底）
├── config/
│   ├── settings.json                    # 阈值参数（RSI/市值/上市天数/holdout 等）
│   ├── watchlist.json                   # 自定义观察池（额外纳入筹码/估值分析）
│   └── industry_map.json                # 板块名称→标准化行业映射
├── scripts/
│   ├── run_all.py                       # 总编排（live / --seed-mock / --use-cache / --push-cache）
│   ├── io_utils.py                      # 路径/配置/IO/schema 校验
│   ├── build_site.py                    # 组装 dist/
│   ├── fetch/                           # 数据抓取层（akshare 懒加载）
│   │   ├── universe.py history.py info.py fundamental.py valuation.py cyq.py board.py
│   │   ├── _http.py                     # 指数退避重试
│   │   └── mock.py                      # 离线示例数据生成
│   └── compute/                         # 指标计算层（纯函数，可离线单测）
│       ├── indicators.py selectors.py dividend_quality.py valuation_map.py payback.py
│       ├── cyq_analysis.py seasonality.py attractiveness.py backtest.py
│       └── run_compute.py
├── templates/index.html                 # 页面骨架
├── assets/                              # css + js + echarts
├── tests/                               # 离线单测（fixtures 手搓）
├── requirements.txt
└── dist/                                # 构建产物（gitignore，由 Actions 生成并部署）
```

---

## 本地运行

```bash
# 1) 安装依赖（建议 Python 3.11）
pip install -r requirements.txt

# 2) 离线示例数据预览（不需网络/akshare，生成到 dist/）
python scripts/run_all.py --seed-mock

# 3) 本地起静态服务器查看
python -m http.server 8765 --directory dist
# 浏览器打开 http://127.0.0.1:8765
```

> `--seed-mock` 生成的是**合成示例数据**（页面顶部有"示例数据"横幅），仅用于演示界面与验证逻辑，非真实行情。

真实抓取（需可访问东方财富/百度股市通，境外服务器可能偶发失败）：

```bash
python scripts/run_all.py            # 抓取→计算→构建
python scripts/run_all.py --force    # 忽略交易日校验强制抓取
```

---

## 参数说明（`config/settings.json`）

| 字段 | 含义 | 默认 |
|---|---|---|
| `selector.mcap_min/max` | 总市值区间（元） | 50 亿 / 1000 亿 |
| `selector.min_listed_days` | 上市天数下限 | 3500 |
| `selector.rsi_window` | 月线 RSI 窗口 | 14 |
| `selector.m250_window` | 日线均线窗口 | 250 |
| `cyq.max_symbols` | 筹码分析标的数上限（重接口） | 200 |
| `pipeline.max_scan` | 单轮扫描候选上限（控制 Actions 时长） | 180（链路确认后可回 600） |
| `pipeline.workers` | 候选抓取并发线程数 | 6（遇限速降到 4） |
| `pipeline.time_budget_min` | 候选抓取时间预算，超时优雅收尾并标注"部分数据" | 55 |
| `pipeline.cyq_budget_min` / `board_budget_min` | 筹码 / 板块各自预算 | 12 / 8 |
| `backtest.train/valid/holdout_*` | 回测三段划分 | 2015–2020 / 2021–2023 / 2024– |
| `backtest.min_trades_for_sig` | 判定统计显著的最小样本 | 30 |
| `schedule.cron_utc` | Actions 定时（UTC） | `30 8 * * 1-5` |

自定义观察池：编辑 `config/watchlist.json` 的 `watchlist` 数组（6 位代码）。

---

## GitHub 部署（已完成，仅记录流程）

线上仓库：**https://github.com/srfdghnsr/Action** · 看板地址：**https://srfdghnsr.github.io/Action/**

1. 公开仓库 `srfdghnsr/Action`（建仓时附带 MIT LICENSE）。
2. 本地推送（若默认 TLS 走不通，加 `git config http.sslBackend openssl`）：
   ```bash
   git remote add origin https://github.com/srfdghnsr/Action.git
   git branch -M main
   git fetch origin main && git rebase origin/main   # 保留远端 LICENSE
   git push -u origin main
   ```
3. Pages：工作流内 `actions/configure-pages` 会尝试自动开通（`enablement: true`）；
   若被权限拒绝，仓库 **Settings → Pages → Source = GitHub Actions** 手动选一次。
4. 首次推送即自动触发（`on.push`）；日常可 **Actions → build-deploy → Run workflow** 手动强制抓取
   （手动触发会带 `--force`，忽略交易日判断）。
5. 之后每个交易日北京时间 16:30 自动更新（GitHub cron 可能有几分钟延迟）。

### 失败兜底机制

实时抓取失败时，工作流按两级兜底，保证 **Pages 始终可访问**：

1. 有 `data-cache` 快照 → `git checkout origin/data-cache -- data/processed` 复用最近一次成功数据重建，
   页面顶部显示"数据延迟"横幅；
2. 无快照（首次运行）→ `--seed-mock` 生成示例数据，横幅明示"示例数据（非实时）"，绝不白屏假装成功。

---

## 回测口径（诚实优先）

- **无未来函数**：指标在全序列计算后按月末 as-of 取值（RSI/MA 均为因果指标），成交价为区间收盘价，杜绝前视。
- **三段划分**：训练（2015–2020）/ 验证（2021–2023）/ 样本外（2024–），样本外仅报告不调参。
- **显著性**：样本外月份数 < 30 或 t 检验 p > 0.05 时，前端明确标注"仅观测，不具统计显著"。
- **已知近似**：历史市值用「最新市值 ÷ 最新价 × 历史价」回推股本；筹码止损位为密集区下沿的模型估算。

---

## 数据源与局限

### 数据源换源说明（重要，勿改回东财全市场快照）

2026-11-01 在 GitHub 美国 runner 上实测（`scripts/probe_sources.py`，结果自动贴成 issue）：

| 接口 | 境外可用性 | 本项目用法 |
|---|---|---|
| `stock_zh_a_spot_em`（东财全市场快照） | ❌ `RemoteDisconnected` | **改用腾讯批量行情** `qt.gtimg.cn`（自带总市值/PE/PB） |
| `stock_board_industry_name_em` / `index_zh_a_hist` | ❌ 同上 | 板块改**同花顺 → 新浪行业**；指数改 `stock_zh_index_daily`(sina) |
| `stock_zh_a_hist`（东财个股日线） | ⚠️ 偶发断连 | 日线改 **sina `stock_zh_a_daily`(qfq) → 腾讯 → 东财** 三级降级 |
| 财务摘要 / 分红 / 筹码 / 百度估值 | ✅（偶发抖动） | 保留东财与百度，逐标的 try/except 容错 |

- 月线由日线本地重采样（`history.to_monthly`），每标的只请求一次日线。
- 腾讯行情字段位（88 字段）：`1=名称 2=代码 3=现价 39=PE 44=流通市值(亿) 45=总市值(亿) 46=PB`。
- 筹码接口（`stock_cyq_em` / `stock_cyq_cottle`）较重，仅对候选子集 + watchlist（≤200）运行，并受 `cyq_budget_min` 约束。
- 分红/财务数据存在披露滞后与缺失，缺失字段会降级显示为"—"或标注"数据不足"。
- 首次真实抓取若失败，工作流会自动开 issue 贴日志尾部，便于排查（`.github/workflows/build-deploy.yml` 的 Report failure 步骤）。

---

## 免责声明

本项目仅供学习与研究使用。所有指标、评分、信号与回测结果均基于历史公开数据，不代表未来表现，**不构成任何投资建议**。据此操作，风险自负。
