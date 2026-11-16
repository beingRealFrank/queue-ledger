"""Build the static site (docs/) from data/: index.html, feed.xml, large-load page."""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import os
import sys
from collections import Counter
from email.utils import format_datetime

REPO = "beingRealFrank/queue-ledger"
SITE = "https://beingrealfrank.github.io/queue-ledger/"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/"

root = sys.argv[1] if len(sys.argv) > 1 else "."
data = os.path.join(root, "data")
docs = os.path.join(root, "docs")
os.makedirs(docs, exist_ok=True)
e = html.escape


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


latest = read(os.path.join(data, "latest", "all.csv"))
changes = read(os.path.join(data, "changes", "all_changes.csv"))
status = json.load(open(os.path.join(data, "status.json")))
today = status["date"]

counts = Counter(r["iso"] for r in latest)
active_mw = Counter()
for r in latest:
    st = r["status"].lower()
    if "withdrawn" in st or st.startswith("0 ") or "done" in st or "commercial" in st or "in service" in st:
        continue
    try:
        active_mw[r["iso"]] += float(r["mw"] or 0)
    except ValueError:
        pass

since = (dt.date.fromisoformat(today) - dt.timedelta(days=30)).isoformat()
recent = [c for c in changes if c["date"] >= since]
recent.sort(key=lambda c: (c["date"], c["iso"], c["queue_id"]), reverse=True)
ev_counts = Counter((c["iso"], c["event"]) for c in recent)



def describe(c):
    if c["event"] == "new":
        return "New queue entry"
    if c["event"] == "removed_from_report":
        return "Dropped from the published report"
    return f"{c['field']}: {c['old'] or '∅'} → {c['new'] or '∅'}"


def row(c):
    name = c["project_name"] or c["poi"] or ""
    return (f"<tr><td>{e(c['date'])}</td><td>{e(c['iso'])}</td><td><code>{e(c['queue_id'])}</code></td>"
            f"<td>{e(name)}</td><td>{e(c['fuel'] or c['technology'])}</td><td class=n>{e(c['mw'])}</td>"
            f"<td>{e(c['county'])}{', ' if c['county'] and c['state'] else ''}{e(c['state'])}</td><td>{e(describe(c))}</td></tr>")


CSS = """
body{font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;max-width:1100px;margin:0 auto;padding:24px;color:#1b1f23}
h1{margin:0 0 4px;font-size:28px} h2{margin-top:36px;border-bottom:1px solid #ddd;padding-bottom:4px}
.sub{color:#555;margin:0 0 20px} table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid #eee;padding:5px 6px;text-align:left;vertical-align:top} th{background:#f6f8fa}
td.n,th.n{text-align:right} code{font-size:12px} .tiles{display:flex;gap:12px;flex-wrap:wrap}
.tile{border:1px solid #ddd;border-radius:8px;padding:10px 14px;min-width:150px}
.tile b{display:block;font-size:22px} .muted{color:#666;font-size:13px} a{color:#0550ae}
.box{background:#f6f8fa;border-radius:8px;padding:12px 16px}
"""


def page(title, body, desc):
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name=description content="{e(desc)}">
<link rel=alternate type=application/rss+xml title="Queue Ledger changes" href="{SITE}feed.xml">
<style>{CSS}</style></head><body>{body}
<p class=muted style="margin-top:40px">Queue Ledger is an independent archive of public records and is not affiliated with or endorsed by EIA, CAISO or SPP.
Data is provided as-is, with no warranty; check the linked source file before relying on any row.
Source code and data: <a href="https://github.com/{REPO}">github.com/{REPO}</a>.</p></body></html>"""


groups = Counter((r["iso"], r["record_type"]) for r in latest)
tiles = "".join(
    f"<div class=tile>{e(iso)} · {e(rt.replace('_', ' '))}<b>{n:,}</b></div>" for (iso, rt), n in sorted(groups.items()))
src_rows = "".join(
    f"<tr><td>{e(k.upper())}</td><td>{'ok' if v['ok'] else 'error'}</td><td>{e(v.get('fetched_at',''))}</td>"
    f"<td><code>{e(v.get('sha256','')[:16])}</code></td><td>{'new file' if v.get('new_content') else 'unchanged'}</td>"
    f"<td><a href=\"{e(v.get('url',''))}\">source</a></td></tr>"
    for k, v in sorted(status["sources"].items()))
ev_summary = ", ".join(f"{iso} {ev.replace('_', ' ')}: {n}" for (iso, ev), n in sorted(ev_counts.items())) or \
    "No changes recorded yet: the archive started on 2026-11-13, so the first daily diffs appear from the next run."
recent_html = "".join(row(c) for c in recent[:400])

index = f"""
<h1>Queue Ledger</h1>
<p class=sub>A point-in-time archive of US power-project pipelines — the EIA-860M inventory of every planned, operating,
retired and canceled US generator, plus the CAISO and SPP interconnection queues — with every status change and slipped
in-service date logged, and the original source file and its SHA-256 kept for each snapshot.</p>
<div class=tiles>{tiles}</div>
<p class=muted>Snapshot {e(today)} · {len(latest):,} records · <a href="feed.xml">RSS</a></p>

<h2>Why</h2>
<p>These sources are published as a single current file that is replaced each day or month. The history — when a
project appeared, when its operating date slipped, when it was quietly canceled — is lost unless someone captures every
version. Queue Ledger does that, so you can answer "what did the source say on date X" with the exact file that was
published, and see the change log in between. It is a leading indicator of generation and storage buildout.</p>

<h2>Last 30 days of changes</h2>
<p class=muted>{e(ev_summary)}</p>
<table><tr><th>Date</th><th>ISO</th><th>Queue ID</th><th>Project / POI</th><th>Fuel</th><th class=n>MW</th><th>Location</th><th>Change</th></tr>
{recent_html}</table>

<h2>Download (free)</h2>
<ul>
<li><a href="{RAW}data/latest/all.csv">latest/all.csv</a> — every record, one schema, all sources</li>
<li><a href="{RAW}data/changes/all_changes.csv">changes/all_changes.csv</a> — the full change log (new, changed field old→new, dropped)</li>
<li><a href="{RAW}data/manifest.jsonl">manifest.jsonl</a> — provenance: URL, fetch time, SHA-256, HTTP validators for every capture</li>
<li><a href="https://github.com/{REPO}/tree/main/data/raw">raw/</a> — the original source files, gzipped, one per distinct version</li>
<li><a href="state/">Planned projects by state</a>: every planned US generator in each state, with a CSV and change history</li>
<li><a href="https://apify.com/civic_data_feeds/us-power-plant-pipeline">US Power Plant Pipeline on Apify</a>: pull the same EIA-860M generators as JSON from code or no-code tools, pay per result ($4 per 1,000)</li>
<li><a href="https://www.kaggle.com/datasets/beingrealfrank/us-power-plant-pipeline-eia-860m">Kaggle mirror</a> of the latest EIA-860M generator table, updated on each EIA release</li>
<li>Every day is a git commit, so <code>git log -- data/latest/caiso.csv</code> gives the queue as of any day.</li>
</ul>

<h2>Sources (today's run)</h2>
<table><tr><th>Source</th><th>Status</th><th>Fetched (UTC)</th><th>SHA-256</th><th>Content</th><th></th></tr>{src_rows}</table>
<p class=muted>Every source is a public file fetched without logging in, only from paths its site's robots.txt allows,
and only where the publisher's terms allow automated access.</p>

<h2>Licences and credit</h2>
<ul>
<li><b>EIA-860M</b>: U.S. government data in the public domain. Source: U.S. Energy Information Administration, Preliminary
Monthly Electric Generator Inventory (Form EIA-860M), with the release month as given in each raw file.</li>
<li><b>CAISO</b>: Source: the California ISO, Public Queue Report. Credit the California ISO when you reuse it; its
copyright notices are kept in the raw files.</li>
<li><b>SPP</b>: Source: Southwest Power Pool, Generation Interconnection active queue. SPP's terms allow copying with
citation but require SPP's written authorization for commercial use, so the SPP rows here are for non-commercial use.</li>
<li>Code: MIT. The change logs and normalized tables add no restrictions beyond those of each source.</li>
</ul>
<div class=box><p>Need filtered alerts (e.g. every new planned plant over 100&nbsp;MW in a set of states, or every
operating-date slip), a backfill, or a source we don't cover yet?
<a href="https://github.com/{REPO}/issues/new?template=feed-request.yml">Open a request</a>; requests are answered in writing.</p></div>
"""
open(os.path.join(docs, "index.html"), "w").write(page(
    "Queue Ledger — point-in-time archive of US power-project pipelines (EIA-860M, CAISO, SPP)", index,
    "Snapshots and change log of the EIA-860M planned generator inventory and the CAISO and SPP interconnection queues, with source files and SHA-256 provenance."))

# RSS: one item per day with changes, plus one per new large load
items = []
by_day = Counter(c["date"] for c in changes)
for day in sorted(by_day, reverse=True)[:30]:
    day_ev = [c for c in changes if c["date"] == day]
    summ = Counter((c["iso"], c["event"]) for c in day_ev)
    desc = "; ".join(f"{iso} {ev.replace('_', ' ')}: {n}" for (iso, ev), n in sorted(summ.items()))
    big = [c for c in day_ev if c["event"] == "new" and c["mw"].replace(".", "").isdigit() and float(c["mw"]) >= 100]
    if big:
        desc += ". New ≥100 MW: " + "; ".join(f"{c['iso']} {c['queue_id']} {c['project_name'] or c['poi']} {c['fuel']} {c['mw']} MW {c['county']} {c['state']}".strip() for c in big[:25])
    pub = format_datetime(dt.datetime.fromisoformat(day + "T14:00:00+00:00"))
    items.append(f"<item><title>Queue changes {day}: {len(day_ev)} events</title><link>{SITE}#{day}</link>"
                 f"<guid isPermaLink=\"false\">queue-ledger-{day}</guid><pubDate>{pub}</pubDate><description>{e(desc)}</description></item>")
feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Queue Ledger — power-project pipeline changes</title><link>{SITE}</link>
<description>Changes to US power-project pipelines: EIA-860M planned generators and CAISO and SPP queues.</description>{''.join(items)}</channel></rss>
"""
open(os.path.join(docs, "feed.xml"), "w").write(feed)
open(os.path.join(docs, ".nojekyll"), "w").write("")
open(os.path.join(docs, "sitemap.xml"), "w").write(
    '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f'<url><loc>{SITE}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url></urlset>')
print("site built:", len(latest), "entries,", len(recent), "recent changes")
