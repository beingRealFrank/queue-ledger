"""Build per-state planned-project pages (EIA-860M only) and rewrite docs/sitemap.xml.

Run after collector/site.py:  python collector/pages.py <root>
Reads data/latest/eia860m.csv, data/status.json and (if present) data/changes/all_changes.csv.
Writes docs/state/<ST>.html, docs/state/<ST>.csv, docs/state/index.html and docs/sitemap.xml
(index + every state page + any docs/changes/*.html). Standard library only.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
DATA = os.path.join(ROOT, "data")
DOCS = os.path.join(ROOT, "docs")
SITE = "https://beingrealfrank.github.io/queue-ledger/"
REPO = "https://github.com/beingRealFrank/queue-ledger"
APIFY = "https://apify.com/civic_data_feeds/us-power-plant-pipeline"
e = html.escape

STATES = {
    "AK": "Alaska", "AL": "Alabama", "AR": "Arkansas", "AZ": "Arizona", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DC": "District of Columbia", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "IA": "Iowa", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine",
    "MI": "Michigan", "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "MT": "Montana",
    "NC": "North Carolina", "ND": "North Dakota", "NE": "Nebraska", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VA": "Virginia", "VT": "Vermont", "WA": "Washington",
    "WI": "Wisconsin", "WV": "West Virginia", "WY": "Wyoming",
}
STATUS_LABEL = {"P": "Planned, approvals not started", "L": "Approvals pending", "T": "Approvals received",
                "U": "Under construction (50% or less)", "V": "Under construction (over 50%)",
                "TS": "Construction complete, not yet operating"}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from person import looks_like_person  # noqa: E402


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def mw(r):
    try:
        return float(r.get("mw") or 0)
    except ValueError:
        return 0.0


def fmt_mw(x):
    return f"{x:,.0f}" if x >= 10 else f"{x:,.1f}"


def code(r):
    m = re.match(r"^\((\w+)\)", r.get("status", ""))
    return m.group(1) if m else ""


status = json.load(open(os.path.join(DATA, "status.json")))
today = status["date"]
eia_url = status["sources"].get("eia860m", {}).get("url", "")
m = re.search(r"/([a-z]+)_generator(\d{4})\.xlsx", eia_url)
release = f"{m.group(1).capitalize()} {m.group(2)}" if m else today
rows = [r for r in read(os.path.join(DATA, "latest", "eia860m.csv")) if r["record_type"] == "planned"]
for r in rows:
    if looks_like_person(r["developer"]):
        r["developer"] = ""
changes = [c for c in read(os.path.join(DATA, "changes", "all_changes.csv")) if c["iso"] == "EIA-860M"]
by_state = defaultdict(list)
for r in rows:
    if r["state"] in STATES:
        by_state[r["state"]].append(r)
chg_state = defaultdict(list)
for c in changes:
    chg_state[c["state"]].append(c)

CSS = """
body{font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;max-width:1100px;margin:0 auto;padding:24px;color:#1b1f23}
h1{margin:0 0 4px;font-size:26px} h2{margin-top:30px;border-bottom:1px solid #ddd;padding-bottom:4px}
.sub{color:#555;margin:0 0 18px} table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid #eee;padding:5px 6px;text-align:left;vertical-align:top} th{background:#f6f8fa;cursor:pointer}
td.n,th.n{text-align:right} .muted{color:#666;font-size:13px} a{color:#0550ae}
.tiles{display:flex;gap:12px;flex-wrap:wrap} .tile{border:1px solid #ddd;border-radius:8px;padding:8px 14px}
.tile b{display:block;font-size:20px}
"""
SORT_JS = """<script>
document.querySelectorAll('table.sort th').forEach(function(th,i){th.addEventListener('click',function(){
var t=th.closest('table'),b=t.tBodies[0],rs=Array.prototype.slice.call(b.rows),d=th.dataset.d=th.dataset.d==='1'?'-1':'1';
rs.sort(function(a,c){var x=a.cells[i].dataset.v||a.cells[i].textContent,y=c.cells[i].dataset.v||c.cells[i].textContent,
nx=parseFloat(x),ny=parseFloat(y);if(!isNaN(nx)&&!isNaN(ny))return(nx-ny)*d;return x.localeCompare(y)*d;});
rs.forEach(function(r){b.appendChild(r);});});});
</script>"""
FOOT = (f'<p class=muted style="margin-top:36px">Source: U.S. Energy Information Administration, Preliminary Monthly Electric '
        f'Generator Inventory (Form EIA-860M), {e(release)} release; public domain. Preliminary data, so check the raw file in the '
        f'<a href="{REPO}">archive</a> before relying on a row. Not affiliated with or endorsed by EIA. '
        f'Back to <a href="{SITE}">Queue Ledger</a>. Query the same data from code: '
        f'<a href="{APIFY}">US Power Plant Pipeline on Apify</a>.</p>')


def page(title, desc, body, ld, path):
    doc = (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
           f'<meta name=viewport content="width=device-width,initial-scale=1"><title>{e(title)}</title>'
           f'<meta name=description content="{e(desc)}"><link rel=canonical href="{SITE}{path}">'
           f"<style>{CSS}</style>"
           f'<script type="application/ld+json">{json.dumps(ld).replace("</", "<\\/")}</script></head>'
           f"<body>{body}{FOOT}{SORT_JS}</body></html>")
    full = os.path.join(DOCS, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(doc)


CSV_FIELDS = ["queue_id", "project_name", "developer", "technology", "fuel", "mw", "state", "county",
              "status", "proposed_cod", "latitude", "longitude"]
urls = [""]
index_rows = []
os.makedirs(os.path.join(DOCS, "state"), exist_ok=True)
for st in sorted(by_state):
    name = STATES[st]
    rs = sorted(by_state[st], key=mw, reverse=True)
    total = sum(mw(r) for r in rs)
    tech = Counter()
    techn = Counter()
    for r in rs:
        tech[r["technology"]] += mw(r)
        techn[r["technology"]] += 1
    codes = Counter(code(r) for r in rs)
    with open(os.path.join(DOCS, "state", f"{st}.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rs)
    tiles = "".join(f"<div class=tile>{e(t)}<b>{fmt_mw(v)} MW</b><span class=muted>{techn[t]} projects</span></div>"
                    for t, v in tech.most_common(6))
    status_li = "".join(f"<li>{e(STATUS_LABEL.get(c, c))} ({e(c)}): {n}</li>" for c, n in sorted(codes.items()))
    trs = "".join(
        f"<tr><td>{e(r['project_name'])}</td><td>{e(r['developer'])}</td><td>{e(r['technology'])}</td>"
        f"<td class=n data-v=\"{mw(r)}\">{fmt_mw(mw(r))}</td><td>{e(r['county'])}</td>"
        f"<td>{e(STATUS_LABEL.get(code(r), r['status']))}</td><td>{e(r['proposed_cod'])}</td></tr>" for r in rs)
    sc = sorted(chg_state.get(st, []), key=lambda c: c["date"], reverse=True)
    if sc:
        chg = ("<h2>Changes since the previous release</h2><table><tr><th>Date</th><th>Plant</th><th>Change</th></tr>" + "".join(
            f"<tr><td>{e(c['date'])}</td><td>{e(c['project_name'])}</td><td>"
            f"{e('new project' if c['event'] == 'new' else c['field'] + ': ' + c['old'] + ' to ' + c['new'] if c['event'] == 'changed' else 'dropped from the report')}"
            f"</td></tr>" for c in sc[:200]) + "</table>")
    else:
        chg = ("<h2>Changes since the previous release</h2><p class=muted>None recorded yet. Queue Ledger started "
               "capturing EIA-860M in November 2026; changes appear after the next monthly release.</p>")
    body = (f"<h1>Planned power plants in {e(name)}</h1>"
            f"<p class=sub>{len(rs):,} planned projects, {fmt_mw(total)} MW, from the EIA-860M {e(release)} release. "
            f"<a href=\"{st}.csv\">Download CSV</a> · <a href=\"./\">All states</a></p>"
            f"<div class=tiles>{tiles}</div><h2>Where they are in the process</h2><ul>{status_li}</ul>"
            f"<h2>All planned projects</h2><table class=sort><tr><th>Project</th><th>Owner</th><th>Technology</th>"
            f"<th class=n>MW</th><th>County</th><th>Status</th><th>Planned operation</th></tr>{trs}</table>{chg}")
    ld = {"@context": "https://schema.org", "@type": "Dataset",
          "name": f"Planned power plants in {name} (EIA-860M, {release})",
          "description": f"Every planned US generator of 1 MW or more in {name} from EIA Form EIA-860M, with owner, "
                         f"technology, capacity, county, status and planned operating month.",
          "url": f"{SITE}state/{st}.html", "license": "https://creativecommons.org/publicdomain/zero/1.0/",
          "creator": {"@type": "Person", "name": "Frank Gilroy"},
          "isBasedOn": "https://www.eia.gov/electricity/data/eia860m/",
          "temporalCoverage": f"{today[:4]}/..", "spatialCoverage": {"@type": "Place", "name": f"{name}, United States"},
          "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": f"{SITE}state/{st}.csv"}]}
    page(f"Planned power plants in {name} (EIA-860M, {release})",
         f"{len(rs)} planned power plants in {name}, {fmt_mw(total)} MW: owner, technology, county, status and planned "
         f"operating month from EIA-860M.", body, ld, f"state/{st}.html")
    urls.append(f"state/{st}.html")
    index_rows.append((st, name, len(rs), total, tech.most_common(1)[0][0] if tech else ""))

irs = "".join(f"<tr><td><a href=\"{st}.html\">{e(n)}</a></td><td class=n data-v=\"{c}\">{c:,}</td>"
              f"<td class=n data-v=\"{t}\">{fmt_mw(t)}</td><td>{e(top)}</td></tr>"
              for st, n, c, t, top in sorted(index_rows, key=lambda x: -x[3]))
ibody = (f"<h1>Planned power plants by state</h1><p class=sub>{sum(x[2] for x in index_rows):,} planned US generators, "
         f"{fmt_mw(sum(x[3] for x in index_rows))} MW, EIA-860M {e(release)} release. Each state page has a project table, "
         f"a CSV download and the change history.</p><table class=sort><tr><th>State</th><th class=n>Projects</th>"
         f"<th class=n>MW</th><th>Largest technology (MW)</th></tr>{irs}</table>")
ild = {"@context": "https://schema.org", "@type": "Dataset", "name": f"Planned US power plants by state (EIA-860M, {release})",
       "description": "Planned US generators of 1 MW or more by state, from EIA Form EIA-860M.",
       "url": f"{SITE}state/", "license": "https://creativecommons.org/publicdomain/zero/1.0/",
       "creator": {"@type": "Person", "name": "Frank Gilroy"}, "isBasedOn": "https://www.eia.gov/electricity/data/eia860m/",
       "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv",
                         "contentUrl": "https://raw.githubusercontent.com/beingRealFrank/queue-ledger/main/data/latest/eia860m.csv"}]}
page(f"Planned power plants by state (EIA-860M, {release})", "Planned US power plants by state: projects, MW and technology from EIA-860M.",
     ibody, ild, "state/index.html")
urls.insert(1, "state/")

# Sitemap: index, state pages, and any monthly change pages already built.
for fn in sorted(os.listdir(os.path.join(DOCS, "changes"))) if os.path.isdir(os.path.join(DOCS, "changes")) else []:
    if fn.endswith(".html"):
        urls.append(f"changes/{fn}" if fn != "index.html" else "changes/")
sm = "\n" + "\n".join(f"<url><loc>{SITE}{u}</loc><lastmod>{today}</lastmod></url>" for u in urls) + "\n"
with open(os.path.join(DOCS, "sitemap.xml"), "w") as f:
    f.write(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
print(f"state pages: {len(index_rows)}, sitemap urls: {len(urls)}, planned rows: {len(rows)}")
