import math, json, re
from .http import fetch, UA_BOT


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


UNIT_RE = re.compile(r"(?:(?<=\s)|(?<=,)|^)(?:apt|apartment|unit|ste|suite|fl|floor|rm|room|ph|bldg|building|no)\b\.?\s*#?\s*[\w-]+"
                     r"|(?:(?<=\s)|(?<=,)|^)(?:apt|unit|ph)\d[\w-]*\b"
                     r"|(?:(?<=\s)|(?<=,))#\s*[\w-]+", re.I)


def _strip_unit(addr):
    """Nominatim does not understand unit numbers: drop 'Apt 4B', 'apt. 2102', '#12', 'Unit 21-02', 'Fl 3', 'PH2'..."""
    s = UNIT_RE.sub("", addr or "")
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s*,+", ",", s)
    return re.sub(r"\s{2,}", " ", s).strip(" ,")


TOWN_ABBR = [(r"\bft\.?\s+", "Fort "), (r"\bw\.?\s+new york\b", "West New York"), (r"\bwny\b", "West New York"),
             (r"\bn\.?\s+bergen\b", "North Bergen"), (r"\bjc\b", "Jersey City")]


def _variants(address):
    """Queries to try, most exact first (phone-typed: lowercase, no ZIP, no commas, 'Ft Lee', unit numbers)."""
    q = _strip_unit(address)
    out = [q]
    q2 = q
    for a, b in TOWN_ABBR:
        q2 = re.sub(a, b, q2, flags=re.I)
    if q2 != q:
        out.append(q2)
    if not re.search(r"\b(nj|new jersey|ny|new york)\b", q2, re.I):
        out.append(q2 + ", NJ")
    return list(dict.fromkeys(out))


def _nominatim(q):
    from urllib.parse import quote
    url = f"https://nominatim.openstreetmap.org/search?q={quote(q)}&format=json&addressdetails=1&limit=1&countrycodes=us"
    txt = fetch(url, "geocode:nominatim", ttl_hours=24 * 30, ua="bot", min_interval=1.1, timeout=15, retries=0,
                validate=lambda t: t.lstrip().startswith("[{"))
    try:
        d = json.loads(txt) if txt else None
    except Exception:
        return None
    if not d:
        return None
    x = d[0]
    a = x.get("address", {})
    town = a.get("town") or a.get("city") or a.get("village") or a.get("municipality") or a.get("hamlet") or ""
    return {"lat": float(x["lat"]), "lon": float(x["lon"]), "display": x.get("display_name"),
            "town": town, "county": a.get("county", ""), "state": a.get("state", ""),
            "zip": a.get("postcode", ""), "bbox": [float(v) for v in x.get("boundingbox", [])],
            "osm_type": x.get("addresstype"), "source": "OpenStreetMap Nominatim"}


PHOTON = "https://photon.komoot.io/api/"
NJ_BBOX = "-75.6,38.9,-73.3,41.4"   # NJ + NYC (lon/lat)


def _photon_raw(q, limit=5):
    from urllib.parse import quote
    url = f"{PHOTON}?q={quote(q)}&limit={limit}&lang=en&bbox={NJ_BBOX}&lat=40.85&lon=-74.0"
    txt = fetch(url, "geocode:photon", ttl_hours=24 * 30, ua="bot", min_interval=1.1, timeout=15, retries=0,
                validate=lambda t: t.lstrip().startswith("{"))
    try:
        return (json.loads(txt).get("features") or []) if txt else []
    except Exception:
        return []


def _photon_label(p):
    street = " ".join(x for x in [p.get("housenumber"), p.get("street") or (p.get("name") if p.get("type") in ("house", "street") else None)] if x)
    town = p.get("city") or p.get("town") or p.get("village") or p.get("district") or p.get("name") or ""
    st = {"New Jersey": "NJ", "New York": "NY"}.get(p.get("state"), p.get("state") or "")
    tail = " ".join(x for x in [st, p.get("postcode")] if x)
    return ", ".join(x for x in [street, town if town != street else "", tail] if x)


def _photon(q):
    f = _photon_raw(q, 1)
    if not f:
        return None
    p, (lon, lat) = f[0]["properties"], f[0]["geometry"]["coordinates"]
    ext = p.get("extent")   # [minlon, maxlat, maxlon, minlat]
    return {"lat": float(lat), "lon": float(lon), "display": _photon_label(p),
            "town": p.get("city") or p.get("town") or p.get("village") or (p.get("name") if p.get("type") in ("city", "town", "village") else ""),
            "county": p.get("county", ""), "state": p.get("state", ""), "zip": p.get("postcode", ""),
            "bbox": [ext[3], ext[1], ext[0], ext[2]] if ext and len(ext) == 4 else [],
            "osm_type": p.get("type"), "source": "Photon (OpenStreetMap)"}


def suggest(q, limit=5):
    """Address suggestions for phone-typed text (one Photon request per distinct text, cached). Returns labels.
    If OpenStreetMap only knows the street, the typed house number is kept; a typed apartment number is kept too."""
    raw = (q or "").strip()
    base = _strip_unit(raw)
    if len(base) < 5:
        return []
    num = re.match(r"\s*(\d+[A-Za-z]?)\b", base)
    unit = " ".join(m.group(0).strip(" ,") for m in UNIT_RE.finditer(raw))
    out = []
    for f in _photon_raw(base, limit + 2):
        p = dict(f.get("properties") or {})
        if p.get("type") not in ("house", "street", "building") and not p.get("housenumber"):
            continue
        street = (p.get("street") or (p.get("name") if p.get("type") in ("street", "house") else "") or "").lower()
        if num and street:
            if not any(w in base.lower() for w in re.findall(r"[a-z]{3,}", street)[:2]):
                continue             # a different street than the one typed
            if not p.get("housenumber"):
                p["housenumber"] = num.group(1)
        elif num:
            continue
        lab = _photon_label(p)
        if unit and lab:
            parts = lab.split(", ", 1)
            lab = f"{parts[0]} {unit}" + (f", {parts[1]}" if len(parts) > 1 else "")
        if lab and lab not in out:
            out.append(lab)
    return out[:limit]


def _census(q):
    """US Census Bureau geocoder (public, free, good house-number coverage). Needs a town or ZIP in the text."""
    from urllib.parse import quote
    url = ("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=" + quote(q)
           + "&benchmark=Public_AR_Current&format=json")
    txt = fetch(url, "geocode:census", ttl_hours=24 * 30, ua="bot", min_interval=1.0, timeout=20, retries=0,
                validate=lambda t: '"addressMatches"' in t)
    try:
        m = (json.loads(txt)["result"]["addressMatches"] or [None])[0] if txt else None
    except Exception:
        return None
    if not m:
        return None
    c, ac = m.get("coordinates") or {}, m.get("addressComponents") or {}
    town = (ac.get("city") or "").title()
    return {"lat": float(c["y"]), "lon": float(c["x"]), "display": m.get("matchedAddress"), "town": town, "county": "",
            "state": ac.get("state", ""), "zip": ac.get("zip", ""), "bbox": [], "osm_type": "house", "source": "US Census geocoder"}


def geocode(address):
    """Free geocoding, most exact first, trying phone-typed variants of the text:
    OpenStreetMap Nominatim (1 req/s policy, cached 30 days) -> Photon (OpenStreetMap data) -> US Census geocoder.
    Several services because shared cloud hosts get rate-limited or blocked by some of them."""
    vs = _variants(address)
    for fn in (_nominatim, _photon, _census):
        for q in vs:
            try:
                g = fn(q)
            except Exception:
                g = None
            if g and g.get("lat"):
                return g
    return None
