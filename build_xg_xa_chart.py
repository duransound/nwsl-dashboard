"""
Builds an interactive NWSL xGoals-vs-xAssists bubble chart as a single
self-contained HTML file.

Live mode (run on your own machine, unrestricted network):
    pip install requests
    python build_xg_xa_chart.py --season 2026 --minutes 500

This calls the ASA API directly (players/xgoals already includes xassists,
so no separate endpoint is needed), resolves player names, and writes
xg_xa_chart.html with the full qualifying player pool embedded.

ABOUT THE MARKERS
------------------
Real team logo images would make great markers, but this project's cloud
sandbox couldn't fetch them (Wikimedia Commons' file/API endpoints were
blocked by its network allowlist, and the sandbox can't reach
app.americansocceranalysis.com or Commons directly by design). What ships
here instead: a round badge per player showing their team's abbreviation.

To swap in real logos once you're running this locally: fill in the
`TEAM_LOGOS` dict below with `"ABBR": "path/or/url/to/logo.png"` for each
team (a transparent PNG works best), and the chart will use
`<image>` (clipped to a circle) instead of the text badge for any team
that has an entry. Good sources: each team's official press/media kit page,
or Wikipedia's team infobox crest (save the image locally rather than
hot-linking it).

Round 10 (2026-08-12): restyled to the project's Design Guidelines doc --
this was the other chart flagged as "not yet redone" alongside the round-1
matplotlib charts. Now: Karla/Space Grotesk typography matching the main
dashboard (same Google Fonts link + system-sans fallback stack), xG/xA
shown per 96 minutes instead of season totals (matching the per-96
convention established everywhere else in this project), a single
highlighted story point (the most balanced dual threat, same "min(xg96,
xa96)" logic as chart_builders.py's Compare Teammates chart) with everything
else muted to gray, and the same pairwise bubble-collision avoidance the
main dashboard's scatter charts use (this standalone script predates that
addition, so bubbles could previously overlap at a dense cluster).
"""

import argparse
import json
import sys

import requests

BASE_URL = "https://app.americansocceranalysis.com/api/v1/nwsl"

# Fill in to use real logos, e.g. "WAS": "logos/washington_spirit.png"
TEAM_LOGOS = {}

TEAM_ABBR = {
    "2lqRn34qr0": "DEN", "315VnJ759x": "BAY", "4JMAk47qKg": "HOU",
    "4wM4rZdqjB": "KC", "7VqG1lYMvW": "SD", "7vQ7BBzqD1": "SEA",
    "KPqjw8PQ6v": "CHI", "Pk5LeeNqOW": "POR", "XVqKeVKM01": "ORL",
    "aDQ0lzvQEv": "WAS", "eV5D2w9QKn": "UTA", "eV5DR6YQKn": "LOU",
    "kRQa8JOqKZ": "LA", "raMyrr25d2": "NJY", "zeQZeazqKw": "NC",
    "odMX2OJqYL": "BOS",
}


def fetch_live(season: str, minimum_minutes: int):
    xg = requests.get(f"{BASE_URL}/players/xgoals",
                       params={"season_name": season, "minimum_minutes": minimum_minutes},
                       timeout=30).json()
    players = requests.get(f"{BASE_URL}/players", timeout=60).json()
    name_by_id = {p["player_id"]: p["player_name"] for p in players}

    rows = []
    for row in xg:
        minutes = row["minutes"]
        rows.append({
            "player": name_by_id.get(row["player_id"], row["player_id"]),
            "team": TEAM_ABBR.get(row["team_id"], row["team_id"]),
            "minutes": minutes,
            "xg": round(row["xgoals"], 3),
            "xa": round(row["xassists"], 3),
            "xg96": round(per96(row["xgoals"], minutes), 4),
            "xa96": round(per96(row["xassists"], minutes), 4),
            "goals": row["goals"],
        })
    return rows


def per96(value, minutes):
    return (value / minutes * 96) if minutes else 0.0


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Karla:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --series-1: #2a78d6;
    --series-1-ink: #ffffff;
    --font-body: 'Karla', system-ui, -apple-system, "Segoe UI", sans-serif;
    --font-head: 'Space Grotesk', system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  body {{ margin: 0; font-family: var(--font-body); background: #f9f9f7; }}
  .viz-root {{ background: var(--surface-1); max-width: 900px; margin: 24px auto; padding: 24px 28px 28px; border-radius: 12px; }}
  h1 {{ font-family: var(--font-head); font-weight: 500; font-size: 18px; color: var(--text-primary); margin: 0 0 6px; line-height: 1.35; }}
  .subtitle {{ font-size: 12.5px; color: var(--text-secondary); margin: 0 0 18px; max-width: 640px; }}
  .axis path, .axis line {{ stroke: var(--baseline); }}
  .axis text {{ fill: var(--text-muted); font-size: 11px; }}
  .gridline {{ stroke: var(--grid); stroke-width: 1px; }}
  .axis-label {{ fill: var(--text-secondary); font-size: 12px; }}
  .bubble {{ fill: var(--series-1); stroke: var(--surface-1); stroke-width: 2px; cursor: pointer; }}
  .bubble.muted {{ fill: var(--baseline); }}
  .bubble:hover, .bubble.hover {{ fill: #1c5cab; }}
  .badge-text {{ fill: var(--series-1-ink); font-size: 9.5px; font-weight: 600; text-anchor: middle; pointer-events: none; }}
  .badge-text.muted {{ fill: var(--text-secondary); }}
  .annotation {{ fill: var(--text-primary); font-size: 11.5px; font-weight: 600; font-family: var(--font-body); }}
  .tooltip {{
    position: absolute; pointer-events: none; background: var(--text-primary); color: #fff;
    padding: 8px 10px; border-radius: 6px; font-size: 12px; line-height: 1.5; opacity: 0;
    transition: opacity 0.1s ease; box-shadow: 0 4px 14px rgba(0,0,0,0.18); max-width: 220px;
    font-family: var(--font-body);
  }}
  .tooltip .name {{ font-weight: 600; margin-bottom: 2px; }}
  .tooltip .row {{ color: #d8d8d4; }}
  .footnote {{ font-size: 11px; color: var(--text-muted); margin-top: 14px; }}
</style>
</head>
<body>
<div class="viz-root">
  <h1>{title}</h1>
  <p class="subtitle">{subtitle}</p>
  <div id="chart"></div>
  <p class="footnote">{footnote}</p>
  <div class="tooltip" id="tooltip"></div>
</div>
<script>
const data = {data_json};
const highlightName = {highlight_json};

const margin = {{top: 16, right: 24, bottom: 46, left: 54}};
const width = 820 - margin.left - margin.right;
const height = 560 - margin.top - margin.bottom;
const R = 16;

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

const svgNS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {{
  const e = document.createElementNS(svgNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}}

function niceMax(v) {{
  // round up to a clean-ish tick boundary
  const step = v <= 5 ? 0.5 : v <= 10 ? 1 : v <= 20 ? 2 : 5;
  return Math.ceil((v * 1.15) / step) * step;
}}

const xMax = niceMax(Math.max(...data.map(d => d.xg96)));
const yMax = niceMax(Math.max(...data.map(d => d.xa96)));

function xScale(v) {{ return (v / xMax) * width; }}
function yScale(v) {{ return height - (v / yMax) * height; }}

function ticksFor(maxVal) {{
  const count = 8;
  const raw = maxVal / count;
  const step = raw <= 0.5 ? 0.5 : raw <= 1 ? 1 : raw <= 2 ? 2 : Math.ceil(raw / 5) * 5;
  const out = [];
  for (let t = 0; t <= maxVal + 1e-6; t += step) out.push(Math.round(t * 100) / 100);
  return out;
}}

const svg = el("svg", {{
  width: width + margin.left + margin.right,
  height: height + margin.top + margin.bottom,
}});
document.getElementById("chart").appendChild(svg);

const g = el("g", {{transform: `translate(${{margin.left}},${{margin.top}})`}});
svg.appendChild(g);

const xTicks = ticksFor(xMax);
const yTicks = ticksFor(yMax);

xTicks.forEach(t => {{
  g.appendChild(el("line", {{class: "gridline", x1: xScale(t), x2: xScale(t), y1: 0, y2: height}}));
}});
yTicks.forEach(t => {{
  g.appendChild(el("line", {{class: "gridline", x1: 0, x2: width, y1: yScale(t), y2: yScale(t)}}));
}});

const xAxis = el("g", {{class: "axis", transform: `translate(0,${{height}})`}});
xTicks.forEach(t => {{
  const txt = el("text", {{x: xScale(t), y: 18, "text-anchor": "middle"}});
  txt.textContent = t;
  xAxis.appendChild(txt);
}});
xAxis.appendChild(el("line", {{x1: 0, x2: width, y1: 0, y2: 0}}));
g.appendChild(xAxis);

const yAxis = el("g", {{class: "axis"}});
yTicks.forEach(t => {{
  const txt = el("text", {{x: -10, y: yScale(t) + 4, "text-anchor": "end"}});
  txt.textContent = t;
  yAxis.appendChild(txt);
}});
yAxis.appendChild(el("line", {{x1: 0, x2: 0, y1: 0, y2: height}}));
g.appendChild(yAxis);

const xLabel = el("text", {{class: "axis-label", x: width / 2, y: height + 38, "text-anchor": "middle"}});
xLabel.textContent = "xGoals per 96 min";
g.appendChild(xLabel);

const yLabel = el("text", {{class: "axis-label", transform: `rotate(-90)`, x: -height / 2, y: -40, "text-anchor": "middle"}});
yLabel.textContent = "xAssists per 96 min";
g.appendChild(yLabel);

const tooltip = document.getElementById("tooltip");

// true data positions, then nudge apart only enough to stop bubble overlap
// (same approach as the main dashboard's scatter charts -- this standalone
// chart predates that addition, so dense clusters could previously overlap)
const points = data.map(d => ({{x: xScale(d.xg96), y: yScale(d.xa96), d}}));
resolveCollisions(points, R, 3);

points.forEach(p => {{
  const d = p.d;
  const isHighlight = d.player === highlightName;
  const isMuted = highlightName && !isHighlight;
  const node = el("g", {{class: "player-node", transform: `translate(${{p.x}},${{p.y}})`}});
  const circle = el("circle", {{class: "bubble" + (isMuted ? " muted" : ""), r: R}});
  const label = el("text", {{class: "badge-text" + (isMuted ? " muted" : ""), dy: "0.32em", "text-anchor": "middle"}});
  label.textContent = d.team;
  node.appendChild(circle);
  node.appendChild(label);

  if (isHighlight) {{
    const anno = el("text", {{class: "annotation", x: R + 8, y: 4, "text-anchor": "start"}});
    anno.textContent = `${{d.player.split(" ").slice(-1)[0]}}: ${{d.xg96.toFixed(2)}} xG/96, ${{d.xa96.toFixed(2)}} xA/96`;
    node.appendChild(anno);
  }}

  g.appendChild(node);

  node.addEventListener("mouseenter", () => {{
    circle.classList.add("hover");
    tooltip.innerHTML =
      `<div class="name">${{d.player}}</div>` +
      `<div class="row">${{d.team}} &middot; ${{d.minutes}} min</div>` +
      `<div class="row">xG/96 ${{d.xg96.toFixed(2)}} &middot; xA/96 ${{d.xa96.toFixed(2)}} &middot; Goals ${{d.goals}}</div>`;
    tooltip.style.opacity = 1;
  }});
  node.addEventListener("mousemove", (event) => {{
    tooltip.style.left = (event.pageX + 14) + "px";
    tooltip.style.top = (event.pageY - 10) + "px";
  }});
  node.addEventListener("mouseleave", () => {{
    circle.classList.remove("hover");
    tooltip.style.opacity = 0;
  }});
}});
</script>
</body>
</html>
"""


def build_html(rows, season, minimum_minutes, live: bool):
    n = len(rows)
    # Story point: the most balanced dual threat -- same "highest of the
    # lower of the two rates" logic chart_builders.py uses for the main
    # dashboard's xG-vs-xA tab, so the two charts pick highlights the same
    # way even though this one isn't built from chart_builders.py.
    most_balanced = max(rows, key=lambda r: min(r["xg96"], r["xa96"])) if rows else None
    title = (f"NWSL {season}: {most_balanced['player']} is the most balanced dual threat"
              if most_balanced else f"NWSL {season}: xGoals vs. xAssists")
    subtitle = (f"Players with {minimum_minutes}+ minutes, shown per 96 minutes so players with different "
                f"minutes played are compared fairly &middot; {n} qualifying players &middot; hover a bubble for details")
    if live:
        footnote = "Round badges show team abbreviation. Fill in TEAM_LOGOS in build_xg_xa_chart.py to use real logo images instead."
    else:
        footnote = (f"Demo dataset: top {n} players by combined xG+xA among those with {minimum_minutes}+ minutes "
                    "(2026 season in progress, snapshot). Run with --live for the complete qualifying pool.")
    html = HTML_TEMPLATE.format(
        title=title, subtitle=subtitle, footnote=footnote,
        data_json=json.dumps(rows),
        highlight_json=json.dumps(most_balanced["player"] if most_balanced else None),
    )
    return html


def main():
    parser = argparse.ArgumentParser(description="Build the NWSL xG-vs-xA interactive chart.")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--minutes", type=int, default=500)
    parser.add_argument("--out", default="xg_xa_chart.html")
    args = parser.parse_args()

    print(f"Fetching NWSL {args.season} player xG/xA data (min {args.minutes} minutes)...")
    rows = fetch_live(args.season, args.minutes)
    html = build_html(rows, args.season, args.minutes, live=True)
    with open(args.out, "w") as f:
        f.write(html)
    print(f"Wrote {args.out} with {len(rows)} players.")


if __name__ == "__main__":
    sys.exit(main())
