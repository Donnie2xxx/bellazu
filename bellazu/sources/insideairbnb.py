"""Inside Airbnb (insideairbnb.com) — free quarterly scrapes of Airbnb listings.

Occupancy method: Inside Airbnb's own "San Francisco model" columns
(estimated_occupancy_l365d / estimated_revenue_l365d): booked nights = reviews in last
12 months / review rate (50%) x average stay (3 nights, or the listing's minimum nights if
higher), capped at 70% (255 nights). Revenue = modeled nights x listed nightly price.
We also expose the calendar-based upper bound (1 - availability_365/365 = booked OR blocked).
Limitations: review rate is an assumption; price is a quote for one date window (not realized
ADR); excludes cleaning fees; hosts that block calendars look 'booked'; new listings are
under-counted; one snapshot per quarter.
"""
import re, io, gzip, pathlib, pickle, time
import pandas as pd
from ..http import fetch, cache_file, record
from ..geo import haversine_km

INDEX_URL = "https://insideairbnb.com/get-the-data/"
# approximate centres of nearby datasets (used only to decide which to load)
CENTERS = {
    ("nj", "jersey-city"): (40.7178, -74.0431),
    ("nj", "newark"): (40.7357, -74.1724),
    ("ny", "new-york-city"): (40.7580, -73.9855),
}
KEEP = ["id", "listing_url", "name", "latitude", "longitude", "neighbourhood_cleansed", "room_type",
        "property_type", "accommodates", "bedrooms", "bathrooms", "price", "minimum_nights",
        "availability_365", "number_of_reviews", "number_of_reviews_ltm", "reviews_per_month",
        "estimated_occupancy_l365d", "estimated_revenue_l365d", "review_scores_rating", "license", "picture_url",
        "last_scraped", "price_quote_checkin_date", "price_quote_checkout_date", "host_listings_count"]


def dataset_index():
    html = fetch(INDEX_URL, "insideairbnb:index", ttl_hours=24 * 7)
    idx = {}
    if not html:   # offline / blocked: fall back to snapshots already on disk (bundled with the web app)
        for pk in cache_file("insideairbnb/x").parent.glob("*_*_????-??-??.pkl"):
            m = re.match(r"([a-z]{2})_([a-z0-9-]+)_(\d{4}-\d{2}-\d{2})\.pkl$", pk.name)
            if m and (m.group(1), m.group(2)) not in idx or (m and m.group(3) > idx[(m.group(1), m.group(2))]):
                idx[(m.group(1), m.group(2))] = m.group(3)
        if idx:
            record("insideairbnb:index", INDEX_URL, True, "local", "index unreachable; using bundled snapshots")
        return idx
    for st, city, date in re.findall(r"https://data\.insideairbnb\.com/united-states/([a-z]{2})/([a-z0-9-]+)/(\d{4}-\d{2}-\d{2})/data/listings\.csv\.gz", html):
        k = (st, city)
        if k not in idx or date > idx[k]:
            idx[k] = date
    return idx


def load(state, city, date):
    pk = cache_file(f"insideairbnb/{state}_{city}_{date}.pkl")
    if pk.exists():
        return pickle.loads(pk.read_bytes())
    url = f"https://data.insideairbnb.com/united-states/{state}/{city}/{date}/data/listings.csv.gz"
    raw = fetch(url, "insideairbnb:listings", ttl_hours=24 * 120, binary=True, timeout=180)
    if raw is None:
        return None
    df = pd.read_csv(io.BytesIO(gzip.decompress(raw)), low_memory=False)
    df = df[[c for c in KEEP if c in df.columns]].copy()
    df["price_num"] = pd.to_numeric(df["price"].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    df["dataset"] = f"{state}/{city}/{date}"
    # own San-Francisco-model recompute for transparency
    stay = df["minimum_nights"].clip(lower=3).fillna(3)
    nights = (df["number_of_reviews_ltm"].fillna(0) / 0.5 * stay).clip(upper=255)
    df["sf_nights_recalc"] = nights
    df["cal_unavail_pct"] = 1 - df["availability_365"].fillna(365) / 365.0
    pk.write_bytes(pickle.dumps(df))
    return df


def nearby_datasets(lat, lon, max_km=35, state=None):
    """Datasets near a point. If state is given, prefer same-state datasets (an NJ town should not be
    priced off Manhattan listings across the river: different market AND different law)."""
    idx = dataset_index()
    out = []
    for (st, city), (clat, clon) in CENTERS.items():
        d = haversine_km(lat, lon, clat, clon)
        if d <= max_km and (st, city) in idx:
            out.append((d, st, city, idx[(st, city)]))
    if state:
        same = [x for x in out if x[1] == state.lower()]
        if same:
            out = same
    return sorted(out)


def comps(lat, lon, beds=None, room_type="Entire home/apt", radii=(1.0, 2.0, 3.5), min_n=8,
          min_reviews_ltm=1, max_min_nights=29, datasets=None, state=None, nearest_k=15, max_proxy_km=15):
    """Return dict with comps DataFrame + summary. max_min_nights=29 => true STR listings;
    set min_min_nights for mid-term (28+) comps via mtr_comps()."""
    frames = []
    for d, st, city, date in (datasets or nearby_datasets(lat, lon, state=state)):
        df = load(st, city, date)
        if df is not None:
            frames.append(df)
    if not frames:
        return {"ok": False, "reason": "no Inside Airbnb dataset near this location"}
    df = pd.concat(frames, ignore_index=True)
    df["dist_km"] = [haversine_km(lat, lon, a, b) for a, b in zip(df.latitude, df.longitude)]
    base = df[(df.room_type == room_type) & (df.price_num.notna()) &
              (df.minimum_nights <= max_min_nights) & (df.number_of_reviews_ltm.fillna(0) >= min_reviews_ltm)]
    chosen, used_r, bed_rule = None, None, None
    for rule in ("exact", "pm1"):
        for r in radii:
            sub = base[base.dist_km <= r]
            if beds is not None:
                if rule == "exact":
                    sub = sub[sub.bedrooms == beds]
                else:
                    sub = sub[(sub.bedrooms >= beds - 1) & (sub.bedrooms <= beds + 1)]
            if len(sub) >= min_n:
                chosen, used_r, bed_rule = sub, r, rule
                break
        if chosen is not None:
            break
    if chosen is None:  # PROXY: nearest-k same-bedroom listings within max_proxy_km
        sub = base[base.dist_km <= max_proxy_km]
        if beds is not None and (sub.bedrooms == beds).sum() >= 3:
            sub, bed_rule = sub[sub.bedrooms == beds], "exact (nearest-k proxy)"
        else:
            bed_rule = "any (nearest-k proxy)"
        chosen = sub.nsmallest(nearest_k, "dist_km")
        used_r = float(chosen.dist_km.max()) if len(chosen) else None
    chosen = chosen.sort_values("dist_km")
    return {"ok": len(chosen) > 0, "comps": chosen, "radius_km": used_r, "bed_rule": bed_rule,
            "nearest_km": float(df.dist_km.min()), "datasets": sorted(df.dataset.unique().tolist()),
            "summary": summarize(chosen)}


def summarize(c):
    if c is None or len(c) == 0:
        return {"n": 0}
    q = lambda s, p: float(s.quantile(p)) if s.notna().any() else None
    occ = c.estimated_occupancy_l365d / 365.0
    return {
        "n": int(len(c)),
        "adr_p25": q(c.price_num, .25), "adr_median": q(c.price_num, .5), "adr_p75": q(c.price_num, .75),
        "occ_median_sf_model": q(occ, .5), "occ_p25": q(occ, .25), "occ_p75": q(occ, .75),
        "revenue_p25": q(c.estimated_revenue_l365d, .25), "revenue_median": q(c.estimated_revenue_l365d, .5),
        "revenue_p75": q(c.estimated_revenue_l365d, .75),
        "cal_unavail_median": q(c.cal_unavail_pct, .5),
        "licensed_share": float(c.license.notna().mean()) if "license" in c else None,
    }


def mtr_comps(lat, lon, beds=None, radii=(1.0, 2.0, 3.5, 8.0, 15.0), min_n=5, state=None, room_type="Entire home/apt"):
    """Furnished 28+ night listings (mid-term rentals). Occupancy not modeled (few reviews)."""
    frames = []
    for d, st, city, date in nearby_datasets(lat, lon, state=state):
        df = load(st, city, date)
        if df is not None:
            frames.append(df)
    if not frames:
        return {"ok": False}
    df = pd.concat(frames, ignore_index=True)
    df["dist_km"] = [haversine_km(lat, lon, a, b) for a, b in zip(df.latitude, df.longitude)]
    base = df[(df.room_type == room_type) & df.price_num.notna() & (df.minimum_nights >= 28)]
    for r in radii:
        sub = base[base.dist_km <= r]
        if beds is not None:
            sub = sub[sub.bedrooms == beds]
        if len(sub) >= min_n:
            break
    return {"ok": len(sub) > 0, "n": int(len(sub)), "radius_km": r,
            "nightly_median": float(sub.price_num.median()) if len(sub) else None,
            "monthly_equiv_median": float(sub.price_num.median() * 30.4) if len(sub) else None,
            "monthly_equiv_p25": float(sub.price_num.quantile(.25) * 30.4) if len(sub) else None,
            "monthly_equiv_p75": float(sub.price_num.quantile(.75) * 30.4) if len(sub) else None,
            "datasets": sorted(df.dataset.unique().tolist()),
            "comps": sub.sort_values("dist_km")}
