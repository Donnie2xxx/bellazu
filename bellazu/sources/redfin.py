"""Redfin rentals (opportunistic). First request from a fresh IP usually works; repeated requests
get an AWS-WAF challenge (HTTP 202, empty body) -> treated as blocked. Stingray APIs are 403."""
import re, json
from ..http import fetch

CITY_IDS = {"fort lee": 6283}   # add more as discovered (from redfin.com/city/<id>/NJ/<Town> URLs)


def rentals(town, state="NJ"):
    cid = CITY_IDS.get(town.lower())
    if not cid:
        return {"ok": False, "rows": [], "note": "Redfin city id unknown (add to CITY_IDS)"}
    slug = town.title().replace(" ", "-")
    url = f"https://www.redfin.com/city/{cid}/{state}/{slug}/apartments-for-rent"
    html = fetch(url, "redfin:rentals", ttl_hours=12, min_interval=4, validate=lambda t: "application/ld+json" in t)
    if not html:
        return {"ok": False, "rows": [], "url": url}
    rows, acc = [], {}
    for b in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(b)
        except Exception:
            continue
        for x in d if isinstance(d, list) else [d]:
            if x.get("@type") == "Accommodation":
                acc[x.get("url")] = x
            if x.get("@type") == "Product" and x.get("url") in acc:
                a = acc[x["url"]]
                beds = str(a.get("numberOfRooms", ""))
                try:
                    bmin = int(beds.split("-")[0])
                except Exception:
                    bmin = None
                rows.append({"source": "Redfin", "title": a.get("name"), "price": int(float(x["offers"]["price"])),
                             "beds": bmin, "beds_range": beds, "baths": None,
                             "sqft": (a.get("floorSize") or {}).get("value"), "lat": a["geo"]["latitude"],
                             "lon": a["geo"]["longitude"], "locality": a["address"].get("addressLocality"),
                             "address": a["address"].get("streetAddress"), "url": x["url"], "kind": "unit"})
    return {"ok": True, "rows": rows, "url": url}
