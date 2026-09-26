"""HUD FHA-approved condominium lookup (entp.hud.gov). Public search form (read-only query).
Needs the session cookie from the search page first. Co-ops are NOT in this list: FHA generally
does not insure co-op share loans (Section 203(n) exists but few lenders offer it)."""
import re, requests
from bs4 import BeautifulSoup
from ..http import fetch, UA_BROWSER, record

SEARCH = "https://entp.hud.gov/idapp/html/condlook.cfm"
RESULT = "https://entp.hud.gov/idapp/html/condo1.cfm"


def lookup_zip(zipcode, state="NJ"):
    s = requests.Session()
    s.headers.update({"User-Agent": UA_BROWSER})
    try:
        s.get(SEARCH, timeout=30)
    except Exception as e:
        record("hud:fha_condo", SEARCH, False, None, str(e))
        return None
    data = {"fapproval_method": "NEW", "fsorted_by": "condo_name", "fstate": state, "fcounty": "", "fcondo_id": "",
            "fcondo_name": "", "fcity": "", "fzip": zipcode, "fstatus_code": "X", "fsearch_type": "B",
            "fbegin_mo": "", "fbegin_dy": "", "fbegin_yr": "", "fend_mo": "", "fend_dy": "", "fend_yr": "",
            "came_from": "oth", "in_fhac": "true"}
    html = fetch(RESULT, "hud:fha_condo", ttl_hours=24 * 7, method="POST", data=data, session=s,
                 headers={"Referer": SEARCH}, validate=lambda t: "Condominiums List" in t)
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) >= 10 and re.search(r"\bP\d{5,}", " ".join(tds[:2])):
            rows.append({"name": tds[0], "id_address": tds[1], "county": tds[2], "composition": tds[3],
                         "status": tds[-4] if len(tds) >= 12 else "", "raw": " | ".join(tds)})
    return {"zip": zipcode, "rows": rows, "source": SEARCH}


def match_building(rows, street):
    if not rows:
        return []
    key = re.sub(r"\s+", " ", street.upper())
    num = key.split(" ")[0]
    name = " ".join(key.split(" ")[1:2])
    return [r for r in rows if name and name in r["raw"].upper() and num in r["raw"].upper()]
