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

import datetime as _dt
import html as _html
import json

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{social_meta}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600&family=Karla:wght@400;500;700&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'%3E%3Cg transform='translate(100,100)'%3E%3Cg transform='rotate(0)'%3E%3Cpath fill='%23C98A2E' stroke='%231F1B16' stroke-width='4' d='M0,0 C-22,-11 -37,-33 -33,-55 C-29,-75 29,-75 33,-55 C37,-33 22,-11 0,0 Z'/%3E%3C/g%3E%3Cg transform='rotate(90)'%3E%3Cpath fill='%23C98A2E' stroke='%231F1B16' stroke-width='4' d='M0,0 C-22,-11 -37,-33 -33,-55 C-29,-75 29,-75 33,-55 C37,-33 22,-11 0,0 Z'/%3E%3C/g%3E%3Cg transform='rotate(180)'%3E%3Cpath fill='%23C98A2E' stroke='%231F1B16' stroke-width='4' d='M0,0 C-22,-11 -37,-33 -33,-55 C-29,-75 29,-75 33,-55 C37,-33 22,-11 0,0 Z'/%3E%3C/g%3E%3Cg transform='rotate(270)'%3E%3Cpath fill='%23C98A2E' stroke='%231F1B16' stroke-width='4' d='M0,0 C-22,-11 -37,-33 -33,-55 C-29,-75 29,-75 33,-55 C37,-33 22,-11 0,0 Z'/%3E%3C/g%3E%3Ccircle r='10' fill='%231F1B16'/%3E%3C/g%3E%3C/svg%3E">
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
    /* Round 20: series-1 unified with the brand's Amber (was blue #2a78d6) --
       "positive/emphasis" data color now literally matches --brand-amber below,
       by explicit user choice. series-1-dark/ink updated to keep contrast and
       hover-state legible against the new amber fill (white text on amber
       fails WCAG contrast; dark ink passes). Red stays the negative color. */
    --series-1: #C98A2E;
    --surface-2: #eceff1;
    --series-1-dark: #8A5A1E;
    --series-1-ink: #1F1B16;
    --red: #e34948;
    --font-body: 'Karla', system-ui, -apple-system, "Segoe UI", sans-serif;
    --font-head: 'Fraunces', Georgia, serif;
    --font-brand: 'Fraunces', Georgia, serif;
    --brand-amber: #C98A2E;
    --brand-ink: #1F1B16;
    --brand-clay: #B5573F;
    --brand-warmgray: #8C8377;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: var(--font-body); background: var(--page); color: var(--text-primary); }}
  .app {{ max-width: 960px; margin: 0 auto; padding: 28px 24px 48px; text-align: left; }}
  .masthead {{ display: flex; align-items: center; gap: 10px; margin-bottom: 22px; }}
  .masthead-mark {{ width: 36px; height: 36px; flex: none; }}
  .masthead-word {{ font-family: var(--font-brand); font-weight: 600; font-size: 16px; color: var(--brand-ink); letter-spacing: -0.01em; }}
  .app-header {{ border-top: 1px solid var(--grid); padding-top: 18px; }}
  .app-header h1 {{ font-family: var(--font-head); font-weight: 600; letter-spacing: -0.01em; font-size: 22px; margin: 0 0 4px; }}
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
  .kicker {{ font-family: var(--font-body); font-size: 10.5px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); margin: 0 0 6px; }}
  .panel h2 {{ font-family: var(--font-head); font-weight: 600; letter-spacing: -0.01em; font-size: 18px; margin: 0 0 6px; line-height: 1.35; max-width: 640px; }}
  .panel .blurb {{ font-size: 12.5px; color: var(--text-secondary); margin: 0 0 16px; max-width: 640px; }}
  .story {{ margin: 0 0 22px; padding: 16px 20px; background: var(--surface-1); border-radius: 12px; border-left: 3px solid var(--series-1); }}
  .story .kicker {{ margin: 0 0 6px; }}
  .story-lede {{ font-family: var(--font-body); font-size: 15px; font-weight: 500; color: var(--text-primary); line-height: 1.5; margin: 0; max-width: 680px; }}
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
  /* dense (full-league) scatters: translucent, hairline-edged marks so 250
     overlapping points read as density instead of a solid gray mass */
  .bubble.dense {{ opacity: 0.5; stroke-width: 0.75px; }}
  .bubble.dense:hover, .bubble.dense.hover {{ opacity: 1; }}
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
  .page-footer {{ font-size: 11px; color: var(--text-muted); margin-top: 28px; padding-top: 14px; border-top: 1px solid var(--grid); }}
  .page-footer a {{ color: inherit; }}
  .legend {{ display: flex; gap: 16px; font-size: 11.5px; color: var(--text-secondary); margin-bottom: 10px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-swatch {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .line-path {{ fill: none; stroke: var(--series-1); stroke-width: 2.5px; }}
  .line-dot {{ fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2px; cursor: pointer; }}
  .line-dot:hover {{ fill: var(--series-1-dark); }}
  .pitch-outline {{ fill: none; stroke: var(--baseline); stroke-width: 1.5px; }}
  .pitch-line {{ fill: none; stroke: var(--baseline); stroke-width: 1px; }}
  .shot-dot {{ stroke: var(--series-1); stroke-width: 1.5px; cursor: pointer; }}
  .shot-dot.goal {{ fill: var(--series-1); }}
  .shot-dot.no-goal {{ fill: var(--surface-1); }}
  .shot-dot.muted {{ stroke: var(--baseline); }}
  .shot-dot.muted.no-goal {{ fill: var(--surface-1); }}
  /* Chance band. Deliberately NOT --series-1: the emphasis color is reserved
     for the one mark a chart is about, and a large amber wash behind the
     points would compete with the highlighted bubble for exactly the
     attention that bubble is supposed to win. A neutral warm gray at low
     alpha reads as ground, sits under both the amber highlight and the muted
     crowd, and keeps the gridlines visible through it. */
  .chance-band {{ fill: var(--brand-warmgray); opacity: 0.15; pointer-events: none; }}
  .legend-swatch.band-swatch {{ width: 22px; height: 10px; border-radius: 2px; background: rgba(140, 131, 119, 0.30); }}
  .table-wrap {{ margin-top: 18px; }}
  .table-caption {{ font-size: 11.5px; color: var(--text-secondary); margin: 0 0 8px; max-width: 640px; }}
  .table-scroll {{ max-height: 340px; overflow-y: auto; border: 1px solid var(--grid); border-radius: 8px; }}
  .data-table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; font-variant-numeric: tabular-nums; }}
  .data-table th, .data-table td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid var(--grid); white-space: nowrap; }}
  .data-table th {{
    position: sticky; top: 0; background: var(--surface-2); color: var(--text-secondary);
    font-weight: 700; font-size: 10.5px; letter-spacing: 0.04em; text-transform: uppercase;
    cursor: pointer; user-select: none; z-index: 1;
  }}
  .data-table th:hover, .data-table th:focus {{ color: var(--text-primary); }}
  .data-table th.sorted {{ color: var(--series-1-dark); }}
  .data-table th.sorted::after {{ content: " \\2195"; }}
  .data-table td.num, .data-table th.num {{ text-align: right; }}
  .data-table tbody tr:hover {{ background: var(--surface-2); }}
  .methods-heading {{
    font-family: var(--font-head); font-size: 15px; font-weight: 600; color: var(--text-primary);
    margin: 22px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--grid);
  }}
  .methods-list {{ margin: 0; font-size: 12.5px; line-height: 1.55; }}
  .methods-list dt {{ font-weight: 700; color: var(--text-primary); margin-top: 10px; }}
  .methods-list dd {{ margin: 2px 0 0; color: var(--text-secondary); max-width: 720px; }}
  .download-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }}
  .download-btn {{
    font-family: var(--font-body); font-size: 12px; font-weight: 600; color: var(--text-primary);
    background: var(--surface-1); border: 1px solid var(--baseline); border-radius: 6px;
    padding: 7px 12px; cursor: pointer;
  }}
  .download-btn:hover {{ border-color: var(--series-1); color: var(--series-1-dark); }}
  /* ---- Phone-width behaviour ----
     Most traffic to a shared link is mobile, and until the viewport meta tag
     above was added this page rendered at desktop width on a phone. The
     charts are fixed-width SVG, so they scroll horizontally inside their own
     mount rather than being squashed to illegibility. */
  .chart-mount {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  @media (max-width: 600px) {{
    .app {{ padding: 18px 14px 36px; }}
    .app-header h1 {{ font-size: 19px; }}
    .panel {{ padding: 16px 14px 18px; }}
    .panel h2 {{ font-size: 16.5px; }}
    /* Thirteen tabs wrap to six stacked rows at 390px, pushing the first
       chart most of a screen below the fold -- on the width where most
       shared links actually get opened. One scrolling row instead: the
       partially visible next tab is what signals there are more. */
    .tabs {{ gap: 2px; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; -webkit-overflow-scrolling: touch; }}
    .tabs::-webkit-scrollbar {{ display: none; }}
    .tab-btn {{ padding: 8px 10px; font-size: 12px; white-space: nowrap; flex: none; }}
    .story {{ padding: 14px 16px; }}
    .story-lede {{ font-size: 14px; }}
    .picker-row {{ gap: 12px; }}
    .panel select {{ max-width: 100%; }}
    .table-scroll {{ overflow-x: auto; }}
    .methods-list dd {{ max-width: none; }}
    .download-row {{ gap: 8px; }}
  }}
</style>
</head>
<body>
<div class="app">
  <div class="masthead">
    <svg class="masthead-mark" viewBox="0 0 240 240" aria-hidden="true">
      <g stroke="#B5573F" fill="none" stroke-linecap="round" opacity="0.6">
        <path d="M6,74 L234,74" stroke-width="2"/>
        <path d="M6,74 C34,46 52,20 68,20 C92,20 96,54 120,58 C144,54 148,20 172,20 C188,20 206,46 234,74" stroke-width="2"/>
        <line x1="63" y1="72" x2="63" y2="20" stroke-width="3"/>
        <line x1="73" y1="72" x2="73" y2="20" stroke-width="3"/>
        <line x1="63" y1="34" x2="73" y2="34" stroke-width="2"/>
        <line x1="63" y1="52" x2="73" y2="52" stroke-width="2"/>
        <line x1="167" y1="72" x2="167" y2="20" stroke-width="3"/>
        <line x1="177" y1="72" x2="177" y2="20" stroke-width="3"/>
        <line x1="167" y1="34" x2="177" y2="34" stroke-width="2"/>
        <line x1="167" y1="52" x2="177" y2="52" stroke-width="2"/>
      </g>
      <path fill="none" stroke="#8C8377" stroke-width="1.5" opacity="0.25" stroke-linecap="round" d="M-10,80 C40,72 80,88 120,80 C160,72 200,88 250,80"/>
      <path fill="none" stroke="#8C8377" stroke-width="1.5" opacity="0.35" stroke-linecap="round" d="M-10,195 C40,183 80,207 120,195 C160,183 200,207 250,195"/>
      <path fill="none" stroke="#8C8377" stroke-width="2" opacity="0.55" stroke-linecap="round" d="M-10,210 C40,196 90,224 130,210 C170,196 210,224 250,210"/>
      <path fill="none" stroke="#8C8377" stroke-width="2.5" opacity="0.8" stroke-linecap="round" d="M-10,226 C40,210 90,240 130,226 C170,210 220,240 250,226"/>
      <g transform="translate(120,150)">
        <g transform="rotate(0)"><path fill="#C98A2E" stroke="#1F1B16" stroke-width="2.5" d="M0,0 C-20,-10 -34,-30 -30,-50 C-26,-68 26,-68 30,-50 C34,-30 20,-10 0,0 Z"/></g>
        <g transform="rotate(90)"><path fill="#C98A2E" stroke="#1F1B16" stroke-width="2.5" d="M0,0 C-20,-10 -34,-30 -30,-50 C-26,-68 26,-68 30,-50 C34,-30 20,-10 0,0 Z"/></g>
        <g transform="rotate(180)"><path fill="#C98A2E" stroke="#1F1B16" stroke-width="2.5" d="M0,0 C-20,-10 -34,-30 -30,-50 C-26,-68 26,-68 30,-50 C34,-30 20,-10 0,0 Z"/></g>
        <g transform="rotate(270)"><path fill="#C98A2E" stroke="#1F1B16" stroke-width="2.5" d="M0,0 C-20,-10 -34,-30 -30,-50 C-26,-68 26,-68 30,-50 C34,-30 20,-10 0,0 Z"/></g>
        <circle r="8" fill="#1F1B16"/>
      </g>
    </svg>
    <span class="masthead-word">Poppies in the Fog</span>
  </div>
  <div class="app-header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
{story_block}  <div class="tabs" id="tabs"></div>
  <div id="panels"></div>
  <p class="page-footer">{source_credit_block}</p>
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
  // Stable per-point id so a click can be traced back to the same bar
  // across re-renders, independent of the value-sort order below.
  cfg.data.forEach((d, i) => {{ if (d.__cid === undefined) d.__cid = i; }});
  let activeCid = null; // null = show the curated default highlight

  function renderOnce() {{
    container.innerHTML = "";
    // Reader-driven highlight swap: clicking a bar makes IT the sole
    // highlighted/annotated bar and mutes every other bar, exactly like the
    // curated default -- just reader-picked instead of author-picked. This
    // keeps the Design Guidelines' "exactly one emphasized point" rule true
    // at all times; it never adds a second color, it only reassigns the one
    // that already exists.
    const effective = activeCid === null ? cfg.data
      : cfg.data.map(d => ({{...d, highlight: d.__cid === activeCid}}));

    // onSelect: optional hook so a caller can react to the reader reassigning
    // the highlight -- passed the clicked row, or null when showing the curated
    // default. Used by drawPresetCompare to swap the panel's headline/blurb to
    // the clicked player. Absent on every existing chart, so behavior there is
    // unchanged.
    if (cfg.onSelect) {{
      cfg.onSelect(activeCid === null
        ? null
        : effective.find(d => d.__cid === activeCid) || null);
    }}
    // Round 21: best-at-top, worst-at-bottom is now the default for every
    // diverging-bar chart, not just ranked leaderboards -- the earlier
    // ascending default (most-negative-at-top) read as upside down to a
    // reader, since row index 0 renders at the top of the SVG (y = i * rowH,
    // and SVG y grows downward) regardless of what the values mean. sortAsc
    // is the escape hatch if a future chart genuinely needs the opposite;
    // nothing in this project currently does. (cfg.sortDesc is no longer
    // read -- descending is the default now, not an opt-in.)
    const data = [...effective].sort((a, b) => cfg.sortAsc ? a.value - b.value : b.value - a.value);
    const longestLabel = Math.max(...data.map(d => d.label.length));
    const margin = {{top: 8, right: 30, bottom: 34, left: Math.max(90, longestLabel * 6.5 + 12)}};
    const width = 820 - margin.left - margin.right;
    const rowH = 26;
    const height = data.length * rowH;
    const svg = el("svg", {{width: width + margin.left + margin.right, height: height + margin.top + margin.bottom}});
    const g = el("g", {{transform: `translate(${{margin.left}},${{margin.top}})`}});
    svg.appendChild(g);
    container.appendChild(svg);

    // oneSided: for data that's never negative (e.g. goals scored), skip the
    // diverging -max..max axis -- showing unused negative ticks for a value
    // that literally can't go negative is exactly the chartjunk the Design
    // Guidelines doc calls out. Scale 0..max and start bars at the left edge
    // instead of a center zero line.
    const oneSided = cfg.oneSided && data.every(d => d.value >= 0);
    const maxAbs = Math.max(...data.map(d => Math.abs(d.value))) * 1.15 || 1;
    const x = oneSided ? (v => (v / maxAbs) * width) : (v => (v / maxAbs) * (width / 2) + width / 2);
    const zeroX = x(0);

    ticksFor(oneSided ? 0 : -maxAbs, maxAbs, oneSided ? 5 : 6).forEach(t => {{
      g.appendChild(el("line", {{class: "gridline", x1: x(t), x2: x(t), y1: -4, y2: height + 4}}));
      const label = el("text", {{class: "axis-label", x: x(t), y: height + 20, "text-anchor": "middle"}});
      label.textContent = t;
      g.appendChild(label);
    }});
    if (!oneSided) {{
      g.appendChild(el("line", {{x1: zeroX, x2: zeroX, y1: -4, y2: height + 4, stroke: "var(--baseline)", "stroke-width": 1}}));
    }}

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
        `<div class="name">${{d.label}}</div><div class="row">${{cfg.valueLabel}}: ${{d.value.toFixed(2)}}</div>${{d.extra ? `<div class="row">${{d.extra}}</div>` : ""}}`, event));
      rect.addEventListener("mousemove", moveTooltip);
      rect.addEventListener("mouseleave", hideTooltip);
      rect.addEventListener("click", () => {{
        activeCid = (activeCid === d.__cid) ? null : d.__cid;
        renderOnce();
      }});
      g.appendChild(rect);

      const label = el("text", {{class: "bar-label" + (isMuted ? " muted" : ""), x: -8, y: y + (rowH - 8) / 2 + 4, "text-anchor": "end"}});
      label.textContent = d.label;
      g.appendChild(label);

      if (d.highlight) {{
        const sign = (!oneSided && d.value >= 0) ? "+" : "";
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

    // Clicking anywhere on the chart that isn't a bar (empty axis/gridline
    // area) reverts to the curated default highlight.
    svg.addEventListener("click", (event) => {{
      if (event.target === svg && activeCid !== null) {{ activeCid = null; renderOnce(); }}
    }});
  }}

  renderOnce();
}}

function resolveCollisions(points, r, padding, bounds) {{
  // bounds: optional {{width, height}} of the plot area. Without it, a dense
  // cluster (e.g. 249 players packed into the bottom-left corner of a
  // per-96 chart) inflates outward until it escapes the axes entirely --
  // points end up drawn below the x-axis and left of the y-axis, i.e. "off
  // the chart". Clamping INSIDE the loop (rather than once at the end) means
  // a point pinned against an edge still pushes its neighbors, so the
  // cluster spreads along the edge instead of stacking on top of it.
  const minDist = r * 2 + padding;
  const lo = r + 1;
  const hiX = bounds ? bounds.width - r - 1 : Infinity;
  const hiY = bounds ? bounds.height - r - 1 : Infinity;
  const clamp = (p) => {{
    if (!bounds) return;
    p.x = Math.max(lo, Math.min(hiX, p.x));
    p.y = Math.max(lo, Math.min(hiY, p.y));
  }};
  points.forEach(clamp);
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
          clamp(a); clamp(b);
          moved = true;
        }}
      }}
    }}
    if (!moved) break;
  }}
  return points;
}}

// Sortable data table rendered under a chart. Exists because a hover tooltip
// is not a view of the data -- it shows one point at a time, needs a pointer,
// and cannot be scanned, compared, or read by anyone using a keyboard or a
// screen reader. Any chart that carries per-point numbers worth quoting gets
// one of these as the non-hover-dependent way to read the same values.
function buildDataTable(spec) {{
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  if (spec.caption) {{
    const cap = document.createElement("p");
    cap.className = "table-caption";
    cap.innerHTML = spec.caption;
    wrap.appendChild(cap);
  }}
  const scroller = document.createElement("div");
  scroller.className = "table-scroll";
  const table = document.createElement("table");
  table.className = "data-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  spec.columns.forEach((col, ci) => {{
    const th = document.createElement("th");
    th.textContent = col.label;
    th.className = col.num ? "num" : "";
    th.tabIndex = 0;
    th.setAttribute("role", "button");
    th.setAttribute("aria-label", `Sort by ${{col.label}}`);
    const doSort = () => sortBy(ci);
    th.addEventListener("click", doSort);
    th.addEventListener("keydown", (e) => {{
      if (e.key === "Enter" || e.key === " ") {{ e.preventDefault(); doSort(); }}
    }});
    headRow.appendChild(th);
  }});
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  table.appendChild(tbody);
  scroller.appendChild(table);
  wrap.appendChild(scroller);

  let sortCol = null, sortDesc = true;
  let rows = spec.rows.slice();

  function paint() {{
    tbody.innerHTML = "";
    rows.forEach(r => {{
      const tr = document.createElement("tr");
      spec.columns.forEach(col => {{
        const td = document.createElement("td");
        const v = r[col.key];
        // An empty string, not "null"/"undefined": a missing z-score (too few
        // shots to compute one) is genuinely absent, and printing a zero there
        // would assert something the data doesn't say.
        td.textContent = (v === null || v === undefined) ? "" : v;
        td.className = col.num ? "num" : "";
        tr.appendChild(td);
      }});
      tbody.appendChild(tr);
    }});
    headRow.querySelectorAll("th").forEach((th, i) => {{
      th.classList.toggle("sorted", i === sortCol);
      th.setAttribute("aria-sort", i === sortCol ? (sortDesc ? "descending" : "ascending") : "none");
    }});
  }}

  function sortBy(ci) {{
    const col = spec.columns[ci];
    if (sortCol === ci) sortDesc = !sortDesc;
    else {{ sortCol = ci; sortDesc = true; }}
    rows.sort((a, b) => {{
      let av = a[col.key], bv = b[col.key];
      // Missing values sort to the bottom in BOTH directions rather than
      // riding to the top as a phantom minimum -- an absent number is not a
      // small number.
      const aMissing = (av === null || av === undefined || av === "");
      const bMissing = (bv === null || bv === undefined || bv === "");
      if (aMissing && bMissing) return 0;
      if (aMissing) return 1;
      if (bMissing) return -1;
      if (col.num) return sortDesc ? bv - av : av - bv;
      return sortDesc ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv));
    }});
    paint();
  }}

  paint();
  return wrap;
}}

function drawScatter(container, cfg) {{
  // Stable per-point id so a click can be traced back to the same bubble
  // across re-renders (collision-avoidance nudges positions slightly
  // differently once highlight/mute states change, so identity has to
  // travel via an id, not screen position).
  cfg.data.forEach((d, i) => {{ if (d.__cid === undefined) d.__cid = i; }});
  let activeCid = null; // null = show the curated default highlight

  // The SVG is redrawn from scratch on every highlight swap, but the data
  // table underneath is not -- it lives in its own host appended after this
  // one, so clicking a bubble doesn't wipe the reader's chosen sort order.
  const chartHost = document.createElement("div");
  container.appendChild(chartHost);

  function renderOnce() {{
    chartHost.innerHTML = "";
    // Reader-driven highlight swap -- see drawDivergingBar for the same
    // pattern. Clicking a bubble makes it the sole highlighted bubble;
    // every other bubble mutes to gray, same as the curated default. If the
    // clicked point isn't the curated story point it simply has no
    // `annotation` text to show (that guard already exists below) -- the
    // color swap plus the existing hover tooltip is enough detail, and it
    // avoids inventing a new sentence for an arbitrary point.
    const data = activeCid === null ? cfg.data
      : cfg.data.map(d => ({{...d, highlight: d.__cid === activeCid}}));

    const margin = {{top: 12, right: 24, bottom: 46, left: 58}};
    const width = 780 - margin.left - margin.right;
    const height = (cfg.height || 520) - margin.top - margin.bottom;
    const R = cfg.radius || 16;

    const svg = el("svg", {{width: width + margin.left + margin.right, height: height + margin.top + margin.bottom}});
    const g = el("g", {{transform: `translate(${{margin.left}},${{margin.top}})`}});
    svg.appendChild(g);
    chartHost.appendChild(svg);

    const xMin = Math.min(...data.map(d => d.x));
    const xMax = Math.max(...data.map(d => d.x));
    const yMin = Math.min(...data.map(d => d.y));
    const yMax = Math.max(...data.map(d => d.y));
    // Add 15% padding above/below the data range to match the aesthetic of the original design
    const xRange = xMax - xMin;
    const yRange = yMax - yMin;
    // zeroOrigin: anchor both axes at zero instead of padding around the data
    // range. Needed by any chart carrying a chance band, because that band is
    // a fan pinned at the origin -- cropping the axes to the data turns the
    // fan into a floating wedge whose shape (widening with volume) is the
    // entire message. Left off by default: for charts without a band, zooming
    // to the data is the better use of the space.
    const xScaleMin = cfg.zeroOrigin ? 0 : xMin - xRange * 0.075;
    const xScaleMax = xMax + xRange * 0.075;
    const yScaleMin = cfg.zeroOrigin ? 0 : yMin - yRange * 0.075;
    const yScaleMax = yMax + yRange * 0.075;

    const xScale = v => ((v - xScaleMin) / (xScaleMax - xScaleMin)) * width;
    // invertY: plot higher values lower on screen (useful when "lower is better",
    // e.g. xG Against, so "up" reads as "good" on both axes at once)
    const yScale = cfg.invertY ? (v => ((v - yScaleMin) / (yScaleMax - yScaleMin)) * height) : (v => height - ((v - yScaleMin) / (yScaleMax - yScaleMin)) * height);

    // Tick precision follows the tick STEP, not a fixed 2 decimals: season xG
     // totals step by 5 and want "20", while a per-96 g+ axis steps by 0.05 and
    // needs "0.05". Same helper for both axes so they stay consistent.
    const xTicks = ticksFor(xScaleMin, xScaleMax, 8);
    const yTicks = ticksFor(yScaleMin, yScaleMax, 8);
    const fmtFor = (ticks) => {{
      const step = ticks.length > 1 ? Math.abs(ticks[1] - ticks[0]) : 1;
      const dp = Math.min(3, Math.max(0, Math.ceil(-Math.log10(step))));
      return (t) => (t === 0 ? "0" : t.toFixed(dp));
    }};
    const fmtX = fmtFor(xTicks), fmtY = fmtFor(yTicks);

    xTicks.forEach(t => g.appendChild(el("line", {{class: "gridline", x1: xScale(t), x2: xScale(t), y1: 0, y2: height}})));
    yTicks.forEach(t => g.appendChild(el("line", {{class: "gridline", x1: 0, x2: width, y1: yScale(t), y2: yScale(t)}})));

    const xAxis = el("g", {{class: "axis", transform: `translate(0,${{height}})`}});
    xTicks.forEach(t => {{
      const txt = el("text", {{x: xScale(t), y: 18, "text-anchor": "middle"}}); txt.textContent = fmtX(t); xAxis.appendChild(txt);
    }});
    xAxis.appendChild(el("line", {{x1: 0, x2: width, y1: 0, y2: 0}}));
    g.appendChild(xAxis);

    const yAxis = el("g", {{class: "axis"}});
    yTicks.forEach(t => {{
      const txt = el("text", {{x: -10, y: yScale(t) + 4, "text-anchor": "end"}}); txt.textContent = fmtY(t); yAxis.appendChild(txt);
    }});
    yAxis.appendChild(el("line", {{x1: 0, x2: 0, y1: 0, y2: height}}));
    g.appendChild(yAxis);

    const xLabel = el("text", {{class: "axis-label", x: width / 2, y: height + 38, "text-anchor": "middle"}}); xLabel.textContent = cfg.xAxisLabel; g.appendChild(xLabel);
    const yLabel = el("text", {{class: "axis-label", transform: "rotate(-90)", x: -height / 2, y: -40, "text-anchor": "middle"}}); yLabel.textContent = cfg.yAxisLabel; g.appendChild(yLabel);

    // Chance band: the region in which a perfectly average finisher lands 95%
    // of the time. Drawn BEFORE the reference line and the bubbles so it reads
    // as ground rather than as a mark -- it is context for the points, not a
    // series of its own.
    //
    // Band values are clamped into the plot's y-range instead of being folded
    // into the scale domain. Letting the band set the domain would compress
    // every actual data point to make room for an envelope that is widest
    // exactly where nobody plots (the low-volume left edge); clamping instead
    // lets the ribbon run off the top of the panel, which reads correctly as
    // "and it keeps going".
    if (cfg.band && cfg.band.points && cfg.band.points.length > 1) {{
      const clampY = v => Math.min(Math.max(v, yScaleMin), yScaleMax);
      const bp = cfg.band.points.filter(p => p[0] >= xScaleMin && p[0] <= xScaleMax);
      if (bp.length > 1) {{
        const top = bp.map(p => `${{xScale(p[0])}},${{yScale(clampY(p[2]))}}`);
        const bot = bp.slice().reverse().map(p => `${{xScale(p[0])}},${{yScale(clampY(p[1]))}}`);
        g.appendChild(el("path", {{class: "chance-band", d: `M${{top.join(" L")}} L${{bot.join(" L")}} Z`}}));
      }}
    }}

    if (cfg.refLine) {{
      const lim = Math.min(xMax, yMax);
      g.appendChild(el("line", {{class: "refline", x1: xScale(0), y1: yScale(0), x2: xScale(lim), y2: yScale(lim)}}));
    }}
    if (cfg.medianLines) {{
      const medX = data.map(d => d.x).sort((a,b) => a-b)[Math.floor(data.length / 2)];
      const medY = data.map(d => d.y).sort((a,b) => a-b)[Math.floor(data.length / 2)];
      g.appendChild(el("line", {{class: "refline", x1: xScale(medX), x2: xScale(medX), y1: 0, y2: height}}));
      g.appendChild(el("line", {{class: "refline", x1: 0, x2: width, y1: yScale(medY), y2: yScale(medY)}}));
    }}

    // Dense pool (full league, 100-250+ players): plot TRUE positions and let
    // overlap read as density, with translucent marks. Collision-nudging that
    // many points does two bad things -- it inflates the cluster until points
    // sit outside the axes entirely, and what's left is a rigid lattice that
    // no longer shows where anyone actually is. Nudging is still right for the
    // small labeled charts (16 teams, ~20 keepers), where a legible 3-letter
    // badge matters more than sub-pixel position accuracy.
    const dense = cfg.showBadges === false || data.length > 80;
    const points = data.map(d => ({{x: xScale(d.x), y: yScale(d.y), d}}));
    if (!dense) resolveCollisions(points, R, 3, {{width, height}});

    const hasHighlight = data.some(d => d.highlight);

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
      // In dense mode the emphasized point is drawn larger so the one point the
      // title is about still wins the eye at a glance (Design Guidelines: size
      // and color are both preattentive; the muted crowd gets neither).
      const rr = (dense && d.highlight) ? R * 1.9 : R;
      const circle = el("circle", {{
        class: "bubble" + (isMuted ? " muted" : "") + (dense && isMuted ? " dense" : ""), r: rr,
      }});
      node.appendChild(circle);
      // cfg.showBadges === false means the pool is too dense for an always-on
      // 3-letter team badge on every bubble (chart_builders.scatter_display_params
      // decides this past ~40 points): a 249-player chart turns into unreadable
      // label soup and the labels overflow their own bubbles. In that mode only
      // the emphasized point keeps a badge; everyone else is identified on hover.
      if (cfg.showBadges !== false || d.highlight) {{
        const label = el("text", {{class: "badge-text" + (isMuted ? " muted" : ""), dy: "0.32em", "text-anchor": "middle"}});
        label.textContent = d.badge;
        node.appendChild(label);
      }}

      if (d.highlight && d.annotation) {{
        // Prefer placing the annotation beside the bubble (right, or left if
        // there's no room to the right before the chart edge) -- but in a
        // dense cluster, that text can run straight through a neighboring
        // bubble. Check for that along the annotation's actual horizontal
        // band and fall back to stacking the text above the bubble instead,
        // which is reliably clear of horizontal neighbors.
        const estTextWidth = d.annotation.length * 6.4;
        const anchorRight = (p.x + R + 8 + estTextWidth) < width;
        const sideX = anchorRight ? p.x + R + 8 : p.x - R - 8;
        const sideEndX = anchorRight ? sideX + estTextWidth : sideX - estTextWidth;
        const bandLo = Math.min(sideX, sideEndX) - R, bandHi = Math.max(sideX, sideEndX) + R;
        const collides = points.some(other => other.d !== d
          && Math.abs(other.y - p.y) < R * 2
          && other.x > bandLo && other.x < bandHi);

        let annoX = anchorRight ? R + 8 : -(R + 8);
        let annoY = 4;
        let annoAnchor = anchorRight ? "start" : "end";
        if (collides) {{
          // Stack above the bubble instead -- but centering on the bubble can
          // run the text off the left/right edge of the chart when the bubble
          // itself sits near an edge, so clamp to the visible plot area.
          annoY = -(R + 10);
          const halfW = estTextWidth / 2;
          if (p.x - halfW < 4) {{ annoAnchor = "start"; annoX = 4 - p.x; }}
          else if (p.x + halfW > width - 4) {{ annoAnchor = "end"; annoX = (width - 4) - p.x; }}
          else {{ annoAnchor = "middle"; annoX = 0; }}
        }}
        const anno = el("text", {{class: "annotation", x: annoX, y: annoY, "text-anchor": annoAnchor}});
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
      node.addEventListener("click", () => {{
        activeCid = (activeCid === d.__cid) ? null : d.__cid;
        renderOnce();
      }});
    }});

    // Clicking empty chart area (not a bubble) reverts to the curated default.
    svg.addEventListener("click", (event) => {{
      if (event.target === svg && activeCid !== null) {{ activeCid = null; renderOnce(); }}
    }});
  }}

  if (cfg.band) {{
    const legend = document.createElement("div");
    legend.className = "legend";
    legend.innerHTML = `
      <div class="legend-item"><span class="legend-swatch band-swatch"></span>${{cfg.band.label || "Chance band"}} — inside this, the gap is not distinguishable from luck</div>
    `;
    container.insertBefore(legend, chartHost);
  }}

  renderOnce();

  if (cfg.table && cfg.table.rows && cfg.table.rows.length) {{
    container.appendChild(buildDataTable(cfg.table));
  }}
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

function drawLine(container, cfg) {{
  // Single-series line chart -- e.g. a league-wide total plotted one point
  // per season. One highlighted point (per the highlight/mute convention
  // used everywhere else in this dashboard) gets a static annotation; every
  // other point is a plain series-color dot with no callout.
  const margin = {{top: 16, right: 28, bottom: 40, left: 50}};
  const width = 780 - margin.left - margin.right;
  const height = (cfg.height || 340) - margin.top - margin.bottom;

  const svg = el("svg", {{width: width + margin.left + margin.right, height: height + margin.top + margin.bottom}});
  const g = el("g", {{transform: `translate(${{margin.left}},${{margin.top}})`}});
  svg.appendChild(g);
  container.appendChild(svg);

  const xs = cfg.data.map(d => d.x);
  const ys = cfg.data.map(d => d.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMax = Math.max(...ys) * 1.15 || 1;
  const xScale = v => ((v - xMin) / (xMax - xMin || 1)) * width;
  const yScale = v => height - (v / yMax) * height;

  ticksFor(0, yMax, 5).forEach(t => {{
    g.appendChild(el("line", {{class: "gridline", x1: 0, x2: width, y1: yScale(t), y2: yScale(t)}}));
    const label = el("text", {{class: "axis-label", x: -10, y: yScale(t) + 4, "text-anchor": "end"}});
    label.textContent = t;
    g.appendChild(label);
  }});

  const xAxis = el("g", {{class: "axis", transform: `translate(0,${{height}})`}});
  cfg.data.forEach(d => {{
    const txt = el("text", {{x: xScale(d.x), y: 18, "text-anchor": "middle"}});
    txt.textContent = d.xLabel !== undefined ? d.xLabel : d.x;
    xAxis.appendChild(txt);
  }});
  xAxis.appendChild(el("line", {{x1: 0, x2: width, y1: 0, y2: 0}}));
  g.appendChild(xAxis);

  const pathD = cfg.data.map((d, i) => `${{i === 0 ? "M" : "L"}}${{xScale(d.x)}},${{yScale(d.y)}}`).join(" ");
  g.appendChild(el("path", {{class: "line-path", d: pathD}}));

  cfg.data.forEach(d => {{
    const cx = xScale(d.x), cy = yScale(d.y);
    const dot = el("circle", {{class: "line-dot", cx: cx, cy: cy, r: d.highlight ? 6 : 4.5}});
    dot.addEventListener("mouseenter", (event) => showTooltip(d.tooltip || `<div class="row">${{d.y}}</div>`, event));
    dot.addEventListener("mousemove", moveTooltip);
    dot.addEventListener("mouseleave", hideTooltip);
    g.appendChild(dot);

    if (d.highlight && d.annotation) {{
      const above = cy > 24;
      const anno = el("text", {{
        class: "annotation", x: cx, y: above ? cy - 14 : cy + 22, "text-anchor": "middle",
      }});
      anno.textContent = d.annotation;
      g.appendChild(anno);
    }}
  }});

  const xLabel = el("text", {{class: "axis-label", x: width / 2, y: height + 34, "text-anchor": "middle"}});
  xLabel.textContent = cfg.xAxisLabel || "";
  g.appendChild(xLabel);
  const yLabel = el("text", {{class: "axis-label", transform: "rotate(-90)", x: -height / 2, y: -34, "text-anchor": "middle"}});
  yLabel.textContent = cfg.yAxisLabel || "";
  g.appendChild(yLabel);
}}

function drawSeasonCompare(container, cfg) {{
  // Same dropdown-driven pattern as drawTeamCompare, but the picker
  // selects a SEASON instead of a team, and the bar chart shows every
  // team's value for that season.
  const pickerRow = document.createElement("div");
  pickerRow.className = "picker-row";

  const seasonGroup = document.createElement("div");
  seasonGroup.className = "picker-group";
  const seasonLabel = document.createElement("div");
  seasonLabel.className = "picker-label";
  seasonLabel.textContent = "Season";
  const seasonSelect = document.createElement("select");
  cfg.seasons.forEach(s => {{
    const opt = el2("option", {{value: s}});
    opt.textContent = s;
    seasonSelect.appendChild(opt);
  }});
  seasonSelect.value = cfg.seasons[cfg.seasons.length - 1];
  seasonGroup.appendChild(seasonLabel);
  seasonGroup.appendChild(seasonSelect);
  pickerRow.appendChild(seasonGroup);
  container.appendChild(pickerRow);

  const chartMount = document.createElement("div");
  container.appendChild(chartMount);
  const caption = document.createElement("p");
  caption.className = "compare-caption";
  container.appendChild(caption);

  function render() {{
    chartMount.innerHTML = "";
    const season = seasonSelect.value;
    const rows = cfg.bySeason[season] || [];
    if (rows.length === 0) {{ caption.textContent = "No data for this season."; return; }}
    const sorted = [...rows].sort((a, b) => b.value - a.value);
    const top = sorted[0];
    drawDivergingBar(chartMount, {{
      data: rows.map(r => ({{label: r.label, value: r.value, highlight: r.label === top.label}})),
      valueLabel: cfg.valueLabel, xAxisLabel: cfg.valueLabel, oneSided: true,
    }});
    caption.textContent = `${{season}}: ${{top.label}} led the league with ${{top.value}} ${{cfg.valueLabel.toLowerCase()}}.`;
  }}

  seasonSelect.addEventListener("change", render);
  render();
}}

function drawPresetCompare(container, cfg) {{
  // Same dropdown-driven pattern as drawSeasonCompare, but the picker selects a
  // WEIGHTING preset rather than a season. One deliberate difference:
  //   - The panel headline above this chart states rank stability across every
  //     weighting and does NOT change with the dropdown -- that stability is
  //     the finding. The dropdown only changes which single bar is emphasized.
  // (Round 21: best-at-top is now drawDivergingBar's default for every chart,
  // not just this one, so the sortDesc flag this comment used to explain no
  // longer needs calling out here specifically.)
  const pickerRow = document.createElement("div");
  pickerRow.className = "picker-row";

  const group = document.createElement("div");
  group.className = "picker-group";
  const pickerLabel = document.createElement("div");
  pickerLabel.className = "picker-label";
  pickerLabel.textContent = cfg.pickerLabel || "Weighting";
  const presetSelect = document.createElement("select");
  cfg.presets.forEach(p => {{
    const opt = el2("option", {{value: p.key}});
    opt.textContent = p.label;
    presetSelect.appendChild(opt);
  }});
  presetSelect.value = cfg.defaultPreset || cfg.presets[0].key;
  group.appendChild(pickerLabel);
  group.appendChild(presetSelect);
  pickerRow.appendChild(group);
  container.appendChild(pickerRow);

  const chartMount = document.createElement("div");
  container.appendChild(chartMount);
  const caption = document.createElement("p");
  caption.className = "compare-caption";
  container.appendChild(caption);

  // The panel's own <h2>/blurb live OUTSIDE this chart mount (they're built by
  // the tab loop below), so reach up to them. Clicking a bar swaps in that
  // player's headline and story; deselecting restores the panel's default --
  // the league-wide stability finding. Stashing the defaults on first run means
  // a revert never has to reconstruct them from cfg.
  const panel = container.closest(".panel");
  const headEl = panel ? panel.querySelector("h2") : null;
  const blurbEl = panel ? panel.querySelector(".blurb") : null;
  const defaultHead = headEl ? headEl.textContent : "";
  const defaultBlurb = blurbEl ? blurbEl.textContent : "";
  // Announce the swap to screen readers -- the visual change is obvious, the
  // text change is not.
  if (headEl) headEl.setAttribute("aria-live", "polite");

  function showSelection(row) {{
    if (!headEl || !blurbEl) return;
    if (row && row.headline) {{
      headEl.textContent = row.headline;
      blurbEl.textContent = row.story || "";
    }} else {{
      headEl.textContent = defaultHead;
      blurbEl.textContent = defaultBlurb;
    }}
  }}

  function render() {{
    chartMount.innerHTML = "";
    const rows = (cfg.byPreset || {{}})[presetSelect.value] || [];
    if (rows.length === 0) {{
      caption.textContent = "No qualifying players for this weighting.";
      return;
    }}
    drawDivergingBar(chartMount, {{
      data: rows.map(r => ({{label: r.label, value: r.value,
                            highlight: r.highlight, extra: r.extra,
                            headline: r.headline, story: r.story}})),
      valueLabel: cfg.valueLabel,
      xAxisLabel: cfg.xAxisLabel || cfg.valueLabel,
      oneSided: true,
      onSelect: showSelection,
    }});
    caption.textContent = (cfg.captions || {{}})[presetSelect.value] || "";
  }}

  // Changing the weighting rebuilds the bar chart, which resets its own
  // selection to null and fires onSelect(null) -- so the panel text returns to
  // the default automatically, no extra reset needed here.
  presetSelect.addEventListener("change", render);
  render();
}}

function drawPositionGrid(container, cfg) {{
  // Heatmap: teams down, ASA's positions across (defensive-most to
  // attacking-most, so the grid reads like a pitch). Colour is the established
  // diverging pair at varying opacity -- no new hues, per the Design
  // Guidelines' "every non-gray colour maps to something specific" rule.
  //
  // Cells without enough minutes are rendered as an explicit neutral, never as
  // a pale red: "we don't know" must not look like "slightly weak".
  const positions = cfg.positions;
  const teams = cfg.teams;
  const byKey = {{}};
  cfg.cells.forEach(c => {{ byKey[c.abbr + "|" + c.position] = c; }});

  const labelW = 54, headH = 22, rowH = 24, gap = 2;
  const cellW = Math.floor((820 - labelW) / positions.length) - gap;
  const width = labelW + positions.length * (cellW + gap);
  const height = headH + teams.length * rowH;

  const panel = container.closest(".panel");
  const headEl = panel ? panel.querySelector("h2") : null;
  const blurbEl = panel ? panel.querySelector(".blurb") : null;
  const defaultHead = headEl ? headEl.textContent : "";
  const defaultBlurb = blurbEl ? blurbEl.textContent : "";
  if (headEl) headEl.setAttribute("aria-live", "polite");

  const chartMount = document.createElement("div");
  container.appendChild(chartMount);
  const caption = document.createElement("p");
  caption.className = "compare-caption";
  container.appendChild(caption);

  const maxAbs = Math.max(
    ...cfg.cells.filter(c => c.enough).map(c => Math.abs(c.value)), 0.01);
  let activeKey = null;

  function fillFor(c) {{
    if (!c || !c.enough) return "var(--surface-2)";
    const t = Math.min(1, Math.abs(c.value) / maxAbs);
    // Floor the opacity so a near-zero cell is still visibly "measured".
    // Amber 201,138,46 (#C98A2E) is the project's positive/emphasis colour as
    // of round 20. This literal was still the retired blue #2a78d6 until round
    // 22 -- it's an rgba() built at runtime for the opacity ramp, so it never
    // read var(--series-1) and the round-20 sweep missed it. The Position Gaps
    // grid was the last chart in the project still painting positive values
    // blue.
    return (c.value < 0 ? "rgba(227, 73, 72, " : "rgba(201, 138, 46, ")
           + (0.15 + 0.85 * t).toFixed(3) + ")";
  }}

  function renderOnce() {{
    chartMount.innerHTML = "";
    const svg = el("svg", {{width: width, height: height}});
    chartMount.appendChild(svg);

    const emphKey = activeKey || cfg.emphasisKey;

    positions.forEach((p, j) => {{
      const t = el("text", {{class: "axis-label", x: labelW + j * (cellW + gap) + cellW / 2,
                            y: headH - 8, "text-anchor": "middle"}});
      t.textContent = p;
      svg.appendChild(t);
    }});

    teams.forEach((team, i) => {{
      const y = headH + i * rowH;
      const lbl = el("text", {{class: "bar-label", x: labelW - 10,
                              y: y + rowH / 2 + 4, "text-anchor": "end"}});
      lbl.textContent = team.abbr;
      svg.appendChild(lbl);

      positions.forEach((p, j) => {{
        const key = team.abbr + "|" + p;
        const c = byKey[key];
        const x = labelW + j * (cellW + gap);
        const isEmph = key === emphKey;
        const rect = el("rect", {{
          x: x, y: y + 1, width: cellW, height: rowH - 3, rx: 2,
          fill: fillFor(c),
          stroke: isEmph ? "var(--text-primary)" : "none",
          "stroke-width": isEmph ? 2 : 0,
        }});
        rect.style.cursor = c && c.enough ? "pointer" : "default";
        if (c) {{
          rect.addEventListener("mouseenter", (ev) => showTooltip(c.tooltip, ev));
          rect.addEventListener("mousemove", moveTooltip);
          rect.addEventListener("mouseleave", hideTooltip);
          if (c.enough) {{
            rect.addEventListener("click", (ev) => {{
              ev.stopPropagation();
              activeKey = (activeKey === key) ? null : key;
              renderOnce();
            }});
          }}
        }}
        svg.appendChild(rect);
      }});
    }});

    svg.addEventListener("click", (ev) => {{
      if (ev.target === svg && activeKey !== null) {{ activeKey = null; renderOnce(); }}
    }});

    const shown = activeKey ? byKey[activeKey] : null;
    if (headEl && blurbEl) {{
      headEl.textContent = shown && shown.headline ? shown.headline : defaultHead;
      blurbEl.textContent = shown && shown.story ? shown.story : defaultBlurb;
    }}
    caption.textContent = (shown && shown.caption) || cfg.defaultCaption || "";
  }}

  renderOnce();
}}

function drawShotMap(container, cfg) {{
  // Pitch diagram in StatsBomb's coordinate system (0-120 long, 0-80
  // wide), shots normalized to attack rightward so they cluster near the
  // right-hand goal regardless of which literal end they were taken at.
  // Filled dot = goal, hollow dot = anything else; dot radius scales with
  // xG, so a glance at size alone tells you how "clean" a chance was.
  const margin = {{top: 10, right: 16, bottom: 16, left: 16}};
  const width = 720;
  const height = width * (80 / 120);
  const svg = el("svg", {{width: width + margin.left + margin.right, height: height + margin.top + margin.bottom}});
  const g = el("g", {{transform: `translate(${{margin.left}},${{margin.top}})`}});
  svg.appendChild(g);
  container.appendChild(svg);

  const xScale = v => (v / 120) * width;
  const yScale = v => (v / 80) * height;

  // pitch outline + key markings (attacking half is what matters here, but
  // draw the full pitch for context/orientation)
  g.appendChild(el("rect", {{class: "pitch-outline", x: 0, y: 0, width: width, height: height, rx: 2}}));
  g.appendChild(el("line", {{class: "pitch-line", x1: xScale(60), x2: xScale(60), y1: 0, y2: height}}));
  g.appendChild(el("circle", {{class: "pitch-line", cx: xScale(60), cy: yScale(40), r: xScale(10) - xScale(0)}}));
  // 18-yard box + 6-yard box + goal, right-hand (attacking) end only
  g.appendChild(el("rect", {{class: "pitch-line", x: xScale(102), y: yScale(18), width: xScale(18) - xScale(0), height: yScale(62) - yScale(18)}}));
  g.appendChild(el("rect", {{class: "pitch-line", x: xScale(114), y: yScale(30), width: xScale(6) - xScale(0), height: yScale(50) - yScale(30)}}));
  g.appendChild(el("line", {{class: "pitch-outline", x1: width, x2: width, y1: yScale(36), y2: yScale(44), stroke: "var(--series-1)", "stroke-width": 3}}));

  const hasHighlight = cfg.data.some(d => d.highlight);
  const maxXg = Math.max(...cfg.data.map(d => d.xg)) || 0.1;

  cfg.data.forEach(d => {{
    // normalize direction: shots taken in the defensive half are mirrored
    // so every shot renders as if attacking the same (right-hand) goal
    const flip = d.x < 60;
    const px = flip ? 120 - d.x : d.x;
    const py = flip ? 80 - d.y : d.y;
    const isMuted = hasHighlight && !d.highlight;
    const r = 4 + Math.sqrt(d.xg / maxXg) * 11;
    const dot = el("circle", {{
      class: "shot-dot " + (d.outcome === "Goal" ? "goal" : "no-goal") + (isMuted ? " muted" : ""),
      cx: xScale(px), cy: yScale(py), r: r,
    }});
    dot.addEventListener("mouseenter", (event) => showTooltip(d.tooltip, event));
    dot.addEventListener("mousemove", moveTooltip);
    dot.addEventListener("mouseleave", hideTooltip);
    g.appendChild(dot);

    if (d.highlight && d.annotation) {{
      const anchorRight = xScale(px) < width - 160;
      const anno = el("text", {{
        class: "annotation", x: xScale(px) + (anchorRight ? r + 8 : -(r + 8)), y: yScale(py) + 4,
        "text-anchor": anchorRight ? "start" : "end",
      }});
      anno.textContent = d.annotation;
      g.appendChild(anno);
    }}
  }});

  const legend = document.createElement("div");
  legend.className = "legend";
  legend.innerHTML = `
    <div class="legend-item"><span class="legend-swatch" style="background:var(--series-1);"></span>Goal</div>
    <div class="legend-item"><span class="legend-swatch" style="background:var(--surface-1); border:1.5px solid var(--series-1);"></span>No goal</div>
    <div class="legend-item">Dot size = xG</div>
  `;
  container.insertBefore(legend, svg);
}}

// Methods & Data: prose, not a chart. It renders here rather than living in a
// separate README because the question it answers ("what am I actually looking
// at?") is asked while looking at the charts, and an answer one click away in
// the same page is the only version anyone reads.
function drawMethods(container, cfg) {{
  (cfg.sections || []).forEach(section => {{
    const h = document.createElement("h3");
    h.className = "methods-heading";
    h.textContent = section.heading;
    container.appendChild(h);
    const dl = document.createElement("dl");
    dl.className = "methods-list";
    (section.items || []).forEach(item => {{
      const dt = document.createElement("dt");
      dt.textContent = item.term;
      const dd = document.createElement("dd");
      dd.innerHTML = item.detail;
      dl.appendChild(dt);
      dl.appendChild(dd);
    }});
    container.appendChild(dl);
  }});

  if (cfg.downloads && cfg.downloads.length) {{
    const h = document.createElement("h3");
    h.className = "methods-heading";
    h.textContent = "Download the underlying data";
    container.appendChild(h);
    const note = document.createElement("p");
    note.className = "blurb";
    note.textContent = "The exact rows these charts were drawn from, as CSV. Nothing is fetched — the data is already in this page, so these work offline and will keep working if the API changes.";
    container.appendChild(note);
    const row = document.createElement("div");
    row.className = "download-row";
    cfg.downloads.forEach(dl => {{
      const btn = document.createElement("button");
      btn.className = "download-btn";
      btn.textContent = `${{dl.label}} (CSV)`;
      btn.addEventListener("click", () => {{
        // Blob + object URL rather than a data: URI: data URIs hit length
        // limits in some browsers at full-league size, and an object URL also
        // lets the download carry a real filename. Revoked on the next tick so
        // the page doesn't leak a URL per click.
        const blob = new Blob([dl.csv], {{type: "text/csv;charset=utf-8"}});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = dl.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 0);
      }});
      row.appendChild(btn);
    }});
    container.appendChild(row);
  }}
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
    // On phones the tab bar is a single horizontally-scrolling row, so a tab
    // near the end can be selected while only half visible. inline:"nearest"
    // pulls it fully into the strip; block:"nearest" stops the page itself
    // from jumping vertically at the same time.
    if (btn.scrollIntoView) btn.scrollIntoView({{block: "nearest", inline: "nearest"}});
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
  if (chart.type === "line") drawLine(mount, chart);
  if (chart.type === "season-compare") drawSeasonCompare(mount, chart);
  if (chart.type === "preset-compare") drawPresetCompare(mount, chart);
  if (chart.type === "position-grid") drawPositionGrid(mount, chart);
  if (chart.type === "shot-map") drawShotMap(mount, chart);
  if (chart.type === "methods") drawMethods(mount, chart);
}});
</script>
</body>
</html>
"""


DEFAULT_SOURCE_CREDIT = "American Soccer Analysis (americansocceranalysis.com)"


DEFAULT_SOCIAL_IMAGE_FILENAME = "social-card.png"


def _social_meta_block(title, subtitle, page_url=None, social_image=None,
                       social_description=None):
    """Build the <meta> block that decides what a shared link looks like.

    Without this, pasting the dashboard URL into X/Bluesky/LinkedIn/Slack
    renders a bare blue link with no title, description or picture, which is
    the single biggest reason a link post gets scrolled past.

    og:title and og:description are safe to emit unconditionally (they're
    just the page's own title and subtitle). og:url and og:image are NOT --
    both must be absolute URLs to work, and there is no way to derive them
    from inside a generated file, so they're emitted only when the caller
    passes page_url. A relative og:image is silently ignored by every
    scraper, which fails invisibly; omitting it at least degrades to a
    title-and-description card that still renders.
    """
    desc = social_description or subtitle
    e = _html.escape
    lines = [
        f'<meta name="description" content="{e(desc, quote=True)}">',
        f'<meta property="og:title" content="{e(title, quote=True)}">',
        f'<meta property="og:description" content="{e(desc, quote=True)}">',
        '<meta property="og:type" content="website">',
    ]
    if page_url:
        base = page_url if page_url.endswith("/") else page_url + "/"
        image_url = social_image or (base + DEFAULT_SOCIAL_IMAGE_FILENAME)
        lines.append(f'<meta property="og:url" content="{e(page_url, quote=True)}">')
        lines.append(f'<meta property="og:image" content="{e(image_url, quote=True)}">')
        lines.append('<meta property="og:image:width" content="1200">')
        lines.append('<meta property="og:image:height" content="630">')
        lines.append('<meta name="twitter:card" content="summary_large_image">')
        lines.append(f'<meta name="twitter:image" content="{e(image_url, quote=True)}">')
    else:
        # No absolute URL available, so a large-image card would render an
        # empty box. A plain summary card is the honest fallback.
        lines.append('<meta name="twitter:card" content="summary">')
    lines.append(f'<meta name="twitter:title" content="{e(title, quote=True)}">')
    lines.append(f'<meta name="twitter:description" content="{e(desc, quote=True)}">')
    return "".join(line + "\n" for line in lines)


def render_dashboard(title, subtitle, charts, story=None, source_credit=None,
                     generated_at=None, page_url=None, social_image=None,
                     social_description=None):
    """charts: list of dicts matching the JS CHARTS shape. tooltip fields
    must be pre-rendered HTML strings per point (see build helpers below).
    story: optional short dashboard-level narrative (see
    chart_builders.build_story_lede) rendered as a highlighted block between
    the header and the tab bar -- the same insight-led storytelling
    convention used on every chart, just applied once for the whole page.
    Omitted entirely (no empty block left behind) if None/empty.

    source_credit: who to credit for the underlying data, rendered once as a
    "Data: {source_credit}" footer at the bottom of the page (Karla, muted,
    same treatment as a chart footnote -- see the Design Guidelines doc).
    Defaults to American Soccer Analysis, since that's this project's primary
    source and every caller that doesn't override it (build_dashboard.py,
    demo_dashboard.py) is 100% ASA data. Callers whose data comes from
    somewhere else entirely -- build_shot_map_chart.py (StatsBomb),
    build_historical_trend_chart.py (nwslR) -- MUST pass their own
    source_credit here, or this footer would misattribute their page to ASA
    even though the per-chart footnote already names the real source.

    page_url / social_image / social_description: control the Open Graph +
    Twitter card meta tags -- what a shared link looks like when it's pasted
    into X, Bluesky, LinkedIn, Slack or iMessage. page_url should be the
    absolute URL the page is published at; without it, og:url and og:image
    are omitted rather than emitted as relative paths that every scraper
    silently drops (see _social_meta_block). social_image defaults to
    "<page_url>/social-card.png"; social_description defaults to the
    subtitle, and build_dashboard.py passes the week's story lede instead so
    the preview text changes with the data."""
    if story:
        story_block = (
            '  <div class="story">\n'
            '    <p class="kicker">This week in the NWSL</p>\n'
            f'    <p class="story-lede">{story}</p>\n'
            '  </div>\n'
        )
    else:
        story_block = ""
    credit = source_credit if source_credit is not None else DEFAULT_SOURCE_CREDIT
    # A page of season-to-date figures with no build date is unciteable -- a
    # reader can't tell whether they're looking at last night's result or a
    # month-old snapshot, and every number here moves weekly. Defaulting to
    # "now" rather than leaving it blank means a caller that forgets to pass
    # one still produces an honest page.
    stamp = generated_at or _dt.datetime.now().strftime("%d %B %Y, %H:%M %Z").strip()
    source_credit_block = f"Data: {credit}. Built {stamp}."
    social_meta = _social_meta_block(
        title, subtitle, page_url=page_url, social_image=social_image,
        social_description=social_description,
    )
    return PAGE_TEMPLATE.format(
        title=title, subtitle=subtitle, charts_json=json.dumps(charts), story_block=story_block,
        source_credit_block=source_credit_block, social_meta=social_meta,
    )
