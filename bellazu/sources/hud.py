"""HUD Small Area Fair Market Rents (FY2026, ZIP level). Free xlsx download, no token.
(The HUD FMR *API* needs a free token; the downloadable file does not.)"""
import pandas as pd
from ..http import fetch, cache_file

URL = "https://www.huduser.gov/portal/datasets/fmr/fmr2026/fy2026_safmrs_revised.xlsx"
_df = None


def _load():
    global _df
    if _df is not None:
        return _df
    p = cache_file("hud/fy2026_safmrs_revised.xlsx")
    if not p.exists():
        raw = fetch(URL, "hud:safmr_xlsx", ttl_hours=24 * 365, binary=True, timeout=120)
        if raw is None:
            return None
        p.write_bytes(raw)
    df = pd.read_excel(p, engine="openpyxl")
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    df["zip"] = df[df.columns[0]].astype(str).str.zfill(5)
    _df = df
    return df


def safmr(zipcode):
    df = _load()
    if df is None or not zipcode:
        return None
    r = df[df.zip == str(zipcode)[:5].zfill(5)]
    if r.empty:
        return None
    r = r.iloc[0]
    return {"zip": str(zipcode)[:5], "area": r["HUD Fair Market Rent Area Name"],
            **{f"{b}br": int(r[f"SAFMR {b}BR"]) for b in range(5)},
            "source": "HUD FY2026 Small Area FMR (40th-percentile gross rent incl. utilities): " + URL}
