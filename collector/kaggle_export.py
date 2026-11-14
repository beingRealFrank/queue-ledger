"""Write kaggle/eia860m_generators_latest.csv from data/latest/eia860m.csv (run before `kaggle datasets version`)."""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from person import looks_like_person  # noqa: E402

root = sys.argv[1] if len(sys.argv) > 1 else "."
d = pd.read_csv(f"{root}/data/latest/eia860m.csv", dtype=str)
d = d.rename(columns={"queue_id": "plant_generator_id", "developer": "entity_name", "project_name": "plant_name",
                      "utility": "balancing_authority", "poi": "plant_id", "proposed_cod": "operation_date",
                      "withdrawn_date": "retirement_year", "record_type": "inventory", "fuel": "energy_source_code",
                      "mw": "nameplate_mw"})
d["entity_name"] = d["entity_name"].map(lambda v: "" if isinstance(v, str) and looks_like_person(v) else v)
cols = ["plant_generator_id", "plant_id", "plant_name", "entity_name", "inventory", "status", "technology",
        "energy_source_code", "nameplate_mw", "state", "county", "balancing_authority", "operation_date",
        "retirement_year", "latitude", "longitude"]
d[cols].to_csv(f"{root}/kaggle/eia860m_generators_latest.csv", index=False)
src = [json.loads(l) for l in open(f"{root}/data/manifest.jsonl") if '"eia860m"' in l][-1]["url"]
print("exported", len(d), "rows from", src)
