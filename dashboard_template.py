"""
Shared HTML/CSS/JS template for the NWSL analytics dashboard: a single
self-contained, tabbed, interactive page combining every chart built so far.
No CDN dependencies (learned the hard way -- see README) -- pure vanilla
SVG + JS, so it also works fully offline once generated.

This is the natural stepping stone toward a real webapp: it's already a
client-side single-page app. The jump from here to "deployed webapp" is
mostly: (1) swap the embedded JSON for a live fetch, (2) host the file
somewhere. See the README's "From dashboard to webapp" section.
"""

import json

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Karla:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --series-1: #2a78d6;
    --series-1-dark: #1c5cab;
    --series-1-ink: #ffffff;
    --red: #e34948;
    --font-body: 'Karla', system-ui, -apple-system, "Segoe UI", sans-serif;
    --font-head: 'Space Grotesk', system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: var(--font-body); background: var(--page); color: var(--text-primary); }}
  .app {{ max-width: 960px; margin: 0 auto; padding: 28px 24px 48px; text-align: left; }}
  .app-header h1 {{ font-family: var(--font-head); font-weight: 500; font-size: 21px; margin: 0 0 4px; }}
  .app-header p {{ font-size: 13px; color: var(--text-secondary); margin: 0 0 20px; max-width: 660px; }}
  .tabs {{ display: flex; gap: 6px; flex-wrap: wrap; border-bottom: 1px solid var(--grid); margin-bottom: 20px; }}
  .tab-btn {{
    appearance: none; border: none; background: none; padding: 9px 14px; font-family: var(--font-body); font-size: 13px;
    font-weight: 700; color: var(--text-muted); cursor: pointer; border-radius: 8px 8px 0 0;
    position: relative; top: 1px;
  }}
  .tab-btn:hover {{ color: var(--text-primary); }}
  .tab-btn.active {{ color: var(--series-1); border-bottom: 2px solid var(--series-1); }}
  .panel {{ display: none; background: var(--surface-1); border-radius: 12px; padding: 20px 24px 24px; text-align: left; }}
  .panel.active {{ display: block; }}
  .panel .kicker {{ font-family: var(--font-body); font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); margin: 0 0 6px; }}
  .panel h2 {{ font-family: var(--font-head); font-weight: 500; font-size: 18px; margin: 0 0 6px; line-height: 1.35; max-width: 640px; }}
  .panel .blurb {{ font-size: 12.5px; color: var(--text-secondary); margin: 0 0 16px; max-width: 640px; }}
  .panel select {{
    font-family: var(--font-body); font-size: 13px; font-weight: 500; color: var(--text-primary);
    background: var(--surface-1); border: 1px solid var(--baseline); border-radius: 6px;
    padding: 7px 10px; cursor: pointer;
  }}
  .picker-label {{ font-size: 11.5px; color: var(--text-muted); margin: 0 0 4px; }}
  .picker-row {{ display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-end; margin-bottom: 4px; }}
  .picker-group {{ display: flex; flex-direction: column; }}
  .compare-caption {{ font-size: 12.5px; color: var(--text-primary); font-weight: 500; margin-top: 14px; }}
  .axis line {{ stroke: var(--baseline); }}
  .axis text {{ fill: var(--text-muted); font-size: 11px; }}
  .gridline {{ stroke: var(--grid); stroke-width: 1px; }}
  .axis-label {{ fill: var(--text-secondary); font-size: 12px; }}
  .bar {{ fill: var(--series-1); }}
  .bar.negative {{ fill: var(--red); }}
  .bar.muted {{ fill: var(--baseline); }}
  .bar:hover {{ opacity: 0.85; cursor: pointer; }}
  .bar-label {{ fill: var(--text-primary); font-size: 11px; }}
  .bar-label.muted {{ fill: var(--text-muted); }}
  .bar-value {{ fill: var(--text-secondary); font-size: 10.5px; }}
  .annotation {{ fill: var(--text-primary); font-size: 11.5px; font-weight: 600; }}
  .bubble {{ fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2px; cursor: pointer; }}
  .bubble.muted {{ fill: var(--baseline); }}
  .bubble:hover, .bubble.hover {{ fill: var(--series-1-dark); }}
  .badge-text {{ fill: var(--series-1-ink); font-size: 9.5px; font-weight: 600; text-anchor: middle; pointer-events: none; }}
  .badge-text.muted {{ fill: var(--text-secondary); }}
  .refline {{ stroke: var(--baseline); stroke-width: 1px; stroke-dasharray: 4 3; }}
  .tooltip {{
    position: absolute; pointer-events: none; background: var(--text-primary); color: #fff;
    padding: 8px 10px; border-radius: 6px; font-size: 12px; line-height: 1.5; opacity: 0;
    transition: opacity 0.1s ease; box-shadow: 0 4px 14px rgba(0,0,0,0.18); max-width: 230px; z-index: 10;
  }}
  .tooltip .name {{ font-weight: 600; margin-bottom: 2px; }}
  .tooltip .row {{ color: #d8d8d4; }}
  .footnote {{ font-size: 11px; color: var(--text-muted); margin-top: 14px; }}
  .legend {{ display: flex; gap: 16px; font-size: 11.5px; color: var(--text-secondary); margin-bottom: 10px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-swatch {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
</style>
</head>
<body>
<div class="app">
  <div class="app-header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="tabs" id="tabs"></div>
  <div id="panels"></div>
</div>
<div class="tooltip" id="tooltip"></div>
<script>
const CHARTS = {charts_json};

// ---------- tiny chart-drawing library (no dependencies) ----------
const svgNS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {{
  const e = document.createElementNS(svgNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}}
function niceStep(maxVal, targetTicks) {{
  const raw = maxVal / targetTicks;
  const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  return step;
}}
function ticksFor(minVal, maxVal, targetTicks) {{
  const step = niceStep(maxVal - minVal, targetTicks);
  const out = [];
  const start = Math.ceil(minVal / step) * step;
  for (let t = start; t <= maxVal + 1e-6; t += step) out.push(Math.round(t * 1000) / 1000);
  return out;
}}
const tooltip = document.getElementById("tooltip");

function showTooltip(html, event) {{
  tooltip.innerHTML = html;
  tooltip.style.opacity = 1;
  moveTooltip(event);
}}
function moveTooltip(event) {{
  tooltip.style.left = (event.pageX + 14) + "px";
  tooltip.style.top = (event.pageY - 10) + "px";
}}
function hideTooltip() {{ tooltip.style.opacity = 0; }}

function drawDivergingBar(container, cfg) {{
  const data = [...cfg.data].sort((a, b) => a.value - b.value);
  const longestLabel = Math.max(...data.map(d => d.label.length));
  const margin = {{top: 8, right: 30, bottom: 34, left: Math.max(90, longestLabel * 6.5 + 12)}};
  const width = 820 - margin.left - margin.right;
  const rowH = 26;
  const height = data.length * rowH;
  const svg = el("svg", {{width: width + margin.left + margin.right, height: height + margin.top + margin.bottom}});
  const g = el("g", {{transform: `translate(${{margin.left}},${{margin.top}})`}});
  svg.appendChild(g);
  container.appendChild(svg);

  const maxAbs = Math.max(...data.map(d => Math.abs(d.value))) * 1.15 || 1;
  const x = v => (v / maxAbs) * (width / 2) + width / 2;
  const zeroX = x(0);

  ticksFor(-maxAbs, maxAbs, 6).forEach(t => {{
    g.appendChild(el("line", {{class: "gridline", x1: x(t), x2: x(t), y1: -4, y2: height + 4}}));
    const label = el("text", {{class: "axis-label", x: x(t), y: height + 20, "text-anchor": "middle"}});
    label.textContent = t;
    g.appendChild(label);
  }});
  g.appendChild(el("line", {{x1: zeroX, x2: zeroX, y1: -4, y2: height + 4, stroke: "var(--baseline)", "stroke-width": 1}}));

  const hasHighlight = data.some(d => d.highlight);

  data.forEach((d, i) => {{
    const y = i * rowH + 4;
    const barW = Math.abs(x(d.value) - zeroX);
    const barX = d.value < 0 ? x(d.value) : zeroX;
    const isMuted = hasHighlight && !d.highlight;
    const rect = el("rect", {{
      class: "bar" + (isMuted ? " muted" : (d.value < 0 ? " negative" : "")),
      x: barX, y: y, width: Math.max(barW, 1), height: rowH - 8, rx: 3,
    }});
    rect.addEventListener("mouseenter", (event) => showTooltip(
      `<div class="name">${{d.label}}</div><div class="row">${{cfg.valueLabel}}: ${{d.value.toFixed(2)}}</div>`, event));
    rect.addEventListener("mousemove", moveTooltip);
    rect.addEventListener("mouseleave", hideTooltip);
    g.appendChild(rect);

    const label = el("text", {{class: "bar-label" + (isMuted ? " muted" : ""), x: -8, y: y + (rowH - 8) / 2 + 4, "text-anchor": "end"}});
    label.textContent = d.label;
    g.appendChild(label);

    if (d.highlight) {{
      const sign = d.value >= 0 ? "+" : "";
      const annoX = x(d.value) + (d.value < 0 ? -8 : 8);
      const anno = el("text", {{
        class: "annotation", x: annoX, y: y + (rowH - 8) / 2 + 4,
        "text-anchor": d.value < 0 ? "end" : "start",
      }});
      anno.textContent = sign + d.value.toFixed(1) + (cfg.annotationSuffix || "");
      g.appendChild(anno);
    }}
  }});

  const xLabel = el("text", {{class: "axis-label", x: width / 2, y: height + 34, "text-anchor": "middle"}});
  xLabel.textContent = cfg.xAxisLabel || "";
  g.appendChild(xLabel);
}}

function resolveCollisions(points, r, padding) {{
  const minDist = r * 2 + padding;
  for (let iter = 0; iter < 300; iter++) {{
    let moved = false;
    for (let i = 0; i < points.length; i++) {{
      for (let j = i + 1; j < points.length; j++) {{
        const a = points[i], b = points[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 0.01) {{ dx = (Math.random() - 0.5); dy = (Math.random() - 0.5); dist = 0.01; }}
        if (dist < minDist) {{
          const push = (minDist - dist) / 2;
          const ux = dx / dist, uy = dy / dist;
          a.x -= ux * push; a.y -= uy * push;
          b.x += ux * push; b.y += uy * push;
          moved = true;
        }}
      }}
    }}
    if (!moved) break;
  }}
  return points;
}}

function drawScatter(container, cfg) {{
  const margin = {{top: 12, right: 24, bottom: 46, left: 58}};
  const width = 780 - margin.left - margin.right;
  const height = (cfg.height || 520) - margin.top - margin.bottom;
  const R = cfg.radius || 16;

  const svg = el("svg", {{width: width + margin.left + margin.right, height: height + margin.top + margin.bottom}});
  const g = el("g", {{transform: `translate(${{margin.left}},${{margin.top}})`}});
  svg.appendChild(g);
  container.appendChild(svg);

  const xMax = Math.max(...cfg.data.map(d => d.x)) * 1.15;
  const yMax = Math.max(...cfg.data.map(d => d.y)) * 1.15;
  const xScale = v => (v / xMax) * width;
  // invertY: plot higher values lower on screen (useful when "lower is better",
  // e.g. xG Against, so "up" reads as "good" on both axes at once)
  const yScale = cfg.invertY ? (v => (v / yMax) * height) : (v => height - (v / yMax) * height);

  ticksFor(0, xMax, 8).forEach(t => g.appendChild(el("line", {{class: "gridline", x1: xScale(t), x2: xScale(t), y1: 0, y2: height}})));
  ticksFor(0, yMax, 8).forEach(t => g.appendChild(el("line", {{class: "gridline", x1: 0, x2: width, y1: yScale(t), y2: yScale(t)}})));

  const xAxis = el("g", {{class: "axis", transform: `translate(0,${{height}})`}});
  ticksFor(0, xMax, 8).forEach(t => {{
    const txt = el("text", {{x: xScale(t), y: 18, "text-anchor": "middle"}}); txt.textContent = t; xAxis.appendChild(txt);
  }});
  xAxis.appendChild(el("line", {{x1: 0, x2: width, y1: 0, y2: 0}}));
  g.appendChild(xAxis);

  const yAxis = el("g", {{class: "axis"}});
  ticksFor(0, yMax, 8).forEach(t => {{
    const txt = el("text", {{x: -10, y: yScale(t) + 4, "text-anchor": "end"}}); txt.textContent = t; yAxis.appendChild(txt);
  }});
  yAxis.appendChild(el("line", {{x1: 0, x2: 0, y1: 0, y2: height}}));
  g.appendChild(yAxis);

  const xLabel = el("text", {{class: "axis-label", x: width / 2, y: height + 38, "text-anchor": "middle"}}); xLabel.textContent = cfg.xAxisLabel; g.appendChild(xLabel);
  const yLabel = el("text", {{class: "axis-label", transform: "rotate(-90)", x: -height / 2, y: -40, "text-anchor": "middle"}}); yLabel.textContent = cfg.yAxisLabel; g.appendChild(yLabel);

  if (cfg.refLine) {{
    const lim = Math.min(xMax, yMax);
    g.appendChild(el("line", {{class: "refline", x1: xScale(0), y1: yScale(0), x2: xScale(lim), y2: yScale(lim)}}));
  }}
  if (cfg.medianLines) {{
    const medX = cfg.data.map(d => d.x).sort((a,b) => a-b)[Math.floor(cfg.data.length / 2)];
    const medY = cfg.data.map(d => d.y).sort((a,b) => a-b)[Math.floor(cfg.data.length / 2)];
    g.appendChild(el("line", {{class: "refline", x1: xScale(medX), x2: xScale(medX), y1: 0, y2: height}}));
    g.appendChild(el("line", {{class: "refline", x1: 0, x2: width, y1: yScale(medY), y2: yScale(medY)}}));
  }}

  // true data positions, then nudge apart only enough to stop overlap
  const points = cfg.data.map(d => ({{x: xScale(d.x), y: yScale(d.y), d}}));
  resolveCollisions(points, R, 3);

  const hasHighlight = cfg.data.some(d => d.highlight);

  points.forEach(p => {{
    const d = p.d;
    const isMuted = hasHighlight && !d.highlight;
    const dx = p.x - xScale(d.x), dy = p.y - yScale(d.y);
    const displaced = Math.sqrt(dx * dx + dy * dy) > 3;
    const node = el("g", {{class: "player-node", transform: `translate(${{p.x}},${{p.y}})`}});
    if (displaced) {{
      // faint leader line back to the true data position when nudged for legibility
      node.appendChild(el("line", {{
        x1: 0, y1: 0, x2: xScale(d.x) - p.x, y2: yScale(d.y) - p.y,
        stroke: "var(--baseline)", "stroke-width": 1, "stroke-dasharray": "2 2",
      }}));
    }}
    const circle = el("circle", {{class: "bubble" + (isMuted ? " muted" : ""), r: R}});
    const label = el("text", {{class: "badge-text" + (isMuted ? " muted" : ""), dy: "0.32em", "text-anchor": "middle"}});
    label.textContent = d.badge;
    node.appendChild(circle);
    node.appendChild(label);

    if (d.highlight && d.annotation) {{
      const estTextWidth = d.annotation.length * 6.4;
      const anchorRight = (p.x + R + 8 + estTextWidth) < width;
      const anno = el("text", {{
        class: "annotation", x: anchorRight ? R + 8 : -(R + 8), y: 4,
        "text-anchor": anchorRight ? "start" : "end",
      }});
      anno.textContent = d.annotation;
      node.appendChild(anno);
    }}

    g.appendChild(node);

    node.addEventListener("mouseenter", (event) => {{
      circle.classList.add("hover");
      showTooltip(d.tooltip, event);
    }});
    node.addEventListener("mousemove", moveTooltip);
    node.addEventListener("mouseleave", () => {{ circle.classList.remove("hover"); hideTooltip(); }});
  }});
}}

function drawTeamCompare(container, cfg) {{
  const pickerRow = document.createElement("div");
  pickerRow.className = "picker-row";

  const teamGroup = document.createElement("div");
  teamGroup.className = "picker-group";
  const teamLabel = document.createElement("div");
  teamLabel.className = "picker-label";
  teamLabel.textContent = "Team";
  const teamSelect = document.createElement("select");
  Object.keys(cfg.rosters).sort((a, b) => {{
    const nameA = (cfg.teamNames && cfg.teamNames[a]) || a;
    const nameB = (cfg.teamNames && cfg.teamNames[b]) || b;
    return nameA.localeCompare(nameB);
  }}).forEach(abbr => {{
    const opt = el2("option", {{value: abbr}});
    opt.textContent = (cfg.teamNames && cfg.teamNames[abbr]) ? cfg.teamNames[abbr] : abbr;
    teamSelect.appendChild(opt);
  }});
  teamGroup.appendChild(teamLabel);
  teamGroup.appendChild(teamSelect);

  const statGroup = document.createElement("div");
  statGroup.className = "picker-group";
  const statLabel = document.createElement("div");
  statLabel.className = "picker-label";
  statLabel.textContent = "Metric";
  const statSelect = document.createElement("select");
  cfg.stats.forEach(s => {{
    const opt = el2("option", {{value: s.key}});
    opt.textContent = s.label;
    statSelect.appendChild(opt);
  }});
  statGroup.appendChild(statLabel);
  statGroup.appendChild(statSelect);

  pickerRow.appendChild(teamGroup);
  pickerRow.appendChild(statGroup);
  container.appendChild(pickerRow);

  const chartMount = document.createElement("div");
  container.appendChild(chartMount);

  const caption = document.createElement("p");
  caption.className = "compare-caption";
  container.appendChild(caption);

  function render() {{
    chartMount.innerHTML = "";
    const teamAbbr = teamSelect.value;
    const statKey = statSelect.value;
    const statCfg = cfg.stats.find(s => s.key === statKey);
    const players = cfg.rosters[teamAbbr] || [];
    if (players.length === 0) {{ caption.textContent = "No roster data for this team."; return; }}
    const sorted = [...players].sort((a, b) => b[statKey] - a[statKey]);
    const top = sorted[0];

    const barData = sorted.map(p => ({{
      label: p.name,
      value: p[statKey],
      highlight: p.name === top.name,
    }}));

    drawDivergingBar(chartMount, {{
      data: barData,
      valueLabel: statCfg.label,
      xAxisLabel: statCfg.label,
      annotationSuffix: statCfg.suffix || "",
    }});

    const teamFull = (cfg.teamNames && cfg.teamNames[teamAbbr]) ? cfg.teamNames[teamAbbr] : teamAbbr;
    caption.textContent = `${{teamFull}}: ${{top.name}} leads the roster in ${{statCfg.label.toLowerCase()}} (${{top[statKey].toFixed(2)}}${{statCfg.suffix || ""}}).`;
  }}

  teamSelect.addEventListener("change", render);
  statSelect.addEventListener("change", render);
  render();
}}
function el2(tag, attrs) {{
  const e = document.createElement(tag);
  for (const k in (attrs || {{}})) e.setAttribute(k, attrs[k]);
  return e;
}}

// ---------- build tabs + panels ----------
const tabsEl = document.getElementById("tabs");
const panelsEl = document.getElementById("panels");

CHARTS.forEach((chart, i) => {{
  const btn = document.createElement("button");
  btn.className = "tab-btn" + (i === 0 ? " active" : "");
  btn.textContent = chart.tabLabel;
  btn.addEventListener("click", () => {{
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("panel-" + i).classList.add("active");
  }});
  tabsEl.appendChild(btn);

  const panel = document.createElement("div");
  panel.className = "panel" + (i === 0 ? " active" : "");
  panel.id = "panel-" + i;
  panel.innerHTML = `<p class="kicker">${{chart.metricLabel || chart.tabLabel}}</p><h2>${{chart.title}}</h2><p class="blurb">${{chart.blurb}}</p><div class="chart-mount"></div><p class="footnote">${{chart.footnote || ""}}</p>`;
  panelsEl.appendChild(panel);

  const mount = panel.querySelector(".chart-mount");
  if (chart.type === "diverging-bar") drawDivergingBar(mount, chart);
  if (chart.type === "scatter") drawScatter(mount, chart);
  if (chart.type === "team-compare") drawTeamCompare(mount, chart);
}});
</script>
</body>
</html>
"""


def render_dashboard(title, subtitle, charts):
    """charts: list of dicts matching the JS CHARTS shape. tooltip fields
    must be pre-rendered HTML strings per point (see build helpers below)."""
    return PAGE_TEMPLATE.format(
        title=title, subtitle=subtitle, charts_json=json.dumps(charts),
    )
