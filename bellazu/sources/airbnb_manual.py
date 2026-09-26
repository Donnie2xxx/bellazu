"""MANUAL / BROWSER STEP. Airbnb search pages (/s/<place>/homes) are disallowed for crawlers by
airbnb.com/robots.txt ("Disallow: /s/*/*"), so BellaZu never fetches them. A human (or an assistant
driving a browser with the user's OK) can open the search for real dates, then File > Save Page As
(HTML) into manual_inputs/. This parser extracts nightly price, bedrooms, rating/reviews, lat/lon."""
import re, json


def parse_saved_search(path):
    html = open(path, encoding="utf-8", errors="replace").read()
    out = []
    for m in re.finditer(r'<script id="data-deferred-state-\d+"[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        stack = [d]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if "structuredDisplayPrice" in o and "demandStayListing" in o:
                    out.append(_row(o))
                    continue
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return out


def _row(o):
    s = json.dumps(o, ensure_ascii=False)
    nightly = None
    m = re.search(r'(\d+) nights? x \$([\d,]+(?:\.\d+)?)', s)
    if m:
        nightly = float(m.group(2).replace(",", ""))
    beds = None
    m = re.search(r'"body": "(\d+) bedrooms?"', s)
    if m:
        beds = int(m.group(1))
    elif '"Studio"' in s:
        beds = 0
    rating, reviews = None, None
    m = re.match(r"([\d.]+) \((\d+)\)", o.get("avgRatingLocalized") or "")
    if m:
        rating, reviews = float(m.group(1)), int(m.group(2))
    loc = ((o.get("demandStayListing") or {}).get("location") or {}).get("coordinate") or {}
    dates = re.search(r'"body": "([A-Z][a-z]{2} \d+[^"]{1,20})", "bodyA11yLabel": null, "bodyType": null, "fontWeight": null, "headline": null, "type": "DATE"', s)
    return {"source": "Airbnb (saved page, manual)", "title": o.get("title"), "subtitle": o.get("subtitle"),
            "nightly": nightly, "beds": beds, "rating": rating, "reviews": reviews,
            "lat": loc.get("latitude"), "lon": loc.get("longitude"), "dates": dates.group(1) if dates else None}
