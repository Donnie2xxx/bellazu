"""FHA loan check for a home: county loan limits (HUD CY2026) + HUD's FHA-approved condo list + co-op / fixer / cash-only flags.
Data is prebuilt (no live calls from the app):
    python3 -m bellazu.sources.fha build      -> data/fha_limits_2026_nj.json  (HUD FHA Mortgage Limits lookup, entp.hud.gov/idapp/html/hicostlook.cfm)
                                              -> data/fha_condos_nj.json       (HUD condo lookup, entp.hud.gov/idapp/html/condlook.cfm, all statuses)
The lender always has the final say (appraisal/condition, the borrower's credit and income, single-unit approvals)."""
import datetime as dt, difflib, functools, json, pathlib, re, sys, time

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
LIMITS_F = DATA / "fha_limits_2026_nj.json"
CONDOS_F = DATA / "fha_condos_nj.json"
SEARCH = "https://entp.hud.gov/idapp/html/condlook.cfm"
RESULT = "https://entp.hud.gov/idapp/html/condo1.cfm"
LIMITS_URL = "https://entp.hud.gov/idapp/html/hicostlook.cfm"
FHA_DOWN, CONDO_CONV_DOWN, COOP_DOWN = 0.035, 0.10, 0.20

TOWN_COUNTY = {**{t: "HUDSON" for t in ("Bayonne", "Guttenberg", "Harrison", "Hoboken", "Jersey City", "Kearny", "North Bergen", "Secaucus", "Union City",
                                         "Weehawken", "West New York")},
               **{t: "BERGEN" for t in ("Bergenfield", "Cliffside Park", "East Rutherford", "Edgewater", "Englewood", "Englewood Cliffs", "Fairview", "Fort Lee",
                                         "Garfield", "Hackensack", "Hasbrouck Heights", "Leonia", "Little Ferry", "Lodi", "Lyndhurst", "North Arlington",
                                         "Palisades Park", "Ridgefield", "Ridgefield Park", "Rutherford", "Teaneck")},
               **{t: "ESSEX" for t in ("Belleville", "Bloomfield", "East Orange", "Irvington", "Montclair", "Newark", "Nutley", "West Orange")},
               **{t: "UNION" for t in ("Elizabeth", "Linden", "Rahway", "Union")},
               **{t: "PASSAIC" for t in ("Clifton", "Hawthorne", "Passaic", "Paterson")}}
COUNTIES = sorted(set(TOWN_COUNTY.values()))


# ------------------------------------------------------------------ builders (run offline, results committed under data/)
def _session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (BellaZu data builder; low volume)"
    return s


def build_limits():
    """All NJ counties, FHA forward limits CY2026, straight from HUD's lookup."""
    from bs4 import BeautifulSoup
    s = _session()
    s.get(LIMITS_URL, timeout=30)
    d = {"county_name": "", "county": "", "msa_name": "", "msa_code": "", "state": "NJ", "limit_type": "FHA", "limit_year": "CY2026",
         "last_upd_m": "", "last_upd_d": "", "last_upd_y": "", "in_fha": "No", "sorted": "county"}
    r = s.post("https://entp.hud.gov/idapp/html/hicost1.cfm", data=d, headers={"Referer": LIMITS_URL}, timeout=60)
    r.raise_for_status()
    out = {}
    for tr in BeautifulSoup(r.text, "html.parser").find_all("tr"):
        c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(c) >= 11 and c[5] == "NJ" if len(c) > 5 else False:
            pass
        m = [x for x in c if re.fullmatch(r"\$[\d,]+", x)]
        name = next((x for x in c if x.endswith("COUNTY") or re.search(r"COUNT?Y?$", x)), None)
        if name and len(m) >= 4 and "NJ" in c:
            key = re.sub(r"\s+COUNT?Y?$", "", name).strip()
            v = [int(x.replace("$", "").replace(",", "")) for x in m[:4]]
            out[key] = {"1": v[0], "2": v[1], "3": v[2], "4": v[3], "msa": c[1] if len(c) > 1 else ""}
    if len(out) < 15:
        raise RuntimeError(f"only {len(out)} NJ counties parsed")
    LIMITS_F.write_text(json.dumps({"year": "CY2026", "effective": "2026-01-01", "source": LIMITS_URL + " (FHA Forward, CY2026, state NJ)",
                                    "fetched": dt.date.today().isoformat(), "counties": out, "note": "msa = CBSA code"}, indent=1))
    return out


def _parse_rows(html):
    from bs4 import BeautifulSoup
    rows = []
    for tr in BeautifulSoup(html, "html.parser").find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 13:
            continue
        cid = tds[1].get_text(" ", strip=True)
        if not re.match(r"P\d{5,}", cid):
            continue
        addr_lines = [x.strip() for x in tds[2].get_text("\n", strip=True).split("\n") if x.strip()]
        city_line = addr_lines[-1] if addr_lines else ""
        mc = re.match(r"(.*?),\s*NJ\s*(\d{5})?", city_line)
        exp_txt = tds[12].get_text(" ", strip=True)
        rows.append({"name": re.sub(r"\*$", "", tds[0].get_text(" ", strip=True).split("*HOA")[0]).strip(),
                     "id": re.sub(r"\s+", " ", cid), "street": " ".join(addr_lines[:-1]), "city": (mc.group(1) if mc else city_line).strip().title(),
                     "zip": (mc.group(2) if mc else "") or "", "county": tds[3].get_text(" ", strip=True).replace(" COUNTY", ""),
                     "composition": tds[4].get_text(" ", strip=True)[:160], "status": tds[9].get_text(" ", strip=True),
                     "comments": tds[10].get_text(" ", strip=True), "status_date": tds[11].get_text(" ", strip=True),
                     "expires": exp_txt.split(" ")[0], "expired": "expired" in exp_txt.lower()})
    return rows


def build_condos(counties=COUNTIES):
    s = _session()
    s.get(SEARCH, timeout=30)
    allrows = []
    for c in counties:
        start, got = 1, []
        while True:
            d = {"FAPPROVAL_METHOD": "NEW", "FSORTED_BY": "condo_name", "FSTATE": "NJ", "FCOUNTY": c, "FCONDO_ID": "", "FCONDO_NAME": "", "FCITY": "",
                 "FZIP": "", "FSTATUS_CODE": "X", "FSEARCH_TYPE": "B", "FBEGIN_MO": "", "FBEGIN_DY": "", "FBEGIN_YR": "", "FEND_MO": "", "FEND_DY": "",
                 "FEND_YR": "", "CAME_FROM": "oth", "IN_FHAC": "true", "startAt": str(start), "maxRows": "500", "pageIn": SEARCH}
            for k in range(4):
                try:
                    r = s.post(RESULT, data=d, headers={"Referer": SEARCH}, timeout=90)
                    r.raise_for_status()
                    break
                except Exception:
                    if k == 3:
                        raise
                    time.sleep(5 * (k + 1))
                    s = _session()
                    s.get(SEARCH, timeout=30)
            rows = _parse_rows(r.text)
            m = re.search(r"\((\d+) records were selected", r.text)
            total = int(m.group(1)) if m else len(rows)
            got += rows
            print(f"  {c}: {len(got)}/{total}", file=sys.stderr)
            if not rows or len(got) >= total:
                break
            start += len(rows)
            time.sleep(1.5)
        allrows += got
        time.sleep(1.5)
    CONDOS_F.write_text(json.dumps({"source": SEARCH + " (state NJ, status: all, by county)", "fetched": dt.date.today().isoformat(),
                                    "counties": list(counties), "rows": allrows}, indent=0))
    return allrows


# ------------------------------------------------------------------ lookups used by the app
@functools.lru_cache(1)
def limits():
    try:
        return json.loads(LIMITS_F.read_text())
    except Exception:
        return {}


@functools.lru_cache(1)
def condos():
    try:
        return json.loads(CONDOS_F.read_text()).get("rows") or []
    except Exception:
        return []


def county_for(town):
    if not town:
        return None
    t = str(town).strip().lower()
    return next((c for k, c in TOWN_COUNTY.items() if k.lower() == t), None)


def loan_limit(town, units=1):
    c = county_for(town)
    L = (limits().get("counties") or {}).get(c or "")
    return (L or {}).get(str(max(1, min(int(units or 1), 4)))), c


ABBR = {"street": "st", "avenue": "ave", "av": "ave", "boulevard": "blvd", "road": "rd", "drive": "dr", "place": "pl", "terrace": "ter", "court": "ct",
        "lane": "ln", "parkway": "pkwy", "plaza": "plz", "highway": "hwy", "square": "sq", "north": "n", "south": "s", "east": "e", "west": "w",
        "circle": "cir", "harbor": "hbr", "point": "pt", "heights": "hts", "mount": "mt", "saint": "st", "first": "1st", "second": "2nd", "third": "3rd"}


def norm_street(s):
    """'1011 Avenue C Unit 4B' -> ('1011', 'ave c'); '7-9 Main Street #2' -> ('7', 'main st')."""
    s = str(s or "").lower().split(",")[0]
    s = re.sub(r"\b(apt|apartment|unit|ste|suite|fl|floor|#)\s*[\w-]*\s*$", "", s)
    s = re.sub(r"#\s*\w+", "", s)
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    w = s.split()
    if not w:
        return None, ""
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
    if w[0] in words:
        w[0] = words[w[0]]
    num = re.match(r"(\d+)", w[0])
    num = num.group(1) if num else None
    rest = [ABBR.get(x, x) for x in (w[1:] if num else w)]
    return num, " ".join(rest).strip()


def _num_range(s):
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\b", str(s or ""))
    return (int(m.group(1)), int(m.group(2))) if m and int(m.group(2)) > int(m.group(1)) else None


_NAME_STOP = {"condominium", "condominiums", "condo", "condos", "association", "assoc", "inc", "the", "at", "of", "phase", "a", "i", "ii", "iii", "iv",
              "homeowners", "hoa", "urban", "renewal", "llc", "residences", "residence"}


def _name_core(n):
    return [w for w in re.sub(r"[^a-z0-9\s]", " ", str(n).lower()).split() if w not in _NAME_STOP]


def _rank(r):
    st = (r.get("status") or "").lower()
    return (st == "approved" and not r.get("expired"), r.get("status_date", "")[-4:] + r.get("status_date", "")[:5])


def condo_match(address, town=None, zipcode=None, text=None):
    """Best HUD condo-list row for this listing, or None. Match by street number + street name (fuzzy), same town or ZIP;
    else by the project name appearing in the listing text (same town)."""
    rows = condos()
    if not rows:
        return None, "no_data"
    num, street = norm_street(address)
    tl = str(town or "").strip().lower()
    local = [r for r in rows if (tl and r.get("city", "").lower() == tl) or (zipcode and r.get("zip") == str(zipcode))]
    hits = []
    if num and street:
        for r in local:
            n2, s2 = norm_street(r.get("street"))
            rg = _num_range(r.get("street"))
            same_no = n2 == num or (rg and rg[0] <= int(num) <= rg[1] and (int(num) - rg[0]) % 2 == 0)
            if same_no and s2 and difflib.SequenceMatcher(None, s2, street).ratio() >= 0.82:
                hits.append(r)
    how = "address"
    if not hits and text:
        low = " " + re.sub(r"[^a-z0-9\s]", " ", str(text).lower()) + " "
        for r in local:
            core = _name_core(r.get("name"))
            if len(core) >= 2 and len(" ".join(core)) >= 8 and f" {' '.join(core)} " in low:
                hits.append(r)
        how = "name"
    if not hits:
        return None, "none"
    return sorted(hits, key=_rank, reverse=True)[0], how


def _mmyyyy(d):
    m = re.match(r"(\d{2})/\d{2}/(\d{4})", str(d or ""))
    return f"{m.group(1)}/{m.group(2)}" if m else None


FLAG_RX = [("cash", r"\bcash[\s-]*only\b|\bcash buyers? only\b|\bcash or (hard money|rehab loan)\b|\bno financing\b", ("Cash only in the listing", "El anuncio dice solo efectivo")),
           ("asis", r"\bas[\s-]is\b", ("Sold as-is", "Se vende tal cual (as-is)")),
           ("rehab", r"\bneeds? (some |major |a lot of )?(work|tlc|rehab|renovation|updating)\b|\bhandyman\b|\bfixer\b|\bgut (rehab|renovation)\b|\binvestor special\b|\bcontractor special\b|\brehab\b",
            ("Needs work", "Necesita arreglos")),
           ("auction", r"\bauction\b|\bforeclosure auction\b|\bsheriff'?s? sale\b", ("Auction", "Subasta")),
           ("mobile", r"\bmanufactured (home|housing)\b|\bmobile home\b|\bmodular home\b", ("Manufactured / mobile home", "Casa prefabricada / móvil"))]


def listing_flags(text=None, flags=None, ptype=None):
    t = " ".join([str(text or "")] + [k for k, v in (flags or {}).items() if v] if isinstance(flags, dict) else [str(text or "")]).lower().replace("_", " ")
    out = []
    for k, rx, lbl in FLAG_RX:
        if re.search(rx, t):
            out.append(k)
    if ptype and re.search(r"mobile|manufactured", str(ptype).lower()) and "mobile" not in out:
        out.append("mobile")
    return out


def assess(kind, price=None, town=None, address=None, zipcode=None, text=None, flags=None, units=None):
    """kind: condo | coop | house | 2fam | 3-4fam | other. Returns the badge, the loan to model and the down payment.
    code: ok (FHA 3.5%), condo_ok, condo_no, condo_unknown, coop, over_limit, unknown."""
    k = str(kind or "").lower()
    fl = listing_flags(text, flags, kind)
    u = 4 if k in ("3-4fam", "3-4-family") and (units or 3) >= 4 else 3 if k in ("3-4fam", "3-4-family") else 2 if k in ("2fam", "multi-family", "2-family") else 1
    lim, county = loan_limit(town, units or u)
    res = {"flags": fl, "limit": lim, "county": county, "units": units or u, "match": None, "how": None, "exp": None}
    if "coop" in k or "co-op" in k:
        return dict(res, code="coop", loan="conv", down=COOP_DOWN)
    if "cash" in fl:
        res["cash_only"] = True
    if price and lim and float(price) * (1 - FHA_DOWN) > lim:
        return dict(res, code="over_limit", loan="conv", down=0.20 if float(price) > lim * 1.2 else CONDO_CONV_DOWN)
    if "condo" in k:
        m, how = condo_match(address, town, zipcode, text)
        res.update(match=m, how=how)
        if m and (m.get("status") or "").lower() == "approved" and not m.get("expired"):
            return dict(res, code="condo_ok", loan="fha", down=FHA_DOWN, exp=_mmyyyy(m.get("expires")))
        if m:
            return dict(res, code="condo_no", loan="conv", down=CONDO_CONV_DOWN, exp=_mmyyyy(m.get("expires")))
        return dict(res, code="condo_unknown", loan="conv", down=CONDO_CONV_DOWN)
    if k in ("house", "single-family", "2fam", "multi-family", "2-family", "3-4fam", "3-4-family", "townhouse"):
        return dict(res, code="ok", loan="fha", down=FHA_DOWN)
    return dict(res, code="unknown", loan="fha", down=FHA_DOWN)


def badge(a):
    """(en, es) one-line badge for an assess() result."""
    c = a.get("code")
    if c == "ok":
        return ("✅ FHA OK · 3.5% down (you live there + it passes the FHA appraisal)", "✅ FHA sí · 3.5% inicial (usted vive allí + pasa el avalúo FHA)")
    if c == "condo_ok":
        e = a.get("exp")
        return (f"✅ FHA approved building (until {e})" if e else "✅ FHA approved building", f"✅ Edificio aprobado por FHA (hasta {e})" if e else "✅ Edificio aprobado por FHA")
    if c == "condo_no":
        return ("⚠️ Approval expired / not on FHA list: needs normal loan or single-unit approval, ask lender",
                "⚠️ Aprobación vencida / no está en la lista FHA: necesita préstamo normal o aprobación de unidad individual, pregunte al banco")
    if c == "condo_unknown":
        return ("❓ Couldn't confirm the building: ask lender", "❓ No pudimos confirmar el edificio: pregunte al banco")
    if c == "coop":
        return ("🚫 Co-op: no FHA · co-op loan, usually 10-20% down + board approval", "🚫 Co-op: sin FHA · préstamo de co-op, por lo general 10-20% inicial + aprobación de la junta")
    if c == "over_limit":
        return (f"⚠️ Above the {a.get('county', '').title()} County FHA limit (${a.get('limit', 0):,}): normal loan",
                f"⚠️ Por encima del límite FHA del condado de {a.get('county', '').title()} (${a.get('limit', 0):,}): préstamo normal")
    return ("❓ Home type unknown: FHA if you live there and it passes the appraisal, ask lender", "❓ Tipo de casa desconocido: FHA si vive allí y pasa el avalúo, pregunte al banco")


FLAG_NOTE = {"cash": ("Cash only: the seller won't take a loan, so FHA (or any mortgage) won't work unless that changes.",
                      "Solo efectivo: el vendedor no acepta préstamo, así que FHA (ni otra hipoteca) sirve a menos que cambie."),
             "asis": ("As-is: FHA still works only if the home passes the FHA appraisal (safe, sound, working systems). An FHA 203(k) loan can wrap repairs into the loan.",
                      "Tal cual: FHA solo funciona si la casa pasa el avalúo FHA (segura, sólida, sistemas funcionando). Un préstamo FHA 203(k) puede incluir las reparaciones."),
             "rehab": ("Needs work: FHA needs the home to pass its appraisal; for a fixer, ask about an FHA 203(k) rehab loan.",
                       "Necesita arreglos: FHA exige pasar su avalúo; para una casa a reparar, pregunte por un préstamo FHA 203(k)."),
             "auction": ("Auction: usually cash or proof of funds, fast closing, no inspection. Hard to use FHA.",
                         "Subasta: por lo general efectivo o prueba de fondos, cierre rápido, sin inspección. Difícil usar FHA."),
             "mobile": ("Manufactured / mobile: FHA has special rules (permanent foundation, built after June 1976, owned land). Ask lender.",
                        "Prefabricada / móvil: FHA tiene reglas especiales (cimiento permanente, hecha después de junio de 1976, terreno propio). Pregunte al banco.")}


def stats():
    rows = condos()
    ap = [r for r in rows if (r.get("status") or "").lower() == "approved" and not r.get("expired")]
    return {"rows": len(rows), "approved_now": len(ap), "fetched": (json.loads(CONDOS_F.read_text()).get("fetched") if CONDOS_F.exists() else None)}


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        lim = build_limits() if "--condos-only" not in sys.argv else limits()["counties"]
        print("limits:", {k: lim[k] for k in COUNTIES if k in lim})
        rows = build_condos()
        print("condos:", len(rows), stats())
