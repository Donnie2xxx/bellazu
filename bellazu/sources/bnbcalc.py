"""Optional cross-check: a PUBLIC BNBCalc analysis URL (bnbcalc.com/analysis/<slug>/<id>).
robots.txt allows crawling. Only headline numbers are public; comps require a BNBCalc account."""
import re
from bs4 import BeautifulSoup
from ..http import fetch


def parse_analysis(url):
    html = fetch(url, "bnbcalc:analysis", ttl_hours=24 * 7)
    if not html:
        return None
    t = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    out = {"url": url, "title": (BeautifulSoup(html, "lxml").title or "").get_text() if html else None}
    m = re.search(r"(\d+)(?:st|nd|rd|th) revenue percentile \$([\d,]+) Annual Revenue", t)
    if m:
        out["revenue_percentile"], out["annual_revenue"] = int(m.group(1)), int(m.group(2).replace(",", ""))
    m = re.search(r'occupancyRatePercentage\\?"?:\s*(\d+)', html)
    if m:
        out["occupancy_pct"] = int(m.group(1))
    return out
