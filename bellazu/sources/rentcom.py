"""Rent.com city pages (e.g. /new-jersey/fort-lee-apartments). Path allowed by robots.txt.
Parses __NEXT_DATA__: per-building floor plans with beds, rent range, sqft, lat/lng.
Mostly professionally managed buildings (skews to newer/luxury stock)."""
import re, json
from ..http import fetch

STATES = {"nj": "new-jersey", "ny": "new-york"}


def search(town, state="nj", pages=2):
    slug = re.sub(r"[^a-z0-9]+", "-", town.lower()).strip("-")
    base = f"https://www.rent.com/{STATES.get(state.lower(), state)}/{slug}-apartments"
    rows, ok_any, total = [], False, None
    for p in range(1, pages + 1):
        url = base if p == 1 else f"{base}?page={p}"
        html = fetch(url, "rent.com", ttl_hours=12, min_interval=3, validate=lambda t: "__NEXT_DATA__" in t)
        if not html:
            break
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        try:
            ls = json.loads(m.group(1))["props"]["pageProps"]["pageData"]["location"]["listingSearch"]
        except Exception:
            break
        ok_any, total = True, ls.get("total")
        for b in ls.get("listings", []):
            loc = b.get("location") or {}
            for fp in b.get("floorPlans") or []:
                pr = (fp.get("priceRange") or {})
                if not pr.get("min"):
                    continue
                sq = fp.get("sqFtRange") or {}
                rows.append({"source": "Rent.com", "title": b.get("name"), "price": int(pr["min"]),
                             "price_max": pr.get("max"), "beds": fp.get("bedCount"), "baths": fp.get("bathCount"),
                             "sqft": sq.get("min"), "lat": loc.get("lat"), "lon": loc.get("lng"),
                             "locality": loc.get("city"), "address": b.get("name"),
                             "url": "https://www.rent.com" + (b.get("urlPathname") or ""), "kind": "unit"})
        if len(ls.get("listings", [])) < 30:
            break
    # one row per (building, beds): the lowest-priced floor plan (keeps big buildings from dominating)
    best = {}
    for r in rows:
        k = (r["url"], r["beds"])
        if k not in best or r["price"] < best[k]["price"]:
            best[k] = r
    return {"ok": ok_any, "url": base, "rows": list(best.values()), "total_buildings": total, "floorplans_seen": len(rows)}
