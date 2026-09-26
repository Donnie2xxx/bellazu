"""Listing facts for a for-sale address.
Priority: manual overrides > listing_url page parse > RentCast (if key, only for missing fields) (Zillow / Redfin / Coldwell /
any page with JSON-LD) > nothing (report asks the user to fill fields). Portals often block
automated fetches (Zillow/Trulia/StreetEasy/Realtor = 403/429 intermittently), so the core never
depends on them."""
import re, json
from bs4 import BeautifulSoup
from ..http import fetch
from . import rentcast

FIELDS = ["price", "beds", "baths", "sqft", "hoa_monthly", "taxes_annual", "ownership", "year_built",
          "lat", "lon", "description", "status", "hoa_includes"]


def _find(o, pred, depth=0):
    if depth > 9:
        return None
    if isinstance(o, dict):
        if pred(o):
            return o
        for v in o.values():
            r = _find(v, pred, depth + 1)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find(v, pred, depth + 1)
            if r is not None:
                return r
    return None


def _zillow(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    d = json.loads(m.group(1))
    g = _find(d, lambda x: "gdpClientCache" in x)
    g = g.get("gdpClientCache") if g else None
    if isinstance(g, str):
        g = json.loads(g)
    p = _find(g, lambda x: "monthlyHoaFee" in x and "price" in x) if g else None
    if not p:
        return {}
    rf = p.get("resoFacts") or {}
    sub = " ".join(rf.get("propertySubType") or [])
    own = "co-op" if ("Cooperative" in sub or "co-op" in (p.get("description") or "").lower()) else (
        "condo" if p.get("homeType") == "CONDO" else (p.get("homeType") or "").lower())
    tax = p.get("taxAnnualAmount") or rf.get("taxAnnualAmount")
    th = p.get("taxHistory") or []
    if not tax and th:
        tax = th[0].get("taxPaid")
    return {"price": p.get("price"), "beds": p.get("bedrooms"), "baths": p.get("bathrooms"),
            "sqft": p.get("livingArea"), "hoa_monthly": p.get("monthlyHoaFee"), "taxes_annual": tax,
            "ownership": own, "year_built": p.get("yearBuilt"), "lat": p.get("latitude"), "lon": p.get("longitude"),
            "description": p.get("description"), "status": p.get("homeStatus"),
            "rent_zestimate": p.get("rentZestimate")}


def _generic(html):
    out = {}
    for b in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(b)
        except Exception:
            continue
        for x in (d if isinstance(d, list) else d.get("@graph", [d])):
            if not isinstance(x, dict):
                continue
            off = x.get("offers")
            if isinstance(off, dict) and off.get("price") and "price" not in out:
                try: out["price"] = float(str(off["price"]).replace(",", ""))
                except Exception: pass
            if x.get("numberOfRooms") and "beds" not in out:
                out["beds"] = x.get("numberOfRooms")
            fs = x.get("floorSize")
            if isinstance(fs, dict) and fs.get("value") and "sqft" not in out:
                out["sqft"] = fs.get("value")
            geo = x.get("geo")
            if isinstance(geo, dict) and "lat" not in out:
                out["lat"], out["lon"] = geo.get("latitude"), geo.get("longitude")
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    m = re.search(r"(?:Maintenance|HOA|Association)[^$]{0,40}\$\s?([\d,]{3,7})", text, re.I)
    if m: out.setdefault("hoa_monthly", float(m.group(1).replace(",", "")))
    m = re.search(r"(?:Annual\s+)?Tax(?:es)?(?:\s+Amount)?[:\s]{1,5}\$\s?([\d,]{3,7})", text, re.I)
    if m: out.setdefault("taxes_annual", float(m.group(1).replace(",", "")))
    if re.search(r"\bco-?op\b|cooperative", text, re.I): out.setdefault("ownership", "co-op")
    elif re.search(r"\bcondo", text, re.I): out.setdefault("ownership", "condo")
    return out


def includes_from_text(desc):
    d = (desc or "").lower()
    inc = []
    if re.search(r"property tax|taxes", d): inc.append("taxes")
    if re.search(r"all utilities|electric", d): inc.append("utilities")
    elif re.search(r"heat|hot water|gas", d): inc.append("heat/hot water")
    if re.search(r"internet|cable", d): inc.append("internet")
    return inc


def _rc_type(pt):
    pt = (pt or "").lower()
    return {"single family": "single-family", "multi-family": "multi-family", "condo": "condo", "townhouse": "townhouse",
            "apartment": "condo", "manufactured": "manufactured"}.get(pt, pt)


def get_facts(address, listing_url=None, overrides=None, use_rentcast=True):
    """Priority: user input > listing page > RentCast (only called for fields still missing, to save quota)."""
    facts, src = {}, {}
    rc_meta = {"sale_listing": None, "property_record": None}
    for url in ([listing_url] if isinstance(listing_url, str) else (listing_url or [])):
        if not url or not str(url).startswith("http"):
            continue
        html = fetch(url, "listing_page:" + url.split("/")[2], ttl_hours=24, min_interval=3,
                     validate=lambda t: ("Access to this page has been denied" not in t and "captcha" not in t.lower()[:5000]))
        if not html:
            continue
        parsed = _zillow(html) if "zillow.com" in url else {}
        g = _generic(html)
        for k, v in g.items():
            parsed.setdefault(k, v)
        for k, v in parsed.items():
            if v not in (None, "", 0) and k not in facts:
                facts[k], src[k] = v, url
    for k, v in (overrides or {}).items():
        if v is not None:
            facts[k], src[k] = v, "user input"

    def put(k, v, label):
        if v not in (None, "", 0) and k not in facts:
            facts[k], src[k] = v, label

    if use_rentcast and rentcast.available():
        if any(not facts.get(k) for k in ("price", "beds", "hoa_monthly")):
            r, s = rentcast.sale_listing(address)
            rc_meta["sale_listing"] = s if r else (s if s not in ("ok", "cache") else "not_found")
            if r:
                lab = "RentCast sale listing"
                put("price", r.get("price"), lab); put("beds", r.get("bedrooms"), lab); put("baths", r.get("bathrooms"), lab)
                put("sqft", r.get("squareFootage"), lab); put("hoa_monthly", (r.get("hoa") or {}).get("fee"), lab)
                put("lat", r.get("latitude"), lab); put("lon", r.get("longitude"), lab); put("ownership", _rc_type(r.get("propertyType")), lab)
                put("year_built", r.get("yearBuilt"), lab); put("status", r.get("status"), lab)
                put("days_on_market", r.get("daysOnMarket"), lab); put("mls", f"{r.get('mlsName') or ''} {r.get('mlsNumber') or ''}".strip(), lab)
        own = (facts.get("ownership") or "").lower()
        taxes_in_hoa = "taxes" in [x.lower() for x in (facts.get("hoa_includes") or [])]
        if facts.get("taxes_annual") in (None, "") and not ("co-op" in own and taxes_in_hoa):
            rec, s = rentcast.property_record(address)
            rc_meta["property_record"] = s if rec else (s if s not in ("ok", "cache") else "not_found")
            if rec:
                tax, yr = rentcast.latest_tax(rec)
                lab = "RentCast property record"
                put("taxes_annual", tax, f"{lab} ({yr} tax)" if yr else lab)
                put("beds", rec.get("bedrooms"), lab); put("baths", rec.get("bathrooms"), lab); put("sqft", rec.get("squareFootage"), lab)
                put("hoa_monthly", (rec.get("hoa") or {}).get("fee"), lab); put("year_built", rec.get("yearBuilt"), lab)
                put("ownership", _rc_type(rec.get("propertyType")), lab)
                put("lat", rec.get("latitude"), lab); put("lon", rec.get("longitude"), lab)
    if "hoa_includes" not in facts:
        facts["hoa_includes"] = includes_from_text(facts.get("description"))
        if facts["hoa_includes"]:
            src["hoa_includes"] = "parsed from listing description"
    return facts, src, rc_meta
