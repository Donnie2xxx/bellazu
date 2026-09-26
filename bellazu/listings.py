"""Homes-for-sale (and for-rent) photo feed: 'Realty in US' on RapidAPI (realtor.com listing data).
Budget: the free plan is 500 calls a month (RapidAPI's month starts on the subscription day), so
  * one list call per town + status (limit 200, newest first), cached on disk for TTL_H hours; price/beds/type are filtered locally;
  * one detail call per home, only when it is opened (photos + HOA fee), cached on disk for 7 days;
  * a call counter (cache/listings/usage.json) that also stores RapidAPI's own 'requests remaining' header; calls stop at CAP.
Interface used by the app:
    search(town, min_price=None, max_price=None, beds=None, kind="any", status="for_sale") -> list of dicts
        {"id", "address", "town", "zip", "price", "beds", "baths", "sqft", "type", "kind", "hoa_monthly", "photo", "photos",
         "photo_count", "days", "price_cut", "new", "lat", "lon", "url", "broker", "status", "source"}
    fetch_town(town, status) -> {"ok", "rows", "total", "fetched", "error"}   detail(id) -> {"ok", "photos", "hoa_monthly", ...}
The key is set by the app (set_key) or RAPIDAPI_KEY in the environment; it is never logged."""
import datetime as dt, json, os, re, threading, time
import requests
from .http import CACHE, record

HOST = "realty-in-us.p.rapidapi.com"
BASE = f"https://{HOST}"
TTL_H = float(os.environ.get("LISTINGS_TTL_H", 18))
CAP = int(os.environ.get("LISTINGS_CAP", 450))
PLAN = 500
SALE_MAX = 900_000            # the list call skips luxury homes so the 200 newest are in a first-home range
_DIR = CACHE / "listings"
_KEY = None
_LOCK = threading.Lock()
SOURCE = "realtor.com via Realty in US (RapidAPI)"
KIND = {"condos": "condo", "condo_townhome": "condo", "condo_townhome_rowhome_coop": "condo", "coop": "condo", "townhomes": "condo",
        "multi_family": "2fam", "single_family": "house", "apartment": "condo", "duplex_triplex": "2fam"}


def set_key(k):
    global _KEY
    _KEY = (k or "").strip() or None


def _key():
    return _KEY or (os.environ.get("RAPIDAPI_KEY") or "").strip() or None


def available():
    return bool(_key())


# ------------------------------------------------------------------ call counter
def _upath():
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / "usage.json"


def usage():
    try:
        d = json.loads(_upath().read_text())
    except Exception:
        d = {}
    now = time.time()
    if d.get("reset_at") and now > d["reset_at"]:
        d = {}
    used = max(int(d.get("count", 0)), PLAN - int(d["remaining"]) if d.get("remaining") is not None else 0)
    return {"used": used, "cap": CAP, "plan": PLAN, "left": max(CAP - used, 0), "api_remaining": d.get("remaining"),
            "resets": dt.datetime.fromtimestamp(d["reset_at"]).strftime("%b %d") if d.get("reset_at") else None}


def _count(resp):
    with _LOCK:
        try:
            d = json.loads(_upath().read_text())
        except Exception:
            d = {}
        if d.get("reset_at") and time.time() > d["reset_at"]:
            d = {}
        d["count"] = int(d.get("count", 0)) + 1
        h = {k.lower(): v for k, v in (resp.headers if resp is not None else {}).items()}
        if "x-ratelimit-requests-remaining" in h:
            d["remaining"] = int(h["x-ratelimit-requests-remaining"])
            d["count"] = max(d["count"], PLAN - d["remaining"])
        if "x-ratelimit-requests-reset" in h:
            d["reset_at"] = time.time() + int(h["x-ratelimit-requests-reset"])
        _upath().write_text(json.dumps(d))


def _call(method, path, **kw):
    k = _key()
    if not k:
        return None, "no key"
    if usage()["left"] <= 0:
        record("Listings " + path, BASE + path, False, None, "monthly listings cap reached")
        return None, "cap"
    hdr = {"x-rapidapi-key": k, "x-rapidapi-host": HOST}
    try:
        r = requests.request(method, BASE + path, headers=hdr, timeout=25, **kw)
    except Exception as e:
        record("Listings " + path, BASE + path, False, None, e.__class__.__name__)
        return None, e.__class__.__name__
    _count(r)
    record("Listings " + path, BASE + path, r.status_code == 200, r.status_code, None if r.status_code == 200 else f"HTTP {r.status_code}")
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), None
    except Exception:
        return None, "bad json"


# ------------------------------------------------------------------ normalizing
def photo_url(href, size="card"):
    """rdcpix thumbnails end in 's.jpg'; the same photo comes bigger with another suffix (checked on the CDN: rd-w480_h360 = 480 px, od = 1024 px)."""
    if not href:
        return None
    href = href.replace("http://", "https://")
    suf = {"card": "rd-w480_h360.jpg", "big": "od-w1024_h768.jpg"}[size]
    return re.sub(r"(-m\d+)[a-z]?\.jpg$", r"\1" + suf, href) if re.search(r"-m\d+[a-z]?\.jpg$", href) else href


def _days(iso):
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")[:26].rstrip("Z"))
        return max((dt.datetime.now(d.tzinfo) - d).days, 0)
    except Exception:
        return None


def _norm(x, status):
    loc = ((x.get("location") or {}).get("address") or {})
    de = x.get("description") or {}
    co = loc.get("coordinate") or {}
    fl = x.get("flags") or {}
    t = de.get("type") or ""
    ph = (x.get("primary_photo") or {}).get("href")
    baths = de.get("baths") or ((de.get("baths_full_calc") or 0) + 0.5 * (de.get("baths_partial_calc") or 0)) or None
    return {"id": str(x.get("property_id") or ""), "address": f"{loc.get('line') or ''}, {loc.get('city') or ''}, NJ {loc.get('postal_code') or ''}".strip(" ,"),
            "town": loc.get("city"), "zip": loc.get("postal_code"), "price": x.get("list_price"), "beds": de.get("beds"), "baths": baths,
            "sqft": de.get("sqft"), "type": t, "kind": KIND.get(t, "other"), "hoa_monthly": (x.get("hoa") or {}).get("fee") if isinstance(x.get("hoa"), dict) else None,
            "photo": photo_url(ph, "card"), "photos": [photo_url(ph, "big")] if ph else [], "photo_count": x.get("photo_count") or 0,
            "days": _days(x.get("list_date")), "price_cut": x.get("price_reduced_amount") if fl.get("is_price_reduced") or x.get("price_reduced_amount") else None,
            "new": bool(fl.get("is_new_listing")), "lat": co.get("lat"), "lon": co.get("lon"), "url": x.get("href"),
            "broker": ((x.get("branding") or [{}])[0] or {}).get("name"), "status": status, "source": SOURCE}


def _cpath(name):
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + ".json")


def fetch_town(town, status="for_sale", page=0):
    """One list call per town + status (+ page of 200), cached on disk for TTL_H hours. Never raises."""
    p = _cpath(f"{town}_{status}_{page}")
    if p.exists() and time.time() - p.stat().st_mtime < TTL_H * 3600:
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    body = {"limit": 200, "offset": 200 * page, "city": town, "state_code": "NJ", "status": [status], "sort": {"direction": "desc", "field": "list_date"}}
    if status == "for_sale":
        body["list_price"] = {"max": SALE_MAX}
    d, err = _call("POST", "/properties/v3/list", json=body)
    if err:
        return {"ok": False, "error": err, "rows": []}
    hs = ((d or {}).get("data") or {}).get("home_search") or {}
    rows = [_norm(x, status) for x in hs.get("results") or []]
    rows = [r for r in rows if r["type"] != "land"]
    rows = [r for r in rows if r["price"] and (r["town"] or "").lower() == town.lower()] or rows
    out = {"ok": True, "rows": rows, "total": hs.get("total"), "fetched": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "town": town, "status": status}
    p.write_text(json.dumps(out))
    return out


def filter_rows(rows, min_price=None, max_price=None, beds=None, kind="any"):
    out, seen = [], set()
    for r in rows:
        if r.get("id") and r["id"] in seen:
            continue
        seen.add(r.get("id"))
        if min_price and (r["price"] or 0) < min_price:
            continue
        if max_price and (r["price"] or 0) > max_price:
            continue
        if beds and (r["beds"] or 0) < beds:
            continue
        if kind not in (None, "any") and r["kind"] != kind:
            continue
        out.append(r)
    return out


def search(town, min_price=None, max_price=None, beds=None, kind="any", status="for_sale"):
    res = fetch_town(town, status)
    return filter_rows(res.get("rows") or [], min_price, max_price, beds, kind)


def detail(pid):
    """Photos (all sizes -> big) + HOA fee etc. for one home; one call, cached 7 days. Never raises."""
    p = _cpath(f"detail_{pid}")
    if p.exists() and time.time() - p.stat().st_mtime < 7 * 86400:
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    d, err = _call("GET", "/properties/v3/detail", params={"property_id": pid})
    if err:
        return {"ok": False, "error": err}
    h = ((d or {}).get("data") or {}).get("home") or {}
    de = h.get("description") or {}
    hoa = h.get("hoa") or {}
    photos = [photo_url(x.get("href"), "big") for x in h.get("photos") or [] if x.get("href")]
    tax = None
    for t in h.get("tax_history") or []:
        if t.get("tax"):
            tax = t["tax"]; break
    out = {"ok": True, "photos": photos, "hoa_monthly": hoa.get("fee") if isinstance(hoa, dict) else None, "taxes_annual": tax,
           "year_built": de.get("year_built"), "sqft": de.get("sqft"), "beds": de.get("beds"), "baths": de.get("baths"), "type": de.get("type"),
           "text": (de.get("text") or "")[:1200], "price": h.get("list_price")}
    p.write_text(json.dumps(out))
    return out
