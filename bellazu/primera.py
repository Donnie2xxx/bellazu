"""'Nuestra Primera Casa' (Our First Home): a shortlist of towns roughly midway between a work address in Wilmington DE
and Midtown Manhattan, with approximate drive times, short bilingual notes, and for-sale homes from RentCast (one lookup per city, 3-day cache).
Drive minutes = OSRM public router, off-peak, x0.78 (calibrated to Google off-peak in bella-plan/vecindarios); APPROXIMATE, not live.
Rush hour = a rough range of x1.3 to x1.6 of off-peak (not measured). Safety wording is hedged; sources named in SOURCES."""
import json, pathlib
from . import listings, keylock

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAIN = ROOT / "data" / "primera.json"        # source tree only (never shipped)
LOCK = ROOT / "data" / "primera.lock"         # what ships: the same JSON encrypted with the app passcode
_MEMO = {}


def load(passcode=None):
    """The personal part (dict) or None: plain JSON in the source tree, else the lock opened with the passcode."""
    try:
        if PLAIN.exists():
            return json.loads(PLAIN.read_text())
        if LOCK.exists() and passcode:
            if passcode not in _MEMO:
                t = keylock.unlock(json.loads(LOCK.read_text()), passcode)
                _MEMO.clear()
                _MEMO[passcode] = json.loads(t) if t else None
            return _MEMO[passcode]
    except Exception:
        return None
    return None


MIN_BEDS = 2
RUSH = (1.3, 1.6)

# slug, name, state, [RentCast cities], approx. minutes to the Wilmington work address, approx. minutes to Midtown Manhattan.
# The personal parts (who it is for, the work address, favorites, the budget and the notes per town) ship only encrypted: data/primera.lock.
TOWNS = [
    ('robbinsville', 'Robbinsville', 'NJ', ['Robbinsville'], 75, 66),
    ('moorestown', 'Moorestown', 'NJ', ['Moorestown'], 51, 88),
    ('mount_laurel', 'Mount Laurel', 'NJ', ['Mount Laurel'], 51, 87),
    ('cherry_hill', 'Cherry Hill', 'NJ', ['Cherry Hill'], 49, 85),
    ('lower_makefield', 'Lower Makefield (PA)', 'PA', ['Yardley'], 67, 80),
    ('yardley', 'Yardley (PA)', 'PA', ['Yardley'], 68, 76),
    ('bordentown', 'Bordentown', 'NJ', ['Bordentown'], 66, 73),
    ('middletown_pa', 'Middletown Twp (Langhorne, PA)', 'PA', ['Langhorne'], 61, 83),
    ('hamilton', 'Hamilton (Mercer)', 'NJ', ['Hamilton'], 72, 65),
    ('cinnaminson', 'Cinnaminson', 'NJ', ['Cinnaminson'], 48, 91),
    ('marlton', 'Marlton (Evesham)', 'NJ', ['Marlton'], 47, 89),
    ('medford', 'Medford', 'NJ', ['Medford'], 55, 88),
    ('voorhees', 'Voorhees', 'NJ', ['Voorhees'], 48, 98),
    ('haddonfield', 'Haddonfield', 'NJ', ['Haddonfield'], 41, 94),
    ('hopewell', 'Hopewell', 'NJ', ['Hopewell'], 83, 71),
    ('pennington', 'Pennington', 'NJ', ['Pennington'], 75, 76),
    ('west_windsor', 'West Windsor', 'NJ', ['Princeton Junction', 'West Windsor'], 81, 65),
]

SOURCES = ["NJ State Police UCR via mytownview.com (Mercer County)", "FBI UCR 2025 via spotcrime.io (Moorestown, Hopewell Twp, West Windsor)",
           "NeighborhoodScout (Cherry Hill, 2024)", "Niche school grades (approx.) and town notes from bella-plan/vecindarios"]

KIND = {"single family": "house", "townhouse": "townhome", "condo": "condo", "multi-family": "multi", "apartment": "condo",
        "manufactured": "other", "land": "land"}


def town(slug):
    for t in TOWNS:
        if t[0] == slug:
            return t
    return None


def rush(m):
    return int(round(m * RUSH[0] / 5) * 5), int(round(m * RUSH[1] / 5) * 5)


def norm_addr(a):
    import re
    a = str(a or "").lower().split(",")[0]
    a = re.sub(r"\b(apt|unit|#)\s*\S+", "", a)
    for k, v in ((" road", " rd"), (" street", " st"), (" drive", " dr"), (" court", " ct"), (" avenue", " ave"), (" lane", " ln"), (" place", " pl"), (" boulevard", " blvd")):
        a = a.replace(k, v)
    return " ".join(a.replace(".", "").split())


def rc_row(x):
    """One RentCast sale listing in the app's feed-row shape (no id: there is no realtor.com detail to fetch for it)."""
    pt = str(x.get("propertyType") or "")
    k = KIND.get(pt.lower(), "other")
    fee = (x.get("hoa") or {}).get("fee") if isinstance(x.get("hoa"), dict) else None
    typ = {"house": "single_family", "townhome": "townhomes", "condo": "condos", "multi": "multi_family"}.get(k, pt.lower())
    return {"id": None, "address": x.get("formattedAddress"), "town": x.get("city"), "zip": x.get("zipCode"), "price": x.get("price"),
            "beds": x.get("bedrooms"), "baths": x.get("bathrooms"), "sqft": x.get("squareFootage"), "type": typ, "kind": k,
            "hoa_monthly": fee, "photo": None, "photos": [], "photo_count": 0, "days": x.get("daysOnMarket"),
            "price_cut": None, "new": False, "lat": x.get("latitude"), "lon": x.get("longitude"), "url": None,
            "broker": (x.get("listingOffice") or {}).get("name"), "status": "for_sale", "source": "RentCast",
            "flags": [], "year": x.get("yearBuilt"), "rc_type": pt, "mls": x.get("mlsNumber"), "lot": x.get("lotSize")}


def filter_rows(rows, budget, min_beds=MIN_BEDS):
    out = []
    for r in rows:
        if r.get("kind") in ("land", "other") and str(r.get("rc_type")).lower() in ("land", "manufactured"):
            continue
        if not r.get("price") or r["price"] > budget:
            continue
        if (r.get("beds") or 0) < min_beds:
            continue
        out.append(r)
    return out


def merge_photos(rows, feed_rows):
    """Use the realtor.com row (photos, link, real id) for a RentCast home with the same street address; keep RentCast's fee if realtor.com has none."""
    by = {norm_addr(f.get("address")): f for f in (feed_rows or []) if f.get("address")}
    out = []
    for r in rows:
        f = by.get(norm_addr(r.get("address")))
        if f and f.get("photo"):
            m = dict(f)
            m["price"] = f.get("price") or r.get("price")
            if not m.get("hoa_monthly") and r.get("hoa_monthly"):
                m["hoa_monthly"] = r["hoa_monthly"]
            for k_ in ("beds", "baths", "sqft", "year", "rc_type", "mls", "lot"):
                m[k_] = m.get(k_) or r.get(k_)
            if r.get("baths"):
                m["baths"] = r["baths"]          # RentCast counts a half bath as 0.5; realtor.com's list "baths" can count it as 1
            out.append(m)
        else:
            out.append(r)
    return out


def cached_feed(name, state="NJ"):
    """The realtor.com for-sale list for this town if it is already on disk (any age up to 14 days). Never calls the API."""
    try:
        r = listings.read_cache(name, "for_sale", 14 * 24, state=state)
        return (r or {}).get("rows") or []
    except Exception:
        return []
