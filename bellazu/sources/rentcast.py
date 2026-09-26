"""RentCast API (optional; free Developer plan = 50 requests/month). Reads RENTCAST_API_KEY from the environment.
Signup: https://app.rentcast.io/app/api   Docs: https://developers.rentcast.io/reference/introduction

Quota protection (every real request costs 1 of the 50 monthly lookups):
  * every response (including empty lists / 404 "not found") is cached on disk + in memory, keyed by
    endpoint + normalized params (never the key), so repeating an address does not spend quota;
  * a local monthly counter (cache/rentcast/usage.json) counts every real request this app makes;
  * RENTCAST_MONTHLY_CAP (default 45) stops calling before the free 50 are gone -> free-source fallback;
  * RENTCAST_USED_OFFSET="YYYY-MM:N" adds N lookups spent elsewhere in that month (e.g. testing).
The counter is this app's own count, not RentCast's billing meter (RentCast's month may follow the
signup date, and a restarted container without persistent disk starts from the offset again)."""
import datetime as dt, hashlib, json, os, threading, time
import requests
from ..http import CACHE, record

BASE = "https://api.rentcast.io/v1/"
_DIR = CACHE / "rentcast"
_MEM = {}
_LOCK = threading.Lock()
TTL_H = {"listings/sale": 72, "properties": 24 * 30, "avm/rent/long-term": 24 * 14, "listings/rental/long-term": 72}
FREE_PLAN = 50


def _key():
    return (os.environ.get("RENTCAST_API_KEY") or "").strip()


def available():
    return bool(_key())


def _month():
    return dt.date.today().strftime("%Y-%m")


def _usage_path():
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / "usage.json"


def _offset():
    v = os.environ.get("RENTCAST_USED_OFFSET", "")
    try:
        m, n = v.split(":")
        return int(n) if m.strip() == _month() else 0
    except Exception:
        return 0


def cap():
    try:
        return int(os.environ.get("RENTCAST_MONTHLY_CAP", "45"))
    except ValueError:
        return 45


def usage():
    """{'month','app_calls','offset','used','cap','free_plan','remaining_before_cap'} (never contains the key)."""
    p = _usage_path()
    d = {}
    if p.exists():
        try:
            d = json.loads(p.read_text())
        except Exception:
            d = {}
    n = int(d.get("count", 0)) if d.get("month") == _month() else 0
    used = n + _offset()
    return {"month": _month(), "app_calls": n, "offset": _offset(), "used": used, "cap": cap(),
            "free_plan": FREE_PLAN, "remaining_before_cap": max(cap() - used, 0), "enabled": available()}


def _bump(endpoint, status):
    p = _usage_path()
    d = {}
    if p.exists():
        try:
            d = json.loads(p.read_text())
        except Exception:
            d = {}
    if d.get("month") != _month():
        d = {"month": _month(), "count": 0, "log": []}
    d["count"] = int(d.get("count", 0)) + 1
    d.setdefault("log", []).append({"ts": dt.datetime.now().isoformat(timespec="seconds"), "endpoint": endpoint, "http": status})
    d["log"] = d["log"][-200:]
    p.write_text(json.dumps(d))


def _norm(params):
    return {k: (" ".join(str(v).lower().replace(",", " , ").split()) if isinstance(v, str) else v) for k, v in sorted(params.items())}


def _get(path, params):
    """Returns (data, status) where status in ok|cache|no_key|quota|not_found|error:<detail>."""
    if not available():
        return None, "no_key"
    ck = hashlib.sha1((path + json.dumps(_norm(params), sort_keys=True)).encode()).hexdigest()
    f = _DIR / f"{ck}.json"
    ttl = TTL_H.get(path, 72) * 3600
    with _LOCK:
        hit = _MEM.get(ck)
        if hit and time.time() - hit["t"] < ttl:
            record("RentCast " + path, BASE + path, hit["status"] == 200, "cache", "served from session cache (no quota used)")
            return (hit["body"] if hit["status"] == 200 else None), ("cache" if hit["status"] == 200 else "not_found")
        if f.exists() and time.time() - f.stat().st_mtime < ttl:
            try:
                hit = json.loads(f.read_text())
                _MEM[ck] = hit
                record("RentCast " + path, BASE + path, hit["status"] == 200, "cache", "served from disk cache (no quota used)")
                return (hit["body"] if hit["status"] == 200 else None), ("cache" if hit["status"] == 200 else "not_found")
            except Exception:
                pass
        u = usage()
        if u["used"] >= u["cap"]:
            record("RentCast " + path, BASE + path, False, None, f"monthly cap reached ({u['used']}/{u['cap']}); using free sources")
            return None, "quota"
        try:
            r = requests.get(BASE + path, params=params, headers={"X-Api-Key": _key(), "Accept": "application/json"}, timeout=30)
        except Exception as e:
            record("RentCast " + path, BASE + path, False, None, f"network error: {e.__class__.__name__}")
            return None, "error:network"
        _bump(path, r.status_code)
        if r.status_code == 200:
            try:
                body = r.json()
            except Exception:
                record("RentCast " + path, BASE + path, False, 200, "bad JSON")
                return None, "error:json"
            hit = {"status": 200, "body": body, "t": time.time()}
        elif r.status_code == 404:
            hit = {"status": 404, "body": None, "t": time.time()}
        else:
            msg = ""
            try:
                msg = (r.json() or {}).get("error", "")
            except Exception:
                pass
            note = {401: "invalid/missing API key", 429: "rate limited / quota exhausted", 402: "billing / quota"}.get(r.status_code, "error")
            record("RentCast " + path, BASE + path, False, r.status_code, f"{note} {msg}".strip())
            return None, ("quota" if r.status_code in (402, 429) else f"error:{r.status_code}")
        _MEM[ck] = hit
        _DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(hit))
        record("RentCast " + path, BASE + path, hit["status"] == 200, r.status_code, "live API call (1 lookup used)" + ("; no record" if hit["status"] == 404 else ""))
        return (hit["body"] if hit["status"] == 200 else None), ("ok" if hit["status"] == 200 else "not_found")


PTYPE = {"condo": "Condo", "co-op": "Condo", "coop": "Condo", "single-family": "Single Family", "multi-family": "Multi-Family",
         "townhouse": "Townhouse", "apartment": "Apartment"}


def rent_estimate(address, beds=None, baths=None, sqft=None, ownership=None, comp_count=20):
    """Long-term rent AVM + comparables. 1 lookup (cached 14 days)."""
    p = {"address": address, "compCount": comp_count}
    pt = PTYPE.get((ownership or "").lower())
    if pt: p["propertyType"] = pt
    if beds is not None: p["bedrooms"] = int(beds)
    if baths: p["bathrooms"] = float(baths)
    if sqft: p["squareFootage"] = float(sqft)
    d, s = _get("avm/rent/long-term", p)
    if not isinstance(d, dict) or not d.get("rent"):
        return {"ok": False, "status": s}
    comps = []
    for c in d.get("comparables") or []:
        comps.append({"source": "RentCast", "title": c.get("formattedAddress"), "address": c.get("formattedAddress"),
                      "price": c.get("price"), "beds": c.get("bedrooms"), "baths": c.get("bathrooms"), "sqft": c.get("squareFootage"),
                      "lat": c.get("latitude"), "lon": c.get("longitude"), "dist_km": round(float(c.get("distance") or 0) * 1.609, 2),
                      "days_old": c.get("daysOld"), "status": c.get("status"), "correlation": c.get("correlation"),
                      "url": map_link(c.get("formattedAddress"))})
    return {"ok": True, "status": s, "rent": d.get("rent"), "low": d.get("rentRangeLow"), "high": d.get("rentRangeHigh"),
            "n": len(comps), "comps": comps, "subject": {k: (d.get("subjectProperty") or {}).get(k) for k in ("propertyType", "bedrooms", "bathrooms", "squareFootage", "yearBuilt")},
            "source": "RentCast long-term rent AVM (api.rentcast.io/v1/avm/rent/long-term)"}


def sale_listing(address):
    """Active sale listing for this exact address. 1 lookup (cached 3 days)."""
    d, s = _get("listings/sale", {"address": address, "limit": 1})
    return (d[0] if isinstance(d, list) and d else None), s


def property_record(address):
    """Public-record facts (taxes, HOA, beds, sqft). 1 lookup (cached 30 days)."""
    d, s = _get("properties", {"address": address, "limit": 1})
    return (d[0] if isinstance(d, list) and d else None), s


def latest_tax(rec):
    t = (rec or {}).get("propertyTaxes") or {}
    ys = sorted(t.keys())
    return (t[ys[-1]].get("total"), ys[-1]) if ys else (None, None)


def rental_listings(city, state, limit=500):
    """Active long-term rental listings in a city (all bedroom counts in ONE lookup, cached 3 days)."""
    d, s = _get("listings/rental/long-term", {"city": city, "state": state.upper(), "status": "Active", "limit": limit})
    rows = []
    for r in (d if isinstance(d, list) else []):
        rows.append({"source": "RentCast", "title": r.get("formattedAddress"), "price": r.get("price"),
                     "beds": r.get("bedrooms"), "baths": r.get("bathrooms"), "sqft": r.get("squareFootage"),
                     "lat": r.get("latitude"), "lon": r.get("longitude"), "locality": r.get("city"),
                     "address": r.get("formattedAddress"), "url": map_link(r.get("formattedAddress")), "kind": "unit",
                     "property_type": r.get("propertyType"), "days_on_market": r.get("daysOnMarket")})
    return rows, s


def map_link(addr):
    from urllib.parse import quote_plus
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(addr or "")
