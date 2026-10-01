"""NYC / near-Manhattan box: homes up to $300K, a curated top 15 of 2-bedrooms, and the flags that matter for a first home that may be rented out later.
Pure Python (no Streamlit). The data is a dated snapshot of realtor.com list calls (data/nyc_homes.json, shipped only as the encrypted data/nyc_homes.lock);
nothing here calls an API. Money (monthly total, approval tag) comes from the app's own home_money(), passed in as a function."""
import base64, json, pathlib, re, zlib

from . import keylock

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAIN = ROOT / "data" / "nyc_homes.json"          # readable copy (source tree only)
LOCK = ROOT / "data" / "nyc_homes.lock"           # what ships: the same snapshot, compressed and encrypted with the app passcode
TOP_N = 15
PER_BUILDING = 2                                    # at most this many units of one building in the top list (variety)
MIN_SQFT_2BR = 500                                  # under this a "2 bedroom" is probably a small 1BR: flagged
AREAS = {"all": ("All areas", "Todas las zonas"), "manhattan": ("Manhattan", "Manhattan"), "bronx": ("Bronx", "Bronx"),
         "bkq": ("Brooklyn & Queens", "Brooklyn y Queens"), "nj": ("Hudson River NJ", "NJ junto al río Hudson"), "other": ("Other NY", "Otros de NY")}
_MEMO = {}


def pack(plain_json):
    return base64.b64encode(zlib.compress(plain_json.encode(), 9)).decode()


def unpack(txt):
    return zlib.decompress(base64.b64decode(txt)).decode()


def load(passcode=None):
    """The snapshot dict or None. Plain JSON when it exists (source tree), else the encrypted lock opened with the passcode (memoized)."""
    try:
        if PLAIN.exists():
            k = ("plain", PLAIN.stat().st_mtime)
            if k not in _MEMO:
                _MEMO.clear()
                _MEMO[k] = json.loads(PLAIN.read_text())
            return _MEMO[k]
        if LOCK.exists() and passcode:
            k = ("lock", passcode)
            if k not in _MEMO:
                t = keylock.unlock(LOCK, passcode)
                _MEMO.clear()
                _MEMO[k] = json.loads(unpack(t)) if t else None
            return _MEMO[k]
    except Exception:
        return None
    return None


def building(addr):
    """'201 45th St Apt E4, Union City, NJ 07087' -> '201 45th st|union city' (units of one building share it)."""
    parts = str(addr or "").split(",")
    s = re.sub(r"\b(apt|apartment|unit|ste|suite|fl|floor|#)\s*[\w/-]*\s*$", "", parts[0].lower()).strip()
    s = re.sub(r"\b(unit|apt|#)\s*[\w/-]+", "", s).strip()
    return s + "|" + (parts[1].strip().lower() if len(parts) > 1 else "")


def is_coop(r, hi=None):
    return (hi or {}).get("kind") == "coop" or r.get("type") in ("coop", "condop")


def _n(v):
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(v, str(v))


def rent_note(r, hi=None):
    """(level, en, es): is renting this home out later realistic? level 'ok' (condo: usually yes, confirm), 'ask' (co-op or unknown: the board decides) or
    'restrict' (the listing or the building's policy shows limits). Only what the listing/policy files say; otherwise it says to ask."""
    f = r.get("nyc") or {}
    pol = f.get("policy")
    if pol:
        return "restrict", "Co-op: " + pol["en"], "Co-op: " + pol["es"]
    if f.get("fractional"):
        return "restrict", "Fractional / timeshare ownership (a few weeks a year), not a regular home to live in or rent out.", \
            "Propiedad fraccionada / tiempo compartido (pocas semanas al año), no es una vivienda normal para vivir o alquilar."
    if f.get("hdfc"):
        a = f" ({f['ami']}% AMI)" if f.get("ami") else ""
        return "restrict", f"HDFC co-op, income-restricted{a}: buyer income limit and resale/flip-tax rules, and renting out is usually not allowed or needs board approval.", \
            f"Co-op HDFC con límite de ingresos{a}: límite de ingreso del comprador, reglas de reventa/impuesto de venta, y alquilarla normalmente no se permite o necesita aprobación de la junta."
    if f.get("income_restricted"):
        return "restrict", "Income-restricted (affordable housing): the buyer's income is capped and resale/renting rules apply. Ask for the deed restriction.", \
            "Con restricción de ingresos (vivienda asequible): el ingreso del comprador tiene tope y hay reglas de reventa y alquiler. Pida la restricción de la escritura."
    if f.get("sublet_no"):
        return "restrict", "Co-op: the listing says subletting is not allowed.", "Co-op: el anuncio dice que no se permite subarrendar."
    if f.get("sublet_after"):
        n = f["sublet_after"]
        return "restrict", f"Co-op: the listing says it may be rented only after {n} years of ownership (board rules apply).", \
            f"Co-op: el anuncio dice que solo se puede alquilar después de {n} años de ser dueño (aplican las reglas de la junta)."
    if f.get("sublet_board"):
        return "ask", "Co-op: subletting only case by case with board approval. Get the sublet policy in writing.", \
            "Co-op: subarriendo solo caso por caso con aprobación de la junta. Pida la política de subarriendo por escrito."
    if r.get("type") == "apartment" and not is_coop(r, hi):
        return "ask", "Listed only as an \"apartment\": in NYC that is often a co-op. Ask if it is a condo or a co-op, and for the sublet rules.", \
            "Anunciada solo como \"apartamento\": en NYC muchas veces es un co-op. Pregunte si es condo o co-op, y las reglas de subarriendo."
    if is_coop(r, hi):
        return "ask", "Co-op: the board decides if you may rent it out; many cap or ban subletting. Ask for the sublet policy before you bid.", \
            "Co-op: la junta decide si puede alquilarla; muchas limitan o prohíben el subarriendo. Pida la política de subarriendo antes de ofertar."
    if r.get("kind") == "house":
        return "ok", "House: no building rules on renting it out (check local rental licensing).", "Casa: sin reglas de edificio para alquilarla (revise la licencia de alquiler local)."
    return "ok", "Condo: usually free to rent out, but ask for the bylaws (some have rental caps or waiting periods).", \
        "Condo: normalmente se puede alquilar, pero pida los estatutos (algunos tienen límites o esperas para alquilar)."


def rent_short(r, hi=None):
    lv, en, es = rent_note(r, hi)
    if (r.get("nyc") or {}).get("fractional"):
        return lv, "Fractional timeshare, not a normal home", "Tiempo compartido fraccionado, no es una casa normal"
    if (r.get("nyc") or {}).get("policy"):
        return lv, "Co-op: sublet only with board approval, 8-yr cap", "Co-op: subarriendo solo con la junta, máx. 8 años"
    if (r.get("nyc") or {}).get("hdfc"):
        return lv, "HDFC co-op: income limit, renting restricted", "Co-op HDFC: límite de ingresos, alquiler restringido"
    if (r.get("nyc") or {}).get("income_restricted"):
        return lv, "Income-restricted: resale/renting limits", "Con tope de ingresos: límites de reventa/alquiler"
    if (r.get("nyc") or {}).get("sublet_after"):
        return lv, f"Co-op: rent only after {r['nyc']['sublet_after']} yrs", f"Co-op: alquilar solo tras {r['nyc']['sublet_after']} años"
    if (r.get("nyc") or {}).get("sublet_board"):
        return lv, "Co-op: sublet by board approval only", "Co-op: subarriendo solo con la junta"
    if r.get("type") == "apartment" and not is_coop(r, hi):
        return lv, "Type unclear (often a co-op): ask, and ask the sublet rules", "Tipo poco claro (a menudo co-op): pregunte y pregunte las reglas de subarriendo"
    if is_coop(r, hi):
        return lv, "Co-op: renting is up to the board, ask", "Co-op: alquilar depende de la junta, pregunte"
    if r.get("kind") == "house":
        return lv, "House: no building rental rules", "Casa: sin reglas de edificio"
    return lv, "Condo: usually rentable, confirm bylaws", "Condo: normalmente se puede alquilar, confirme estatutos"


def type_label(r, hi=None):
    if (r.get("nyc") or {}).get("fractional"):
        return "Timeshare", "Tiempo compartido"
    if r.get("type") == "condop":
        return "Condop", "Condop"
    if r.get("type") == "apartment" and not is_coop(r, hi):
        return "Apartment (type?)", "Apartamento (¿tipo?)"
    if is_coop(r, hi):
        return "Co-op", "Co-op"
    return {"condo": ("Condo", "Condo"), "house": ("House", "Casa"), "2fam": ("2-family", "2 familias")}.get(r.get("kind"), ("Home", "Vivienda"))


def small_flag(r):
    s = r.get("sqft")
    return bool(r.get("beds") == 2 and s and 100 < float(s) < MIN_SQFT_2BR)


def confirmed(h, hm):
    """True when BOTH halves of the monthly total are real: the fee (listing or agent, not an estimate) and the taxes (listing's tax bill, or inside a co-op's maintenance)."""
    hi = hm.get("hoa") or {}
    fee_ok = hi.get("state") == "real" or (hi.get("state") == "none" and h.get("kind") == "house")
    return bool(fee_ok and (hm.get("m") or {}).get("tax_src") in ("listing", "in"))


def nyc_tag(h, hm, ap, max_price):
    """The approval tag for this box: 'over' (price above the cap), 'monthly' (price OK but the monthly total is above the benchmark: yellow, never green),
    'ok' (GREEN: monthly at or under the benchmark AND fee + taxes confirmed), 'unk' (gray: looks under the benchmark but the fee or taxes are missing/estimated)."""
    if not hm:
        return "unk"
    if (h.get("price") or 0) > max_price:
        return "over"
    if hm["m"]["total"] > ap + 0.5:
        return "monthly"
    return "ok" if confirmed(h, hm) else "unk"


def score(r, hm, hud2, ap, hi):
    """Higher = better for a first home to live in for about a year and then rent or sell. Parts (max): monthly under the benchmark 40 (25 + up to 15 for room;
    only with a confirmed fee and taxes), rent-out friendliness 25, HUD rent vs cost 15, closeness to Midtown 10, listing freshness 5; minus: over the benchmark
    (-20 and more), restricted co-op / timeshare (-25), unusually small '2 bedroom' (-6), listed over a year (-3). Returns (score, parts dict)."""
    t = hm["m"]["total"]
    pts = {}
    if t > ap + .5:
        pts["monthly"] = -20 - min((t - ap) / ap, .5) * 40
    elif confirmed(r, hm):
        pts["monthly"] = 25 + 15 * min(max((ap - t) / ap, 0) / 0.12, 1)
    else:
        pts["monthly"] = 6
    pts["rent"] = {"ok": 25, "ask": 8, "restrict": -25}[rent_note(r, hi)[0]]
    pts["demand"] = 15 * min((hud2 or 0) / max(t, 1), 1.1) / 1.1 if hud2 else 5
    pts["near"] = 10 * (1 - min(float(r.get("mi") or 9), 9) / 9)
    d = r.get("days")
    pts["fresh"] = 5 if (d is not None and d <= 45) else 2 if (d is not None and d <= 120) else 0
    pts["small"] = -6 if small_flag(r) else 0
    pts["stale"] = -3 if (d is not None and d > 365) else 0
    return sum(pts.values()), pts


def pick_top(rows, money, hud, ap, n=TOP_N, beds=2):
    """The ranked top n of true `beds`-bedroom homes (listing says exactly that many beds), best first, at most PER_BUILDING per building. money(h) -> home_money dict
    (or None), hud(zip, beds) -> HUD fair rent for that size or None. Skips pending/contingent listings, timeshare units and anything over the price cap.
    If fewer than n true matches exist, the rest are filled with the CLOSEST options (1 bedroom, then 3 bedrooms), each marked fill=True. -> (picks, n_true)"""
    def ranked(sel):
        out = []
        for h in sel:
            if h.get("pending") or (h.get("nyc") or {}).get("fractional") or not h.get("price") or re.search(r"\b(bsmt|basement)\b", str(h.get("address") or ""), re.I):
                continue
            hm = money(h)
            if not hm:
                continue
            hi = hm.get("hoa") or {}
            s, pts = score(h, hm, hud(h.get("zip"), h.get("beds")), ap, hi)
            out.append({"h": h, "hm": hm, "score": s, "pts": pts})
        out.sort(key=lambda x: (-x["score"], x["h"].get("price") or 0, str(x["h"].get("id"))))
        picked, per = [], {}
        for x in out:
            b = building(x["h"].get("address"))
            if per.get(b, 0) >= PER_BUILDING:
                continue
            per[b] = per.get(b, 0) + 1
            picked.append(x)
        return picked
    true = ranked([h for h in rows if h.get("beds") == beds])[:n]
    picks = [dict(x, fill=False) for x in true]
    n_true = len(picks)
    if n_true < n:
        near = [b for b in ((beds - 1), (beds + 1)) if b >= 0]
        for b in near:
            for x in ranked([h for h in rows if h.get("beds") == b]):
                if len(picks) >= n:
                    break
                picks.append(dict(x, fill=True))
    for i, x in enumerate(picks, 1):
        x["rank"] = i
    return picks, n_true


def filter_rows(rows, area="all", beds=None, kind="any"):
    """beds: None = any, 0 = studio, 1, 2 = exactly that many, 3 = 3 or more. kind: any | condo (not co-op, not timeshare) | coop."""
    out = []
    for r in rows:
        if area != "all" and r.get("area") != area:
            continue
        b = r.get("beds")
        if beds is not None and not ((b or 0) >= 3 if beds == 3 else b == beds):
            continue
        if kind == "condo" and (r.get("type") in ("coop", "condop") or (r.get("nyc") or {}).get("fractional")):
            continue
        if kind == "coop" and r.get("type") not in ("coop", "condop"):
            continue
        out.append(r)
    return out


def by_id(d):
    """{listing id: row} of a loaded snapshot (memoized on the dict)."""
    if not d:
        return {}
    m = d.setdefault("_by_id", {r["id"]: r for r in d.get("rows") or []})
    return m


def ny_towns(d):
    """Lower-case town names of the New York State rows (+ the usual names): for-rent lists and rent lookups in this app are New Jersey only."""
    if not d:
        return set()
    s = d.setdefault("_ny_towns", {str(r.get("town") or "").lower() for r in d.get("rows") or [] if r.get("state") == "NY"} | {"new york", "manhattan", "new york city", "the bronx", "bronx", "brooklyn", "queens", "staten island"})
    return s


def seed_details(d, cache_path, max_age_s=5 * 86400):
    """Put the shortlisted homes' detail records (real fees, taxes, text, photos) into the app's detail cache so cards and the home view see them with no API call.
    A record already there and newer than max_age_s (e.g. a fresh API one) is left alone. Returns how many were written."""
    import time, datetime as dt
    try:
        if (dt.date.today() - dt.date.fromisoformat(str(d.get("built")))).days > 21:
            return 0                     # an old snapshot is not put back into the cache: opening a home then fetches fresh details
    except Exception:
        return 0
    n = 0
    for pid, det in ((d or {}).get("details") or {}).items():
        p = pathlib.Path(cache_path(f"detail_{pid}"))
        try:
            if p.exists() and time.time() - p.stat().st_mtime < max_age_s:
                continue
            p.write_text(json.dumps(det))
            n += 1
        except Exception:
            continue
    return n


def _m(v):
    return f"${float(v):,.0f}"


def reason(h, hm, ap, hud_rent, tag):
    """One line (en, es) for a pick: rent-out friendliness, monthly total vs the benchmark, resale/rental demand."""
    hi = hm.get("hoa") or {}
    t = hm["m"]["total"]
    _lv, r_en, r_es = rent_short(h, hi)
    fee_known = hi.get("state") == "real"
    if tag == "ok":
        m_en = f"{_m(t)}/mo, {_m(ap - t)} under the {_m(ap)} benchmark (fee and taxes confirmed)"
        m_es = f"{_m(t)}/mes, {_m(ap - t)} bajo el referente de {_m(ap)} (cuota e impuestos confirmados)"
    elif tag == "monthly":
        m_en = f"{_m(t)}/mo is {_m(t - ap)} OVER the {_m(ap)} benchmark"
        m_es = f"{_m(t)}/mes está {_m(t - ap)} POR ENCIMA del referente de {_m(ap)}"
    else:
        why_en = "fee not listed" if not fee_known else "taxes not listed (the lender's $4,000/yr is used)"
        why_es = "la cuota no está publicada" if not fee_known else "los impuestos no están publicados (se usan los $4,000/año del banco)"
        m_en = f"{_m(t)}/mo is only a rough figure ({why_en}), so NOT confirmed against the {_m(ap)} benchmark"
        m_es = f"{_m(t)}/mes es solo una cifra aproximada ({why_es}), así que NO está confirmado contra el referente de {_m(ap)}"
    d_en = d_es = ""
    if hud_rent:
        pc = round(100 * hud_rent / max(t, 1))
        d_en = f"HUD fair rent for {h.get('beds')} bd here is {_m(hud_rent)}/mo ({pc}% of the monthly cost), {h.get('mi', 0):.1f} mi from Times Square"
        d_es = f"La renta justa de HUD para {h.get('beds')} hab aquí es {_m(hud_rent)}/mes ({pc}% del costo mensual), a {h.get('mi', 0):.1f} mi de Times Square"
    if (h.get("nyc") or {}).get("tenant"):
        r_en += " (listing says a tenant is in place)"
        r_es += " (el anuncio dice que ya hay inquilino)"
    return f"{r_en}. {m_en}. {d_en}".strip(". ") + ".", f"{r_es}. {m_es}. {d_es}".strip(". ") + "."
