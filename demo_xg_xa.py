"""
Generates the demo xG-vs-xA chart from real, individually-verified NWSL 2026
season data (pulled from the ASA API on 2026-08-11): top 20 players by
combined xG+xA among those with 500+ minutes played.
"""

from build_xg_xa_chart import build_html, per96

rows = [
    {"player": "Croix Bethune", "team": "WAS", "minutes": 1691, "xg": 5.903, "xa": 5.648, "goals": 3},
    {"player": "Sophia Wilson", "team": "POR", "minutes": 1636, "xg": 8.163, "xa": 3.200, "goals": 9},
    {"player": "Trinity Rodman", "team": "WAS", "minutes": 1774, "xg": 8.221, "xa": 2.542, "goals": 9},
    {"player": "Barbra Banda", "team": "ORL", "minutes": 1241, "xg": 8.409, "xa": 2.306, "goals": 12},
    {"player": "Aissata Traore", "team": "BOS", "minutes": 1410, "xg": 7.900, "xa": 1.529, "goals": 5},
    {"player": "Evelyn Ijeh", "team": "NC", "minutes": 1242, "xg": 8.157, "xa": 1.205, "goals": 9},
    {"player": "Cloe Lacasse", "team": "UTA", "minutes": 1769, "xg": 4.855, "xa": 4.140, "goals": 6},
    {"player": "Jordynn Dudley", "team": "NJY", "minutes": 1439, "xg": 5.366, "xa": 3.429, "goals": 3},
    {"player": "Mina Tanaka", "team": "UTA", "minutes": 1415, "xg": 5.221, "xa": 2.478, "goals": 5},
    {"player": "Olivia Moultrie", "team": "POR", "minutes": 1460, "xg": 5.073, "xa": 2.452, "goals": 5},
    {"player": "Leicy Santos", "team": "WAS", "minutes": 1664, "xg": 3.173, "xa": 3.845, "goals": 5},
    {"player": "Riley Jackson", "team": "NC", "minutes": 1767, "xg": 3.146, "xa": 3.703, "goals": 2},
    {"player": "Katherine Rader", "team": "HOU", "minutes": 1714, "xg": 4.849, "xa": 1.949, "goals": 7},
    {"player": "Debinha", "team": "KC", "minutes": 930, "xg": 4.101, "xa": 2.686, "goals": 4},
    {"player": "Amanda Santos", "team": "BOS", "minutes": 1066, "xg": 5.578, "xa": 1.185, "goals": 5},
    {"player": "Dudinha", "team": "SD", "minutes": 1247, "xg": 3.964, "xa": 2.791, "goals": 5},
    {"player": "Sveindís Jane Jónsdóttir", "team": "LA", "minutes": 1187, "xg": 4.667, "xa": 2.083, "goals": 6},
    {"player": "Jaedyn Shaw", "team": "NJY", "minutes": 1628, "xg": 4.164, "xa": 2.343, "goals": 5},
    {"player": "Lia Eugenia Godfrey", "team": "SD", "minutes": 1180, "xg": 4.056, "xa": 2.343, "goals": 5},
    {"player": "Maddie Mercado", "team": "SEA", "minutes": 1489, "xg": 5.129, "xa": 1.122, "goals": 5},
]
for r in rows:
    r["xg96"] = round(per96(r["xg"], r["minutes"]), 4)
    r["xa96"] = round(per96(r["xa"], r["minutes"]), 4)

html = build_html(rows, season="2026", minimum_minutes=500, live=False)
with open("xg_xa_chart_demo.html", "w") as f:
    f.write(html)
print(f"Wrote xg_xa_chart_demo.html with {len(rows)} players.")
