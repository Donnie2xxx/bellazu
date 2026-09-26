"""ACS 5-year median gross rent by bedrooms (table B25031) via Census Reporter API (free, no key).
The official api.census.gov now redirects keyless calls to a 'Missing Key' page (free key needed)."""
import json
from ..http import fetch

BR = {"all": "B25031001", 0: "B25031002", 1: "B25031003", 2: "B25031004", 3: "B25031005", 4: "B25031006", 5: "B25031007"}


def median_rent_by_beds(zipcode):
    if not zipcode:
        return None
    url = f"https://api.censusreporter.org/1.0/data/show/latest?table_ids=B25031&geo_ids=86000US{str(zipcode)[:5]}"
    txt = fetch(url, "census:censusreporter_acs", ttl_hours=24 * 60, ua="bot", min_interval=1)
    if not txt:
        return None
    try:
        d = json.loads(txt)
        est = list(d["data"].values())[0]["B25031"]["estimate"]
    except Exception:
        return None
    out = {("all" if k == "all" else f"{k}br"): est.get(v) for k, v in BR.items()}
    out["release"] = d.get("release", {}).get("name")
    out["note"] = "Median GROSS rent (rent+utilities) of ALL occupied rentals incl. long-time tenants; lags market asking rents; 3,501 = top-coded '3,500+'."
    out["source"] = url
    return out
