"""Craigslist apartments (cat=apa) and rooms (cat=roo). Search pages allowed by robots.txt.
Parses the JSON-LD (beds, baths, lat/lon) + static list (price, url, title), which align 1:1."""
import re, json
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from ..http import fetch


def town_slug(town, state="nj"):
    return re.sub(r"[^a-z0-9]+", "-", town.lower()).strip("-") + "-" + state.lower()


def search(town, state="nj", cat="apa", min_beds=None, max_beds=None, postal=None, radius_mi=None):
    q = {"cat": cat}
    if min_beds is not None: q["min_bedrooms"] = min_beds
    if max_beds is not None: q["max_bedrooms"] = max_beds
    if postal: q["postal"] = postal
    if radius_mi: q["radius"] = radius_mi
    url = f"https://www.craigslist.org/search/city/{town_slug(town, state)}?{urlencode(q)}"
    html = fetch(url, f"craigslist:{cat}", ttl_hours=12, min_interval=3, retries=3,
                 validate=lambda t: "cl-static-search-result" in t or "ld_searchpage_results" in t)
    if not html:
        return {"ok": False, "url": url, "rows": []}
    m = re.search(r'id="ld_searchpage_results"[^>]*>(.*?)</script>', html, re.S)
    items = json.loads(m.group(1)).get("itemListElement", []) if m else []
    lis = BeautifulSoup(html, "lxml").select("li.cl-static-search-result")
    rows = []
    for i, li in enumerate(lis):
        it = items[i]["item"] if i < len(items) else {}
        ptxt = li.select_one(".price").get_text() if li.select_one(".price") else ""
        price = int(re.sub(r"[^\d]", "", ptxt)) if re.search(r"\d", ptxt) else None
        a = it.get("address", {}) if isinstance(it.get("address"), dict) else {}
        rows.append({"source": "Craigslist", "title": li.get("title") or it.get("name"),
                     "price": price, "beds": it.get("numberOfBedrooms"),
                     "baths": it.get("numberOfBathroomsTotal"), "sqft": None,
                     "lat": it.get("latitude"), "lon": it.get("longitude"),
                     "locality": (li.select_one(".location").get_text(strip=True) if li.select_one(".location") else None) or a.get("addressLocality"),
                     "geo_locality": a.get("addressLocality"),
                     "address": a.get("streetAddress") or "",
                     "url": li.a.get("href") if li.a else url, "kind": "room" if cat == "roo" else "unit"})
    return {"ok": True, "url": url, "rows": rows}
