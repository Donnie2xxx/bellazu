"""HUD Small Area Fair Market Rents (FY2026, ZIP level). Free xlsx download, no token.
(The HUD FMR *API* needs a free token; the downloadable file does not.)"""
import gzip, json, pathlib
import pandas as pd
from ..http import fetch, cache_file

URL = "https://www.huduser.gov/portal/datasets/fmr/fmr2026/fy2026_safmrs_revised.xlsx"
_df = None


COMPACT = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "hud_safmr_fy2026.json.gz"


def build_compact():
    """One-time: the 4 MB xlsx (5-10 s to open with openpyxl) -> a small gzip JSON {zip: [area, 0BR..4BR]} (first row per ZIP,
    same as the lookup below). Run: python3 -m bellazu.sources.hud"""
    df = _load_xlsx()
    out = {}
    for _, r in df.iterrows():
        z = r["zip"]
        if z not in out:
            out[z] = [r["HUD Fair Market Rent Area Name"]] + [None if pd.isna(r[f"SAFMR {b}BR"]) else int(r[f"SAFMR {b}BR"]) for b in range(5)]
    COMPACT.write_bytes(gzip.compress(json.dumps(out, separators=(",", ":")).encode(), 9))
    return len(out)


def _load_xlsx():
    p = cache_file("hud/fy2026_safmrs_revised.xlsx")
    if not p.exists():
        raw = fetch(URL, "hud:safmr_xlsx", ttl_hours=24 * 365, binary=True, timeout=120)
        if raw is None:
            return None
        p.write_bytes(raw)
    df = pd.read_excel(p, engine="openpyxl")
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    df["zip"] = df[df.columns[0]].astype(str).str.zfill(5)
    return df


def _load():
    """{zip: [area, 0BR..4BR]} from the compact file (fast), else built from the xlsx. Loaded once per process."""
    global _df
    if _df is not None:
        return _df
    if COMPACT.exists():
        try:
            _df = json.loads(gzip.decompress(COMPACT.read_bytes()))
            return _df
        except Exception:
            pass
    df = _load_xlsx()
    if df is None:
        return None
    d = {}
    for z, a, *v in zip(df["zip"], df["HUD Fair Market Rent Area Name"], *[df[f"SAFMR {b}BR"] for b in range(5)]):
        if z not in d:
            d[z] = [a] + [None if pd.isna(x) else int(x) for x in v]
    _df = d
    return d


def safmr(zipcode):
    d = _load()
    if d is None or not zipcode:
        return None
    r = d.get(str(zipcode)[:5].zfill(5))
    if not r:
        return None
    return {"zip": str(zipcode)[:5], "area": r[0],
            **{f"{b}br": int(r[1 + b]) for b in range(5)},
            "source": "HUD FY2026 Small Area FMR (40th-percentile gross rent incl. utilities): " + URL}


if __name__ == "__main__":
    print("ZIPs:", build_compact(), "->", COMPACT)
