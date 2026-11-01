/* app.js: 各页面渲染与 ECharts 图表构造。依赖 common.js (WB) 与全局 echarts。 */
(function () {
  const A = WB.DARK, ax = WB.axisDark;

  function card(title, sub, bodyNode) {
    const c = WB.el("div", { class: "card" }, [WB.el("h3", {}, [title])]);
    if (sub) c.appendChild(WB.el("div", { class: "sub" }, [sub]));
    c.appendChild(bodyNode);
    return c;
  }
  function tags(list) {
    const span = WB.el("span", {});
    (list || []).forEach((t) => {
      const cls = /亏损|不足|未分红|风险|数据不足/.test(t) ? "bad" : (/正常|健康|集中/.test(t) ? "good" : "warn");
      span.appendChild(WB.el("span", { class: "tag " + cls }, [t]));
    });
    return span;
  }
  function table(headers, rows) {
    const t = WB.el("table", {});
    const thead = WB.el("thead", {}, [WB.el("tr", {}, headers.map((h) => WB.el("th", {}, [h])))]);
    t.appendChild(thead);
    const tb = WB.el("tbody", {});
    rows.forEach((r) => tb.appendChild(WB.el("tr", {}, r.map((c) => {
      // 已是 <td> 则直接复用，避免重复包裹
      return (c && c.tagName === "TD") ? c : WB.el("td", {}, [c]);
    }))));
    t.appendChild(tb);
    return t;
  }

  // ---------- 总览 ----------
  WB.pages.overview = async function (root) {
    const [sel, dq, pay, vm] = await Promise.all([
      WB.loadJSON("selectors").catch(() => ({ selected_count: 0 })),
      WB.loadJSON("dividend_quality").catch(() => ({ items: [], count: 0 })),
      WB.loadJSON("payback").catch(() => ({ median_payback_years: null, count: 0 })),
      WB.loadJSON("valuation_map").catch(() => ({ count: 0 })),
    ]);
    const avgDy = dq.items.length
      ? (dq.items.reduce((a, x) => a + (x.dividend_yield || 0), 0) / dq.items.length).toFixed(2)
      : "—";
    const kpis = WB.el("div", { class: "kpis" }, [
      WB.kpi(sel.selected_count, "牛股评估入选"),
      WB.kpi(avgDy + "%", "平均股息率"),
      WB.kpi(pay.median_payback_years != null ? pay.median_payback_years + " 年" : "—", "分红回本中位"),
      WB.kpi(vm.count, "估值样本"),
    ]);
    root.appendChild(kpis);
    const grid = WB.el("div", { class: "grid" });
    const entries = [
      ["行情 · 牛股评估", "优质牛股5条件打分选股", "market"],
      ["回测", "策略历史表现与显著性", "backtest"],
      ["分析 · 分红/筹码", "分红质量预警 + 估值分位 + 筹码分布", "analysis"],
      ["实战 · 季节性/性价比", "板块季节性 + 权益性价比气泡", "strategy"],
    ];
    entries.forEach(([t, s, p]) => {
      const body = WB.el("div", { class: "sub" }, [s]);
      const link = WB.el("a", { href: "#" + p, style: "color:var(--accent);font-size:13px;" }, ["进入 →"]);
      body.appendChild(link);
      grid.appendChild(card(t, "", body));
    });
    root.appendChild(grid);
    root.appendChild(WB.el("div", { class: "disclaimer", style: "margin-top:20px" },
      ["说明：本看板为数据驱动的辅助研究工具，所有信号与回测均为历史统计，不构成投资建议。样本外结论若无统计显著性会明确标注「仅观测」。"]));
  };

  // ---------- 行情 / 牛股评估 ----------
  WB.pages.market = async function (root) {
    const sel = await WB.loadJSON("selectors");
    const rows = (sel.selected || []).map((r) => {
      const s = r.signals;
      const mk = (b) => (b ? WB.el("span", { class: "signal-pass" }, ["✓"]) : WB.el("span", { class: "signal-fail" }, ["✗"]));
      return [
        WB.el("td", {}, [r.symbol]),
        WB.el("td", {}, [r.name || "—"]),
        WB.el("td", {}, [r.scores.mcap ? (r.scores.mcap / 1e8).toFixed(1) + "亿" : "—"]),
        WB.el("td", {}, [r.scores.listed_days != null ? r.scores.listed_days + "天" : "—"]),
        mk(s.rsi_cross), mk(s.above_m250), mk(s.mcap_ok), mk(s.age_ok), mk(s.not_st),
      ];
    });
    const head = ["代码", "名称", "市值", "上市天数", "RSI金叉", "站上m250", "市值区间", "上市>3500", "非ST"];
    root.appendChild(WB.el("div", { class: "sub" }, [`扫描 ${sel.total_scanned || 0} 只，入选 ${sel.selected_count || 0} 只。条件：月线RSI金叉 + 股价>m250 + 市值50-1000亿 + 上市>3500天 + 剔除ST。`]));
    root.appendChild(card("牛股评估入选列表", "", table(head, rows)));
  };

  // ---------- 回测 ----------
  WB.pages.backtest = async function (root) {
    let bt;
    try { bt = await WB.loadJSON("backtest"); }
    catch (e) { root.innerHTML = '<div class="loading">暂无回测数据（首次运行需抓取历史行情）。</div>'; return; }
    if (bt.error) { root.innerHTML = '<div class="loading">回测数据不足：' + bt.error + "</div>"; return; }
    const m = bt.metrics || {};
    const kpis = WB.el("div", { class: "kpis" }, [
      WB.kpi(((m.total_return || 0) * 100).toFixed(1) + "%", "累计收益"),
      WB.kpi(((m.annualized || 0) * 100).toFixed(1) + "%", "年化"),
      WB.kpi(((m.win_rate || 0) * 100).toFixed(1) + "%", "月胜率"),
      WB.kpi(((m.max_drawdown || 0) * 100).toFixed(1) + "%", "最大回撤"),
      WB.kpi((m.sharpe || 0).toFixed(2), "Sharpe"),
    ]);
    root.appendChild(kpis);
    const sig = bt.significance || "仅观测";
    root.appendChild(WB.el("div", { class: "sub", style: "color:var(--yellow)" },
      [`显著性判定：${sig}（样本外 ${bt.period ? bt.period.n_months : "?"} 个月，t=${bt.t_stat}, p=${bt.p_value}）`]));
    const line = card("策略 vs 基准 累计收益", (bt.period ? bt.period.start + " ~ " + bt.period.end : ""), WB.el("div", { class: "chart", id: "bt-chart" }));
    root.appendChild(line);
    const eq = bt.equity || [];
    WB.chart("bt-chart", {
      ...A,
      tooltip: { trigger: "axis" },
      legend: { data: ["策略", "基准"], textStyle: { color: "#c9d1d9" } },
      xAxis: { type: "category", data: eq.map((e) => e.date), ...ax() },
      yAxis: { type: "value", ...ax(), axisLabel: { formatter: (v) => (v * 100).toFixed(0) + "%" } },
      series: [
        { name: "策略", type: "line", showSymbol: false, data: eq.map((e) => e.strategy), lineStyle: { color: "#3fb950" }, itemStyle: { color: "#3fb950" } },
        { name: "基准", type: "line", showSymbol: false, data: eq.map((e) => e.benchmark), lineStyle: { color: "#58a6ff", type: "dashed" }, itemStyle: { color: "#58a6ff" } },
      ],
    });
    if (m.benchmark_total_return != null)
      root.appendChild(WB.el("div", { class: "sub" }, [`基准累计 ${(m.benchmark_total_return * 100).toFixed(1)}%，超额 ${(m.excess_return * 100).toFixed(1)}%，平均持仓 ${bt.avg_selected} 只。`]));
  };

  // ---------- 分析 / 分红 / 估值 / 筹码 ----------
  WB.pages.analysis = async function (root) {
    const [dq, vm, cyq] = await Promise.all([
      WB.loadJSON("dividend_quality").catch(() => ({ items: [] })),
      WB.loadJSON("valuation_map").catch(() => ({ points: [] })),
      WB.loadJSON("cyq").catch(() => ({ items: [] })),
    ]);
    // 分红质量表
    const dqRows = dq.items.slice(0, 60).map((x) => [
      WB.el("td", {}, [x.symbol]), WB.el("td", {}, [x.name || "—"]),
      WB.el("td", {}, [(x.dividend_yield || 0) + "%"]),
      WB.el("td", {}, [(x.payout_ratio || 0) + "%"]),
      WB.el("td", {}, [String(x.consecutive_years)]),
      WB.el("td", {}, [x.cashflow_cover != null ? x.cashflow_cover : "—"]),
      WB.el("td", {}, [tags(x.tags)]),
    ]);
    root.appendChild(card("分红质量预警", `共 ${dq.count || 0} 只`, table(["代码", "名称", "股息率", "派息率", "连续分红", "现金流覆盖", "标签"], dqRows)));

    // 估值分位气泡
    const sc = card("估值分位地图", "X=PE便宜分位(越高越便宜) Y=股息率(%) 大小=市值", WB.el("div", { class: "chart", id: "vm-chart" }));
    root.appendChild(sc);
    const pts = vm.points || [];
    WB.chart("vm-chart", {
      ...A, tooltip: { formatter: (p) => p.data.name + "<br/>便宜分位:" + (p.data.value[0] * 100).toFixed(0) + "%<br/>股息率:" + p.data.value[1] + "%" },
      xAxis: { name: "PE便宜分位", min: 0, max: 1, ...ax() },
      yAxis: { name: "股息率%", ...ax() },
      visualMap: { show: false, dimension: 0, min: 0, max: 1, inRange: { color: ["#f85149", "#d29922", "#3fb950"] } },
      series: [{
        type: "scatter", symbolSize: (v) => Math.max(6, Math.sqrt((v[2] || 0) / 1e9) * 1.2),
        data: pts.map((p) => ({ name: p.name, value: [p.pe_cheap_pct, p.div_yield, p.mcap || 0] })),
        itemStyle: { opacity: 0.75 },
      }],
    });

    // 筹码分布
    const cyqRows = (cyq.items || []).map((x) => [
      WB.el("td", {}, [x.symbol]), WB.el("td", {}, [x.name || "—"]),
      WB.el("td", {}, [x.profit_ratio + "%"]),
      WB.el("td", {}, [x.concentration_90 + "%"]),
      WB.el("td", {}, [tags([x.band, x.density, x.peak_migration])]),
      WB.el("td", {}, [x.stop_estimate != null ? x.stop_estimate : "—"]),
    ]);
    root.appendChild(card("筹码分布分析", `共 ${cyq.count || 0} 只 · 止损位=密集区下沿估算`, table(["代码", "名称", "获利比例", "90集中度", "判读/形态", "止损估算"], cyqRows)));
  };

  // ---------- 实战 / 季节性 / 性价比 ----------
  WB.pages.strategy = async function (root) {
    const [seas, attr] = await Promise.all([
      WB.loadJSON("seasonality").catch(() => ({ boards: {}, months: [] })),
      WB.loadJSON("attractiveness").catch(() => ({ points: [] })),
    ]);
    // 季节性热力
    const boards = Object.keys(seas.boards || {});
    const months = seas.months || [];
    const data = [];
    boards.forEach((b, yi) => {
      months.forEach((mo, xi) => {
        data.push([xi, yi, seas.boards[b][mo] != null ? seas.boards[b][mo] : 50]);
      });
    });
    root.appendChild(card("板块季节性热力图", "各自然月上涨占比(%)", WB.el("div", { class: "chart", id: "seas-chart" })));
    WB.chart("seas-chart", {
      ...A, tooltip: { formatter: (p) => boards[p.data[1]] + " " + months[p.data[0]] + "月: " + p.data[2] + "%" },
      grid: { height: "70%", top: 30 },
      xAxis: { type: "category", data: months.map((m) => m + "月"), ...ax() },
      yAxis: { type: "category", data: boards, ...ax() },
      visualMap: { min: 0, max: 100, calculable: true, orient: "horizontal", left: "center", bottom: 0,
        inRange: { color: ["#f85149", "#d29922", "#3fb950"] }, textStyle: { color: "#c9d1d9" } },
      series: [{ type: "heatmap", data, label: { show: false }, emphasis: { itemStyle: { borderColor: "#fff", borderWidth: 1 } } }],
    });

    // 性价比气泡
    root.appendChild(card("权益性价比气泡", "X=成本友好分位(PE便宜) Y=账面分位(PB便宜) 大小=市值", WB.el("div", { class: "chart", id: "attr-chart" })));
    const ap = attr.points || [];
    WB.chart("attr-chart", {
      ...A, tooltip: { formatter: (p) => p.data.name + "<br/>PE便宜:" + (p.data.value[0] * 100).toFixed(0) + "%<br/>PB便宜:" + (p.data.value[1] * 100).toFixed(0) + "%<br/>股息率:" + (p.data.value[2] * 100).toFixed(2) + "%" },
      xAxis: { name: "PE便宜分位", min: 0, max: 1, ...ax() },
      yAxis: { name: "PB便宜分位", min: 0, max: 1, ...ax() },
      visualMap: { show: false, dimension: 2, min: 0, max: 0.06, inRange: { color: ["#58a6ff", "#3fb950", "#d29922"] } },
      series: [{
        type: "scatter", symbolSize: (v) => Math.max(6, Math.sqrt((v[3] || 0) / 1e9) * 1.2),
        data: ap.map((p) => ({ name: p.name, value: [p.cost_friendly_pct, p.book_pct, p.div_yield, p.mcap || 0] })),
        itemStyle: { opacity: 0.75 },
      }],
    });
  };

  // ---------- 工具箱 ----------
  WB.pages.tools = async function (root) {
    let meta = {};
    try { meta = await WB.loadJSON("meta"); } catch (e) {}
    root.appendChild(card("参数与免责", "", (function () {
      const box = WB.el("div", { class: "disclaimer" });
      box.innerHTML =
        "<p><b>回测口径：</b>月末调仓、等权持有、无未来函数（指标按月末 as-of 取值）；训练/验证/样本外三段划分，样本外仅报告不调参。统计不显著时标注「仅观测」。</p>" +
        "<p><b>数据来源：</b>AKShare（东方财富 / 百度股市通 / 新浪），由 GitHub Actions 每日收盘后自动抓取并更新本页。</p>" +
        "<p><b>风险披露：</b>本看板为量化研究辅助工具，所有信号、评分、回测均为历史数据统计，<b>不构成任何投资建议</b>，亦不涉及真实交易下单。市场有风险，决策需谨慎。</p>" +
        "<p><b>版本：</b>" + (meta.version || "1.0.0") + " · 生成时间 " + (meta.generated_at || "—") + "</p>";
      return box;
    })()));
    root.appendChild(WB.el("div", { class: "sub", style: "margin-top:14px" },
      ["自定义观察池与阈值请在仓库 config/ 下调整（watchlist.json / settings.json），下次自动运行即生效。"]));
  };

  WB.start();
})();
