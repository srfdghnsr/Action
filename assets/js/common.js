/* common.js: 共享工具、状态栏、横幅、路由。依赖全局 echarts。 */
window.WB = window.WB || {};
WB.pages = WB.pages || {};
WB.DATA_BASE = "data/";

WB.loadJSON = async function (name) {
  const res = await fetch(WB.DATA_BASE + name + ".json", { cache: "no-store" });
  if (!res.ok) throw new Error("加载失败: " + name);
  return res.json();
};

WB.el = function (tag, attrs, children) {
  const e = document.createElement(tag);
  attrs = attrs || {};
  for (const k in attrs) {
    if (k === "class") e.className = attrs[k];
    else if (k === "html") e.innerHTML = attrs[k];
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), attrs[k]);
    else e.setAttribute(k, attrs[k]);
  }
  (children || []).filter((c) => c !== null && c !== undefined)
    .forEach((c) => {
      const isPrimitive = ["string", "number", "boolean"].includes(typeof c);
      e.appendChild(isPrimitive ? document.createTextNode(String(c)) : c);
    });
  return e;
};

WB.chart = function (domId, option) {
  const dom = document.getElementById(domId);
  if (!dom) return null;
  if (typeof echarts === "undefined") {
    dom.innerHTML = '<div class="loading">图表库加载失败（ECharts CDN 不可达）</div>';
    return null;
  }
  const inst = echarts.init(dom, null, { renderer: "canvas" });
  inst.setOption(option);
  window.addEventListener("resize", () => inst.resize());
  return inst;
};

WB.DARK = {
  textStyle: { color: "#c9d1d9" },
  backgroundColor: "transparent",
};

WB.axisDark = function () {
  return {
    axisLine: { lineStyle: { color: "#30363d" } },
    axisLabel: { color: "#8b949e" },
    splitLine: { lineStyle: { color: "#21262d" } },
  };
};

WB.setStatus = function (status, time) {
  const s = document.getElementById("status");
  const t = document.getElementById("updated");
  if (s) {
    s.textContent = status.text;
    s.className = "pill " + (status.ok ? "ok" : "warn");
  }
  if (t && time) t.textContent = "更新: " + time;
};
WB.setBanner = function (text) {
  const b = document.getElementById("banner");
  if (!b) return;
  if (text) { b.textContent = text; b.className = "show"; }
  else { b.className = ""; }
};
WB.setTitle = function (title) {
  const h = document.getElementById("page-title");
  if (h) h.textContent = title;
  document.querySelectorAll("#sidebar nav a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("data-page") === WB._cur);
  });
};

WB.kpi = function (value, label) {
  return WB.el("div", { class: "kpi" }, [
    WB.el("div", { class: "v" }, [String(value)]),
    WB.el("div", { class: "l" }, [label]),
  ]);
};

WB.start = function () {
  const route = function () {
    let page = location.hash.replace("#", "") || "overview";
    if (!WB.pages[page]) page = "overview";
    WB._cur = page;
    const fn = WB.pages[page];
    const root = document.getElementById("page-root");
    root.innerHTML = "";
    Promise.resolve(WB.loadJSON("meta"))
      .then((m) => {
        WB.setStatus({ text: m.status || "畅通", ok: m.ok !== false }, m.generated_at);
        WB.setBanner(m.banner || "");
      })
      .catch(() => {})
      .finally(() => {
        Promise.resolve()
          .then(() => fn(root))
          .catch((e) => {
            console.error(e);
            const msg = (e && (e.stack || e.message)) || String(e);
            root.innerHTML = '<div class="loading" style="white-space:pre-wrap;text-align:left">页面渲染失败:\n' +
              msg.replace(/</g, "&lt;") + "</div>";
          });
        WB.setTitle(({
          overview: "总览", market: "行情 · 牛股评估", backtest: "回测",
          analysis: "分析 · 分红/筹码", strategy: "实战 · 季节性/性价比", tools: "工具箱",
        })[page] || page);
      });
  };
  window.addEventListener("hashchange", route);
  route();
};
