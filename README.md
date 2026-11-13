# Queue Ledger

A point-in-time archive of US power-project pipelines, with a change log and SHA-256 provenance for every source file.
Site: https://beingrealfrank.github.io/queue-ledger/

| Source | What | Cadence | Licence |
|---|---|---|---|
| EIA-860M | Every planned, operating, retired and canceled/postponed US generator ≥1 MW: owner, plant, county, coordinates, balancing authority, status, planned operating month | monthly (checked daily) | U.S. government, public domain. Credit: "Source: U.S. Energy Information Administration, Form EIA-860M (release month)" |
| CAISO | Public interconnection queue report (active, completed, withdrawn) | daily | Credit "the California ISO"; its notices are kept in the raw files |
| SPP | Generation interconnection active queue | daily | SPP terms: copying with citation is allowed; commercial use needs SPP's written authorization. SPP rows are non-commercial. |

Each source is a public file fetched without logging in, only from paths its robots.txt allows, and only where the
publisher's terms allow automated access. Other ISOs (MISO, ERCOT, NYISO, ISO-NE, PJM) are not included because their
terms or robots.txt do not clearly allow automated collection and republication.

## Data

| Path | What |
|---|---|
| `data/latest/all.csv` | Every record, all sources, one schema |
| `data/latest/<source>.csv` | Same, per source. Git history gives the data as of any day. |
| `data/changes/<date>.csv`, `all_changes.csv` | Events: `new`, `changed` (field, old, new), `removed_from_report` |
| `data/manifest.jsonl` | One line per fetch: source URL, UTC time, SHA-256, bytes, HTTP Last-Modified/ETag, raw path |
| `data/raw/<source>/<date>_<sha12>.<ext>.gz` | The original file, stored once per distinct version |
| `data/status.json` | Result of the latest run |

Schema: `iso, queue_id, record_type, project_name, developer, status, fuel, technology, mw, state, county, poi, utility,
queue_date, proposed_cod, withdrawn_date, end_use, source_sheet, latitude, longitude`. For EIA-860M, `queue_id` is
`<plant id>-<generator id>`, `developer` is the reporting entity, `utility` is the balancing authority, `record_type` is
the inventory sheet (planned, operating, retired, canceled_or_postponed) and a move between sheets is logged as a
`record_type` change. Fields a source does not publish are blank. Status values are the source's own.

## Code licence

MIT. No warranty: verify against the raw source file before relying on a row. Not affiliated with or endorsed by EIA,
CAISO or SPP.

## Requests

Filtered alerts, backfills or new sources: [open an issue](https://github.com/beingRealFrank/queue-ledger/issues/new?labels=request).

## Run locally

    uv run --with openpyxl --with pandas --with certifi python collector/collect.py --root .
    uv run python collector/site.py .
