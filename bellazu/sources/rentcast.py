"""RentCast API (optional; free Developer plan = 50 requests/month). Reads RENTCAST_API_KEY from the environment.
Signup: https://app.rentcast.io/app/api   Docs: https://developers.rentcast.io/reference/introduction

Quota protection (every real request costs 1 of the 50 monthly lookups):
  * every response (including empty lists / 404 "not found") is cached on disk + in memory, keyed by
    endpoint + normalized params (never the key), so repeating an address does not spend quota;
  * a local monthly counter (cache/rentcast/usage.json) counts every real request this app makes;
  * RENTCAST_MONTHLY_CAP (default 45) stops calling before the free 50 are gone -> free-source fallback;
  * RENTCAST_USED_OFFSET="YYYY-MM:N" adds N lookups spent elsewhere in that month (e.g. testing); the larger of it
    and DEFAULT_OFFSET (below) is used;
  * the last lookup left (monthly cap or a per-run budget) is kept for the rent estimate (property record skipped).
Keys: the app may pass candidate keys with set_keys() (e.g. the passcode-locked key in data/rc.lock); RENTCAST_API_KEY
from the environment is the last fallback. A key RentCast refuses (HTTP 401) is dropped for this process and the next
one is tried; 401s are not counted as lookups.
The counter is this app's own count, not RentCast's billing meter (RentCast's month may follow the
signup date, and a restarted container without persistent disk starts from the offset again)."""
import contextlib, contextvars, datetime as dt, hashlib, json, os, threading, time
import requests
from ..http import CACHE, record

BASE = "https://api.rentcast.io/v1/"
_DIR = CACHE / "rentcast"
_MEM = {}
_LOCK = threading.Lock()
TTL_H = {"listings/sale": 72, "properties": 24 * 30, "avm/rent/long-term": 24 * 14, "listings/rental/long-term": 72}
FREE_PLAN = 50
DEFAULT_OFFSET = "2026-09:9"   # lookups already used this month (app count + tests), as of 2026-09-26
_KEYS = []                     # candidate keys in priority order (set by the app)
_BAD = set()                   # fingerprints of keys RentCast refused (401) in this process
_BUDGET = contextvars.ContextVar("rentcast_budget", default=None)   # optional per-run limit: [remaining]


def _fp(k):
    return hashlib.sha256(k.encode()).hexdigest()[:16]


def set_keys(*keys):
    _KEYS[:] = [k.strip() for k in keys if isinstance(k, str) and k.strip()]


def _candidates():
    out = []
    for k in list(_KEYS) + [(os.environ.get("RENTCAST_API_KEY") or "").strip()]:
        if k and k not in out and _fp(k) not in _BAD:
            out.append(k)
    return out


def _key():
    c = _candidates()
    return c[0] if c else ""


def available():
    return bool(_key())


def key_state():
    """'ok' (a usable key), 'refused' (every key got HTTP 401) or 'none' (no key set up)."""
    return "ok" if available() else ("refused" if _BAD else "none")


@contextlib.contextmanager
def budget(n):
    """Limit live lookups inside this block to n (None = no extra limit). Yields [remaining]."""
    if n is None:
        yield None
        return
    b = [max(int(n), 0)]
    tok = _BUDGET.set(b)
    try:
        yield b
    finally:
        _BUDGET.reset(tok)


def remaining():
    """Live lookups still allowed right now (monthly cap and any per-run budget)."""
    m = usage()["remaining_before_cap"]
    b = _BUDGET.get()
    return min(m, b[0]) if b is not None else m


def _month():
    return dt.date.today().strftime("%Y-%m")


def _usage_path():
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / "usage.json"


def _parse_offset(v):
    try:
        m, n = (v or "").split(":")
        return int(n) if m.strip() == _month() else 0
    except Exception:
        return 0


def _offset():
    return max(_parse_offset(os.environ.get("RENTCAST_USED_OFFSET", "")), _parse_offset(DEFAULT_OFFSET))


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
            "free_plan": FREE_PLAN, "remaining_before_cap": max(cap() - used, 0), "enabled": available(),
            "key_state": key_state()}


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


def _cache_key(path, params):
    return hashlib.sha1((path + json.dumps(_norm(params), sort_keys=True)).encode()).hexdigest()


def _cached(path, params):
    ck = _cache_key(path, params)
    ttl = TTL_H.get(path, 72) * 3600
    hit = _MEM.get(ck)
    f = _DIR / f"{ck}.json"
    return bool((hit and time.time() - hit["t"] < ttl) or (f.exists() and time.time() - f.stat().st_mtime < ttl))


def _get(path, params):
    """Returns (data, status) where status in ok|cache|no_key|quota|not_found|error:<detail>."""
    if not available():
        return None, "no_key"
    ck = _cache_key(path, params)
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
        b = _BUDGET.get()
        if b is not None and b[0] <= 0:
            record("RentCast " + path, BASE + path, False, None, "lookup budget for this run used up; using free sources")
            return None, "budget"
        while True:
            key = _key()
            if not key:
                return None, "error:401"
            try:
                r = requests.get(BASE + path, params=params, headers={"X-Api-Key": key, "Accept": "application/json"}, timeout=30)
            except Exception as e:
                record("RentCast " + path, BASE + path, False, None, f"network error: {e.__class__.__name__}")
                return None, "error:network"
            if r.status_code != 401:
                break
            _BAD.add(_fp(key))            # refused key: not a billed lookup; drop it and try the next one
            record("RentCast " + path, BASE + path, False, 401, "invalid/missing API key" + ("; trying the other key" if available() else ""))
        _bump(path, r.status_code)
        if b is not None:
            b[0] -= 1
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
            note = {429: "rate limited / quota exhausted", 402: "billing / quota"}.get(r.status_code, "error")
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


def property_record(address, reserve=0):
    """Public-record facts (taxes, HOA, beds, sqft). 1 lookup (cached 30 days). Skipped (status 'skipped') when it is not
    cached and no more than `reserve` lookups are left, so the last one goes to the rent estimate."""
    p = {"address": address, "limit": 1}
    if reserve and available() and not _cached("properties", p) and remaining() <= reserve:
        record("RentCast properties", BASE + "properties", False, None, "skipped to keep the last lookup for the rent estimate")
        return None, "skipped"
    d, s = _get("properties", p)
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
