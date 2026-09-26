import math, json, re
from .http import fetch, UA_BOT


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _strip_unit(addr):
    # Nominatim does not understand unit numbers
    return re.sub(r"\b(apt|apartment|unit|ste|suite|#)\s*[\w-]+", "", addr, flags=re.I).replace(" ,", ",").strip()


def geocode(address):
    """Free geocoding via OpenStreetMap Nominatim (1 req/s policy, cached 30 days)."""
    from urllib.parse import quote
    q = _strip_unit(address)
    url = f"https://nominatim.openstreetmap.org/search?q={quote(q)}&format=json&addressdetails=1&limit=1&countrycodes=us"
    txt = fetch(url, "geocode:nominatim", ttl_hours=24 * 30, ua="bot", min_interval=1.1)
    if not txt:
        return None
    try:
        d = json.loads(txt)
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
