"""Queue Ledger collector.

Fetches public, logged-out US grid interconnection queue reports, stores each raw
file with provenance (URL, fetch time, sha256, HTTP validators), normalizes them
into one schema, and writes a dated change log against the previous snapshot.

Usage: python collector/collect.py [--root .] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys
import ssl
import urllib.request

import certifi

import pandas as pd

UA = "QueueLedger/1.0 (public-records archiver; https://github.com/beingRealFrank/queue-ledger)"

FIELDS = [
    "iso", "queue_id", "record_type", "project_name", "developer", "status",
    "fuel", "technology", "mw", "state", "county", "poi", "utility",
    "queue_date", "proposed_cod", "withdrawn_date", "end_use", "source_sheet", "latitude", "longitude",
]
# Fields whose change we report as an event.
TRACKED = ["record_type", "status", "mw", "proposed_cod", "withdrawn_date", "project_name", "developer", "poi"]


def http_get(url: str, timeout: int = 120) -> tuple[bytes, dict]:
    import http.cookiejar
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context(cafile=certifi.where())
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                                         urllib.request.HTTPSHandler(context=ctx))
    with opener.open(req, timeout=timeout) as r:
        body = r.read()
        if body[:2] == b"\x1f\x8b":  # Wayback sometimes returns the stored gzip stream as-is
            body = gzip.decompress(body)
        hdr = {k: r.headers.get(k) for k in ("Last-Modified", "ETag", "Content-Type") if r.headers.get(k)}
        return body, hdr


# ---------------------------------------------------------------- helpers

def clean(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v).strip()
    s = re.sub(r"\s+", " ", s)
    if s.lower() in ("nan", "nat", "none"):
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]00:00:00(\+00:00)?", s):
        return s[:10]
    return s


def num(v) -> str:
    s = clean(v).replace(",", "")
    try:
        f = float(s)
    except ValueError:
        return s
    return ("%.3f" % f).rstrip("0").rstrip(".")


def date(v) -> str:
    if isinstance(v, (pd.Timestamp, dt.datetime, dt.date)):
        return clean(v)
    s = clean(v)
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T.*", s)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"(\d{1,2})-(\d{4})", s)  # NYISO "04-2028"
    if m:
        return "%s-%02d" % (m.group(2), int(m.group(1)))
    return s


def read_sheet(xls: pd.ExcelFile, sheet: str, first_col_re: str) -> pd.DataFrame:
    """Read a sheet whose header row is the first row with a cell matching first_col_re."""
    raw = pd.read_excel(xls, sheet, header=None, dtype=object)
    for i in range(min(60, len(raw))):
        if any(re.fullmatch(first_col_re, clean(v), re.I) for v in raw.iloc[i].tolist()):
            cols = [clean(c) or f"_c{j}" for j, c in enumerate(raw.iloc[i].tolist())]
            df = raw.iloc[i + 1:].copy()
            df.columns = cols
            return df
    raise ValueError(f"header not found in {sheet!r}")


def col(df: pd.DataFrame, *patterns: str):
    for p in patterns:
        for c in df.columns:
            if re.search(p, c, re.I):
                return c
    return None


def rows(df, mapping, base):
    out = []
    cols = {k: (col(df, *v) if isinstance(v, tuple) else None) for k, v in mapping.items()}
    for _, r in df.iterrows():
        rec = dict(base)
        for k, v in mapping.items():
            if isinstance(v, tuple):
                c = cols[k]
                val = r[c] if c is not None else ""
            else:
                val = v(r) if callable(v) else v
            if k == "mw":
                rec[k] = num(val)
            elif k in ("queue_date", "proposed_cod", "withdrawn_date"):
                rec[k] = date(val)
            else:
                rec[k] = clean(val)
        if rec.get("queue_id") and len(rec["queue_id"]) <= 40 and not rec["queue_id"].endswith(":"):
            out.append(rec)
    return out


# ---------------------------------------------------------------- sources

def parse_spp(data: bytes):
    text = data.decode("utf-8-sig", "replace")
    lines = text.splitlines()
    df = pd.read_csv(io.StringIO("\n".join(lines[1:])), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return rows(df, {
        "queue_id": (r"^Generation Interconnection Number$",), "status": (r"^Status$",),
        "fuel": (r"^Fuel Type$",), "technology": (r"^Generation Type$",), "mw": (r"^Capacity$",),
        "state": (r"^State$",), "county": (r"Nearest Town or County",), "poi": (r"Substation or Line",),
        "utility": (r"^TO at POI$",), "queue_date": (r"^Request Received$",),
        "proposed_cod": (r"^Commercial Operation Date$", r"In-Service Date"),
        "withdrawn_date": (r"^Date Withdrawn$",),
    }, {"iso": "SPP", "record_type": "generation", "project_name": "", "developer": "", "end_use": "",
        "source_sheet": "GenerateActiveCSV"})


def parse_caiso(data: bytes):
    xls = pd.ExcelFile(io.BytesIO(data))
    out = []
    for sheet in xls.sheet_names:
        df = read_sheet(xls, sheet, r"Project Name.*")
        out += rows(df, {
            "queue_id": (r"^Queue Position$",), "project_name": (r"^Project Name",),
            "status": (r"^Application Status$",), "fuel": (r"^Fuel-1$",), "technology": (r"^Type-1$",),
            "mw": (r"^Net MWs to Grid$",), "state": (r"^State$",), "county": (r"^County$",),
            "poi": (r"Station or Transmission Line",), "utility": (r"^Utility$",),
            "queue_date": (r"^Queue Date$",), "proposed_cod": (r"^Current On-line Date",),
            "withdrawn_date": (r"^Withdrawn Date$",),
        }, {"iso": "CAISO", "record_type": "generation", "developer": "", "end_use": "", "source_sheet": sheet})
    return out


EIA_INDEX = "https://www.eia.gov/electricity/data/eia860m/"
EIA_SHEETS = {"Planned": "planned", "Canceled or Postponed": "canceled_or_postponed",
              "Retired": "retired", "Operating": "operating"}


def eia860m_url() -> str:
    """Newest monthly EIA-860M file linked from EIA's index page (robots.txt disallows the archive/ paths, so
    only the current files under xls/ are used)."""
    body, _ = http_get(EIA_INDEX)
    links = re.findall(r'href="(/electricity/data/eia860m/xls/[a-z]+_generator(\d{4})\.xlsx)"', body.decode("utf-8", "replace"))
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
              "october", "november", "december"]
    def key(link):
        m = re.search(r"/([a-z]+)_generator(\d{4})", link[0])
        return (int(m.group(2)), months.index(m.group(1)) if m.group(1) in months else -1)
    for path, _y in sorted(set(links), key=key, reverse=True):
        url = "https://www.eia.gov" + path
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as r:
                if r.status == 200 and r.geturl() == url:
                    return url
        except Exception:
            continue
    raise ValueError("no downloadable EIA-860M file linked from the index")


def parse_eia860m(data: bytes):
    xls = pd.ExcelFile(io.BytesIO(data))
    out = []
    for sheet, kind in EIA_SHEETS.items():
        if sheet not in xls.sheet_names:
            continue
        df = read_sheet(xls, sheet, r"Entity ID")
        df = df[pd.to_numeric(df["Plant ID"], errors="coerce").notna()]
        df["_qid"] = df["Plant ID"].map(lambda v: num(v)) + "-" + df["Generator ID"].map(clean)
        ycol = col(df, r"^(Planned )?Operation Year$", r"^Operating Year$")
        mcol = col(df, r"^(Planned )?Operation Month$", r"^Operating Month$")
        df["_cod"] = [
            "%d-%02d" % (int(float(y)), int(float(m))) if num(y).isdigit() and num(m).isdigit() else num(y)
            for y, m in zip(df[ycol] if ycol else [""] * len(df), df[mcol] if mcol else [""] * len(df))
        ]
        out += rows(df, {
            "queue_id": (r"^_qid$",), "project_name": (r"^Plant Name$",), "developer": (r"^Entity Name$",),
            "status": (r"^Status$",) if col(df, r"^Status$") else (lambda r, k=kind: k.replace("_", " ")),
            "fuel": (r"^Energy Source Code$",), "technology": (r"^Technology$",),
            "mw": (r"^Nameplate Capacity \(MW\)$",), "state": (r"^Plant State$",), "county": (r"^County$",),
            "poi": (r"^Plant ID$",), "utility": (r"^Balancing Authority Code$",),
            "proposed_cod": (r"^_cod$",), "withdrawn_date": (r"^Retirement Year$",),
            "latitude": (r"^Latitude$",), "longitude": (r"^Longitude$",),
        }, {"iso": "EIA-860M", "record_type": kind, "queue_date": "", "end_use": "", "source_sheet": sheet})
    return out


SOURCES = {
    "spp": ("https://opsportal.spp.org/Studies/GenerateActiveCSV", "csv", parse_spp),
    "caiso": ("http://www.caiso.com/PublishedDocuments/PublicQueueReport.xlsx", "xlsx", parse_caiso),
    "eia860m": (eia860m_url, "xlsx", parse_eia860m),
}


# ---------------------------------------------------------------- pipeline

def load_csv(path):
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as f:
        return {(r["iso"], r["queue_id"]): r for r in csv.DictReader(f)}


def write_csv(path, recs, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)


def dedupe(recs):
    """Same queue id can appear on several sheets (e.g. active + withdrawn); keep the first."""
    seen, out = set(), []
    for r in recs:
        k = (r["iso"], r["queue_id"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def diff(prev: dict, cur: dict, day: str):
    ev = []
    for k, r in cur.items():
        if k not in prev:
            ev.append({"date": day, "event": "new", **{f: r.get(f, "") for f in FIELDS}, "field": "", "old": "", "new": ""})
            continue
        p = prev[k]
        for f in TRACKED:
            if p.get(f, "") != r.get(f, ""):
                ev.append({"date": day, "event": "changed", **{x: r.get(x, "") for x in FIELDS},
                           "field": f, "old": p.get(f, ""), "new": r.get(f, "")})
    for k, p in prev.items():
        if k not in cur:
            ev.append({"date": day, "event": "removed_from_report", **{f: p.get(f, "") for f in FIELDS},
                       "field": "", "old": "", "new": ""})
    return ev


EVENT_FIELDS = ["date", "event"] + FIELDS + ["field", "old", "new"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    root, day = a.root, a.date
    data = os.path.join(root, "data")
    manifest = os.path.join(data, "manifest.jsonl")
    status = {}
    all_events = []
    for name, (url, ext, parser) in SOURCES.items():
        if a.only and name not in a.only:
            continue
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        try:
            u = url() if callable(url) else url
            body, hdr = http_get(u)
            recs = dedupe(parser(body))
            if len(recs) < 20:
                raise ValueError(f"only {len(recs)} records parsed")
        except Exception as e:  # keep going; one source down must not stop the others
            status[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300], "fetched_at": fetched_at}
            print(f"[{name}] FAILED {e}", file=sys.stderr)
            continue
        sha = hashlib.sha256(body).hexdigest()
        rawdir = os.path.join(data, "raw", name)
        os.makedirs(rawdir, exist_ok=True)
        rawpath = os.path.join(rawdir, f"{day}_{sha[:12]}.{ext}.gz")
        known = any(fn.endswith(f"_{sha[:12]}.{ext}.gz") for fn in os.listdir(rawdir))
        if not known:
            with open(rawpath, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as g:
                g.write(body)
        else:
            rawpath = os.path.join(rawdir, next(fn for fn in os.listdir(rawdir) if fn.endswith(f"_{sha[:12]}.{ext}.gz")))
        with open(manifest, "a") as m:
            m.write(json.dumps({"source": name, "url": u, "fetched_at": fetched_at, "sha256": sha,
                                "bytes": len(body), "http": hdr, "raw": os.path.relpath(rawpath, root),
                                "new_content": not known, "records": len(recs)}) + "\n")
        latest = os.path.join(data, "latest", f"{name}.csv")
        prev = load_csv(latest)
        cur = {(r["iso"], r["queue_id"]): r for r in recs}
        ev = diff(prev, cur, day) if prev else []
        write_csv(latest, recs, FIELDS)
        all_events += ev
        status[name] = {"ok": True, "records": len(recs), "events": len(ev), "sha256": sha,
                        "new_content": not known, "fetched_at": fetched_at, "url": u}
        print(f"[{name}] {len(recs)} records, {len(ev)} events, new_content={not known}")

    if all_events:
        write_csv(os.path.join(data, "changes", f"{day}.csv"), all_events, EVENT_FIELDS)
        allpath = os.path.join(data, "changes", "all_changes.csv")
        exists = os.path.exists(allpath)
        with open(allpath, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=EVENT_FIELDS, extrasaction="ignore")
            if not exists:
                w.writeheader()
            w.writerows(all_events)
    # combined latest
    combined = []
    for fn in sorted(os.listdir(os.path.join(data, "latest"))):
        if fn.endswith(".csv") and fn != "all.csv":
            combined += list(load_csv(os.path.join(data, "latest", fn)).values())
    write_csv(os.path.join(data, "latest", "all.csv"), combined, FIELDS)
    with open(os.path.join(data, "status.json"), "w") as f:
        json.dump({"date": day, "sources": status}, f, indent=1, sort_keys=True)
    if not any(s["ok"] for s in status.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
