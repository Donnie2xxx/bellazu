"""Rent comps from realtor.com for-rent listings (Realty in US on RapidAPI). Took Rent.com's place in the rent pool
(Rent.com answers the DigitalOcean server with a robot check, so the server never asks it).

Costs few calls: it reads the SAME on-disk list the app's 'What similar places rent for' box and the For-rent feed use
(listings.fetch_town(town, "for_rent"), kept RENT_TTL_H = 72 h). A new call is made only when
  * that list is missing or older than 72 h, and
  * the caller allows calls (the nightly free pass does not; the pre-warm RapidAPI pass refreshes lists within its budget), and
  * the month still has more than reserve() calls left (40 on the free plan, 300 on Pro), so browsing never runs dry.
Otherwise an older copy (up to STALE_MAX_H = 14 days) is used, or nothing.

rows_for(town, state, zipcode, allow_call=True) -> {"ok", "rows", "url", "n", "note", "fetched"}
rows use the rent-pool columns: source, title, price, beds, baths, sqft, lat, lon, locality, address, url, kind."""
from .. import listings

SOURCE = "realtor.com"
STALE_MAX_H = 14 * 24


def reserve():
    return 300 if listings.pro() else 40


def _pool_rows(res):
    out = []
    for r in (res or {}).get("rows") or []:
        if not r.get("price") or r.get("beds") is None:
            continue
        addr = r.get("address") or ""
        out.append({"source": SOURCE, "title": addr, "price": float(r["price"]), "beds": int(r["beds"]), "baths": r.get("baths"),
                    "sqft": r.get("sqft"), "lat": r.get("lat"), "lon": r.get("lon"), "locality": r.get("town") or "", "address": addr,
                    "url": r.get("url"), "kind": "unit"})
    return out


def rows_for(town, state="nj", zipcode=None, allow_call=True):
    url = f"https://www.realtor.com/apartments/{town.replace(' ', '-')}_{(state or 'nj').upper()}"
    if not listings.available() and not listings.read_cache(town, "for_rent", STALE_MAX_H):
        return {"ok": False, "rows": [], "url": url, "n": 0, "note": "no RapidAPI key"}
    note = "cached list"
    if listings.cached(town, "for_rent"):
        res = listings.fetch_town(town, "for_rent", zip_code=zipcode)
    elif allow_call and listings.available() and listings.usage()["left"] > reserve():
        res = listings.fetch_town(town, "for_rent", zip_code=zipcode)
        note = "new list"
        if not res.get("ok"):
            old = listings.read_cache(town, "for_rent", STALE_MAX_H)
            res, note = (old, "older cached list (new call failed)") if old else (res, f"call failed: {res.get('error')}")
    else:
        res = listings.read_cache(town, "for_rent", STALE_MAX_H)
        why = "calls not allowed here" if not allow_call else "keeping the month's reserve"
        note = f"older cached list ({why})" if res else f"not loaded ({why})"
    rows = _pool_rows(res) if res and res.get("ok") else []
    return {"ok": bool(res and res.get("ok")), "rows": rows, "url": url, "n": len(rows), "note": note, "fetched": (res or {}).get("fetched")}
