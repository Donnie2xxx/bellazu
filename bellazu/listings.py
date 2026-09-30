"""Homes-for-sale (and for-rent) photo feed: 'Realty in US' on RapidAPI (realtor.com listing data).
Budget: the free plan is 500 calls a month (RapidAPI's month starts on the subscription day), so
  * one list call per town + status (limit 200, newest first), cached on disk for TTL_H hours; price/beds/type are filtered locally;
  * one detail call per home, only when it is opened (photos + HOA fee), cached on disk for 7 days;
  * a call counter (cache/listings/usage.json) that also stores RapidAPI's own 'requests remaining' and 'requests limit' headers;
    calls stop at cap() = 90% of the plan RapidAPI reports (free 500 -> 450; Pro 10,000 -> 9,000), or LISTINGS_CAP if set.
  * for-rent lists are kept RENT_TTL_H (72 h) and also feed the rent estimates (sources/realtor_rent.py).
Interface used by the app:
    search(town, min_price=None, max_price=None, beds=None, kind="any", status="for_sale") -> list of dicts
        {"id", "address", "town", "zip", "price", "beds", "baths", "sqft", "type", "kind", "hoa_monthly", "photo", "photos",
         "photo_count", "days", "price_cut", "new", "lat", "lon", "url", "broker", "status", "source"}
    fetch_town(town, status) -> {"ok", "rows", "total", "fetched", "error"}   detail(id) -> {"ok", "photos", "hoa_monthly", ...}
The key is set by the app (set_key) or RAPIDAPI_KEY in the environment; it is never logged."""
import datetime as dt, json, os, pathlib, re, threading, time
import requests
from .http import CACHE, record
from . import hoa as _hoa

HOST = "realty-in-us.p.rapidapi.com"
BASE = f"https://{HOST}"
TTL_H = float(os.environ.get("LISTINGS_TTL_H", 18))
RENT_TTL_H = float(os.environ.get("LISTINGS_RENT_TTL_H", 72))   # for-rent lists change slowly; they also feed the rent estimates
FREE_PLAN = 500               # Basic (free) plan: 500 calls a month
PRO_MIN = 5000                # a monthly limit this big in RapidAPI's own header = a paid plan (Pro = 10,000)
PLAN = FREE_PLAN              # kept for old imports; the live value is plan()
CAP = int(os.environ.get("LISTINGS_CAP", 0) or 0) or None     # env override; otherwise cap() = 90% of the plan RapidAPI reports
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


def _read():
    try:
        d = json.loads(_upath().read_text())
    except Exception:
        d = {}
    if d.get("reset_at") and time.time() > d["reset_at"]:
        d = {"limit": d["limit"]} if d.get("limit") else {}     # new month: the count starts over, the plan stays
    return d


def plan():
    """Monthly calls in the plan, as RapidAPI itself reports it (x-ratelimit-requests-limit on every answer).
    500 until a response has shown a bigger limit: caps are only raised after RapidAPI confirms the upgrade."""
    try:
        return max(int(_read().get("limit") or FREE_PLAN), 1)
    except Exception:
        return FREE_PLAN


def pro():
    return plan() >= PRO_MIN


def cap():
    """App cap: LISTINGS_CAP if set, else 90% of the plan (free 500 -> 450, Pro 10,000 -> 9,000)."""
    return CAP or int(plan() * 0.9)


def usage():
    d = _read()
    pl, cp = plan(), cap()
    used = max(int(d.get("count", 0)), pl - int(d["remaining"]) if d.get("remaining") is not None else 0)
    return {"used": used, "cap": cp, "plan": pl, "pro": pl >= PRO_MIN, "left": max(cp - used, 0), "api_remaining": d.get("remaining"),
            "resets": dt.datetime.fromtimestamp(d["reset_at"]).strftime("%b %d") if d.get("reset_at") else None}


def _count(resp):
    with _LOCK:
        try:
            d = json.loads(_upath().read_text())
        except Exception:
            d = {}
        if d.get("reset_at") and time.time() > d["reset_at"]:
            d = {"limit": d["limit"]} if d.get("limit") else {}
        d["count"] = int(d.get("count", 0)) + 1
        h = {k.lower(): v for k, v in (resp.headers if resp is not None else {}).items()}
        new_plan = False
        if "x-ratelimit-requests-limit" in h:
            try:
                lim = int(h["x-ratelimit-requests-limit"])
                new_plan = bool(d.get("limit")) and lim != int(d["limit"])
                if lim != int(d.get("limit") or 0):
                    d["limit_seen"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
                d["limit"] = lim
            except ValueError:
                pass
        if "x-ratelimit-requests-remaining" in h:
            d["remaining"] = int(h["x-ratelimit-requests-remaining"])
            pl = int(d.get("limit") or FREE_PLAN)
            # plan changed (e.g. free -> Pro): RapidAPI's own count for the new plan replaces ours
            d["count"] = pl - d["remaining"] if new_plan else max(d["count"], pl - d["remaining"])
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
    price, beds, pfrom = x.get("list_price"), de.get("beds"), False
    if status == "for_rent" and not price and x.get("list_price_min") and de.get("beds_min") is not None and de.get("beds_min") == de.get("beds_max"):
        price, beds, pfrom = x.get("list_price_min"), de.get("beds_min"), True     # one-size building: its lowest asking rent
    return {"id": str(x.get("property_id") or ""), "address": f"{loc.get('line') or ''}, {loc.get('city') or ''}, NJ {loc.get('postal_code') or ''}".strip(" ,"),
            "town": loc.get("city"), "zip": loc.get("postal_code"), "price": price, "beds": beds, "baths": baths, "price_from": pfrom,
            "sqft": de.get("sqft"), "type": t, "kind": KIND.get(t, "other"), "hoa_monthly": (x.get("hoa") or {}).get("fee") if isinstance(x.get("hoa"), dict) else None,
            "photo": photo_url(ph, "card"), "photos": [photo_url(ph, "big")] if ph else [], "photo_count": x.get("photo_count") or 0,
            "days": _days(x.get("list_date")), "price_cut": x.get("price_reduced_amount") if fl.get("is_price_reduced") or x.get("price_reduced_amount") else None,
            "new": bool(fl.get("is_new_listing")), "lat": co.get("lat"), "lon": co.get("lon"), "url": x.get("href"),
            "broker": ((x.get("branding") or [{}])[0] or {}).get("name"), "status": status, "source": SOURCE,
            "flags": [k for k, v in fl.items() if v]}


def _cpath(name):
    _DIR.mkdir(parents=True, exist_ok=True)
    return _DIR / (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + ".json")


def ttl_h(status):
    return RENT_TTL_H if status == "for_rent" else TTL_H


def age_h(town, status="for_sale", page=0):
    """Hours since this town's list was fetched (None if never)."""
    p = _cpath(f"{town}_{status}_{page}_v2")
    return (time.time() - p.stat().st_mtime) / 3600 if p.exists() else None


def read_cache(town, status="for_sale", max_age_h=None, page=0):
    """The on-disk list even if past its TTL (up to max_age_h), or None. Never calls the API."""
    p = _cpath(f"{town}_{status}_{page}_v2")
    if p.exists() and (max_age_h is None or time.time() - p.stat().st_mtime < max_age_h * 3600):
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def fetch_town(town, status="for_sale", page=0, zip_code=None, force=False):
    """One list call per town + status (+ page of 200), cached on disk for TTL_H hours (for-rent: RENT_TTL_H). Never raises.
    If the city name finds fewer than 25 homes and the town's main ZIP is known, one more call by ZIP is merged in
    (realtor.com's city names don't always match the township name, e.g. Union)."""
    p = _cpath(f"{town}_{status}_{page}_v2")
    if not force and p.exists() and time.time() - p.stat().st_mtime < ttl_h(status) * 3600:
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
    res = list(hs.get("results") or [])
    if len(res) < 25 and zip_code and page == 0:
        b2 = {k: v for k, v in body.items() if k not in ("city",)}
        b2["postal_code"] = str(zip_code)
        d2, err2 = _call("POST", "/properties/v3/list", json=b2)
        if not err2:
            ids = {x.get("property_id") for x in res}
            res += [x for x in (((d2 or {}).get("data") or {}).get("home_search") or {}).get("results") or [] if x.get("property_id") not in ids]
    rows = [_norm(x, status) for x in res]
    rows = [r for r in rows if r["type"] != "land"]
    rows = [r for r in rows if r["price"]]
    out = {"ok": True, "rows": rows, "total": hs.get("total"), "fetched": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "town": town, "status": status}
    p.write_text(json.dumps(out))
    return out


SOLD_TTL_H = 30 * 24          # recent sales change slowly: one list call per town, kept 30 days
SOLD_MIN_LEFT = 60            # never start a sold-list call when fewer than this many calls are left in the month


def _norm_sold(x):
    r = _norm(x, "sold")
    r["list_price"] = r.get("price")
    r["price"] = x.get("last_sold_price")
    r["sold_date"] = str(x.get("last_sold_date") or "")[:10] or None
    return r


def sold_cached(town):
    """The saved sold list for a town (any age up to the TTL), or None. Never calls the API."""
    return read_cache(town, "sold", SOLD_TTL_H)


def fetch_sold(town, allow_call=True):
    """Recent SALES in a town (Realty in US sold list, 200 newest by sale date, all home types), cached 30 days. One API call when not cached,
    and only when plenty of calls are left. Returns {"ok", "rows", "fetched", "town"} or {"ok": False, "error"}."""
    p = _cpath(f"{town}_sold_0_v2")
    got = sold_cached(town)
    if got:
        return got
    if not allow_call:
        return {"ok": False, "error": "not loaded", "rows": []}
    if usage()["left"] < SOLD_MIN_LEFT:
        return {"ok": False, "error": "cap", "rows": []}
    body = {"limit": 200, "offset": 0, "city": town, "state_code": "NJ", "status": ["sold"], "sort": {"direction": "desc", "field": "sold_date"}}
    d, err = _call("POST", "/properties/v3/list", json=body)
    if err:
        return {"ok": False, "error": err, "rows": []}
    res = (((d or {}).get("data") or {}).get("home_search") or {}).get("results") or []
    rows = [_norm_sold(x) for x in res]
    rows = [r for r in rows if r["type"] != "land" and r.get("price") and r.get("sold_date")]
    out = {"ok": True, "rows": rows, "total": len(rows), "fetched": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "town": town, "status": "sold"}
    p.write_text(json.dumps(out))
    return out


def all_cached_rows(status="for_sale"):
    """Every saved list of one status across towns (no API calls), de-duplicated by property id."""
    out, seen = [], set()
    for f in sorted(_DIR.glob(f"*_{status}_0_v2.json")) if _DIR.exists() else []:
        try:
            for r in json.loads(f.read_text()).get("rows") or []:
                k = r.get("id") or r.get("address")
                if k in seen:
                    continue
                seen.add(k)
                out.append(r)
        except Exception:
            continue
    return out


def find_row(pid):
    """One saved for-sale row by property id (no API call), or None."""
    if not pid:
        return None
    for r in all_cached_rows("for_sale"):
        if str(r.get("id")) == str(pid):
            return r
    return None


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


def search(town, min_price=None, max_price=None, beds=None, kind="any", status="for_sale", zip_code=None):
    res = fetch_town(town, status, zip_code=zip_code)
    return filter_rows(res.get("rows") or [], min_price, max_price, beds, kind)


def cached(town, status="for_sale", page=0):
    """True if this town's list is on disk and fresh (opening it costs no call)."""
    p = _cpath(f"{town}_{status}_{page}_v2")
    return p.exists() and time.time() - p.stat().st_mtime < ttl_h(status) * 3600


def detail_cached(pid):
    """The 7-day detail cache for one home, or None. Never calls the API."""
    p = _cpath(f"detail_{pid}")
    if pid and p.exists() and time.time() - p.stat().st_mtime < 7 * 86400:
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


_INFLIGHT = {}                 # pid -> Event while a detail call for it runs (a swipe and a prefetch never pay twice)
_POOL = None


def prefetch_details(pids, limit=8):
    """Pro plan only: load the photo galleries (detail calls, 7-day cache) for these homes on a side thread, so their cards
    already carry every photo and swiping is instant. Skips cached/in-flight homes; keeps the month's 300-call reserve.
    Returns how many were queued. Does nothing on the free plan (caps are only raised after RapidAPI confirms Pro)."""
    global _POOL
    if not (available() and pro()):
        return 0
    todo = []
    for pid in pids:
        pid = str(pid or "")
        if pid and pid not in todo and pid not in _INFLIGHT and detail_cached(pid) is None:
            todo.append(pid)
    todo = todo[:max(0, min(limit, usage()["left"] - 300))]
    if not todo:
        return 0
    if _POOL is None:
        import concurrent.futures as cf
        _POOL = cf.ThreadPoolExecutor(max_workers=3, thread_name_prefix="bz-photos")
    for pid in todo:
        _POOL.submit(detail, pid)
    return len(todo)


def detail(pid):
    """Photos (all sizes -> big) + HOA fee etc. for one home; one call, cached 7 days. Never raises."""
    pid = str(pid)
    with _LOCK:
        ev = _INFLIGHT.get(pid)
        mine = ev is None
        if mine:
            ev = _INFLIGHT[pid] = threading.Event()
    if not mine:                          # the same home is loading on another thread: wait for it instead of a 2nd call
        ev.wait(30)
        d = detail_cached(pid)
        if d:
            return d
    try:
        return _detail(pid)
    finally:
        if mine:
            with _LOCK:
                _INFLIGHT.pop(pid, None)
            ev.set()


def _detail(pid):
    p = _cpath(f"detail_{pid}")
    if p.exists() and time.time() - p.stat().st_mtime < 7 * 86400:
        try:
            old = json.loads(p.read_text())
            # detail files from before the HOA fix (hoa_v < 2) kept only hoa.fee: condos/co-ops/townhomes without it are asked
            # again once (the fee is often in the HOA section or the text); everything else is upgraded in place, no call
            if old.get("hoa_v", 0) >= 2 or old.get("hoa_monthly") or _hoa.kind_of(old.get("type")) not in _hoa.HOA_KINDS:
                if old.get("hoa_v", 0) < 2:
                    old.update(hoa_v=2, hoa_src="listing: HOA fee field" if old.get("hoa_monthly") else None,
                               hoa_kind=_hoa.kind_of(old.get("type")), hoa_label="maintenance" if _hoa.kind_of(old.get("type")) == "coop" else "hoa")
                return old
        except Exception:
            pass
    d, err = _call("GET", "/properties/v3/detail", params={"property_id": pid})
    if err:
        return {"ok": False, "error": err}
    h = ((d or {}).get("data") or {}).get("home") or {}
    out = detail_from_home(h)
    p.write_text(json.dumps(out))
    if out["hoa_monthly"]:
        _hoa.add_obs(_DIR, pid, out.get("town"), out.get("zip"), out["hoa_kind"], out["hoa_monthly"], out.get("sqft"), out.get("beds"))
    return out


def detail_from_home(h):
    """The cached detail record from one /properties/v3/detail 'home' object (photos, fee, taxes, facts, text)."""
    de = h.get("description") or {}
    ad = ((h.get("location") or {}).get("address") or {})
    photos = [photo_url(x.get("href"), "big") for x in h.get("photos") or [] if x.get("href")]
    tax = None
    for t in h.get("tax_history") or []:
        if t.get("tax"):
            tax = t["tax"]; break
    if not tax:
        for dd in h.get("details") or []:
            for line in dd.get("text") or []:
                if str(line).lower().startswith("annual tax amount:"):
                    tax = _hoa._num(line.split(":", 1)[1]); break
    hz = _hoa.parse_detail(h)
    out = {"ok": True, "photos": photos, "hoa_monthly": hz["fee"], "hoa_src": hz["src"], "hoa_label": hz["label"], "hoa_inc": hz["inc"],
           "hoa_none": hz["none"], "hoa_kind": hz["kind"], "hoa_v": 2, "taxes_annual": tax,
           "year_built": de.get("year_built"), "sqft": de.get("sqft"), "beds": de.get("beds"), "baths": de.get("baths"), "type": de.get("type"),
           "town": ad.get("city"), "zip": ad.get("postal_code"), "text": (de.get("text") or "")[:3000], "price": h.get("list_price")}
    return out


# ------------------------------------------------------------------ HOA for a card / home (no API call)
_OBS = {"t": 0, "obs": {}}
SEED = pathlib.Path(__file__).resolve().parent.parent / "data" / "hoa_seed.json"


def hoa_obs():
    """Real fees seen so far (bundled seed + every detail call since), re-read at most once a minute."""
    if time.time() - _OBS["t"] > 60:
        _OBS.update(t=time.time(), obs=_hoa.load_obs(_DIR, SEED))
    return _OBS["obs"]


def set_detail_hoa(pid, fee, src):
    """A fee found elsewhere (e.g. RentCast's copy of the listing): keep it with the home's detail file so its card shows it too."""
    p = _cpath(f"detail_{pid}")
    try:
        d = json.loads(p.read_text())
        if not d.get("hoa_monthly"):
            d.update(hoa_monthly=int(fee), hoa_src=src)
            p.write_text(json.dumps(d))
    except Exception:
        pass


def add_hoa_obs(pid, town, zip_, kind, fee, sqft=None, beds=None):
    _hoa.add_obs(_DIR, pid, town, zip_, kind, fee, sqft, beds)
    _OBS["t"] = 0


OVR = pathlib.Path(__file__).resolve().parent.parent / "data" / "listing_overrides.json"
_OVR = {"t": 0, "d": {}}


def overrides():
    """Facts confirmed by a listing agent (data/listing_overrides.json, by listing id); re-read at most once a minute."""
    if time.time() - _OVR["t"] > 60:
        try:
            d = json.loads(OVR.read_text())
        except Exception:
            d = {}
        _OVR.update(t=time.time(), d={str(k): v for k, v in d.items() if isinstance(v, dict) and not str(k).startswith("_")})
    return _OVR["d"]


def hoa_info(row, d=None):
    """What to show for the monthly fee of one listing, from what is already on disk (never calls the API):
    {"state": "real"|"none"|"est"|"unknown", "fee", "label": "hoa"|"maintenance", "src", "inc", "n", "where", "kind"}."""
    row = row or {}
    ov = overrides().get(str(row.get("id"))) if row.get("id") else None
    if ov and ov.get("fee"):                       # confirmed by the listing agent: exact, beats any listing field or estimate
        k_ = ov.get("kind") or "other"
        return {"state": "real", "fee": int(ov["fee"]), "label": "maintenance" if k_ == "coop" else "hoa", "src": ov.get("src") or "confirmed by the listing agent (exact)",
                "inc": list(ov.get("inc") or []), "kind": k_, "exact": bool(ov.get("exact")), "capital_assessment": ov.get("capital_assessment"),
                "move_in_fee": ov.get("move_in_fee"), "move_in_plus": bool(ov.get("move_in_plus"))}
    if d is None and row.get("id"):
        d = detail_cached(str(row["id"]))
    d = d if (d and d.get("ok")) else {}
    kind = _hoa.kind_of(row.get("type"))
    if kind in ("other",) and d.get("type"):
        kind = _hoa.kind_of(d.get("type"))
    if d.get("hoa_kind") == "coop":
        kind = "coop"
    label = "maintenance" if kind == "coop" or d.get("hoa_label") == "maintenance" else "hoa"
    if d.get("hoa_monthly"):
        return {"state": "real", "fee": int(d["hoa_monthly"]), "label": label, "src": d.get("hoa_src") or "listing", "inc": d.get("hoa_inc") or [], "kind": kind}
    if row.get("hoa_monthly"):
        return {"state": "real", "fee": int(row["hoa_monthly"]), "label": label, "src": "listing", "inc": [], "kind": kind}
    if kind in ("house", "multi") or d.get("hoa_none"):
        return {"state": "none", "fee": 0, "label": "hoa", "src": "listing says no association" if d.get("hoa_none") else "typical for houses",
                "inc": [], "kind": kind}
    if kind in _hoa.HOA_KINDS:
        e = _hoa.estimate(hoa_obs(), row.get("town") or d.get("town"), row.get("zip") or d.get("zip"), kind, row.get("sqft") or d.get("sqft"))
        if e:
            return {"state": "est", "fee": e["fee"], "label": label, "src": f"median of {e['n']} similar homes", "n": e["n"], "where": e["where"],
                    "inc": d.get("hoa_inc") or [], "kind": kind}
    return {"state": "unknown", "fee": None, "label": label, "src": None, "inc": d.get("hoa_inc") or [], "kind": kind}
