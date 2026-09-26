"""BellaZu core: analyze_property() and scan_arbitrage(). Return JSON-serializable dicts.
No browser, no GUI. Every number carries a source or is labeled as an assumption."""
import datetime as dt
import math
import numpy as np
import pandas as pd

from . import http
from .config import load_assumptions, load_env, by_beds
from .geo import geocode, haversine_km
from .finance import loan_costs, carrying_costs, str_operating, mtr_operating
from . import towns
from . import compare as cmpmod
from .sources import insideairbnb as iab, hud, census, fred, craigslist, rentcom, redfin, rentcast, listing, fha, str_rules
from .sources import airbnb_manual, bnbcalc

STR_RULES_URL_HINT = "data/str_rules.json"


def _clean(o):
    """Make numpy/pandas values JSON-safe."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if (o is None or math.isnan(o)) else float(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    return o


def _trim(s, pct):
    s = pd.Series(s).dropna()
    if len(s) >= 8 and pct:
        lo, hi = s.quantile(pct), s.quantile(1 - pct)
        s = s[(s >= lo) & (s <= hi)]
    return s


def _rates(A):
    f = A["financing"]
    base = f["base_rate_30yr"]
    src = "assumptions.yaml"
    if base == "auto":
        r = fred.mortgage30()
        if r:
            base, src = r["rate_pct"], f"{r['source']} week of {r['date']}"
        else:
            base, src = 7.0, "FALLBACK 7.0% (FRED unreachable) — edit assumptions.yaml"
    return {"base": base, "source": src,
            "fha": base + f["fha_rate_adjust"], "owner_conv": base + f["owner_conv_rate_adjust"],
            "investment": base + f["investment_rate_adjust"]}


# ------------------------------------------------------------------ rent comps
def _ltr_rows(town, state, zipcode, lat, lon, beds_range=(0, 4), include_rentcast=False):
    rows, used = [], []
    cl = craigslist.search(town, state, "apa", beds_range[0], beds_range[1], postal=zipcode, radius_mi=3 if zipcode else None)
    used.append({"source": "Craigslist", "ok": cl["ok"], "url": cl["url"], "n": len(cl["rows"])})
    rows += cl["rows"]
    rc = rentcom.search(town, state, pages=2)
    used.append({"source": "Rent.com", "ok": rc["ok"], "url": rc["url"], "n": len(rc["rows"])})
    rows += rc["rows"]
    rf = redfin.rentals(town, state.upper())
    used.append({"source": "Redfin", "ok": rf["ok"], "url": rf.get("url"), "n": len(rf["rows"]), "note": rf.get("note", "")})
    rows += rf["rows"]
    if include_rentcast and rentcast.available():
        d, s = rentcast.rental_listings(town, state)
        rows += d
        used.append({"source": "RentCast", "ok": bool(d), "n": len(d), "note": s})
    df = pd.DataFrame(rows)
    if df.empty:
        return df, used
    df = df[pd.to_numeric(df.price, errors="coerce").between(700, 20000)]
    df = _dedupe(df)
    df = _drop_other_town(df, town)
    df["dist_km"] = [haversine_km(lat, lon, a, b) if pd.notna(a) and pd.notna(b) else np.nan for a, b in zip(df.lat, df.lon)]
    return df, used


def _dedupe(df):
    df = df.drop_duplicates(subset=["title", "price", "beds"])
    key = df.price.astype(str) + "|" + df.beds.astype(str) + "|" + df.lat.round(3).astype(str) + "|" + df.lon.round(3).astype(str)
    return df[~key.duplicated()]


def _drop_other_town(df, town):
    """Craigslist pins many posts at the searched town's centroid even when the poster wrote another
    town (e.g. 'East Rutherford'). Drop Craigslist rows whose poster-written location names a different place."""
    if df.empty or not town:
        return df
    t = town.lower()
    loc = df.get("locality").fillna("").str.lower()
    bad = (df.source == "Craigslist") & (loc != "") & (~loc.str.contains(t, regex=False))
    return df[~bad]


def rent_estimate(df, beds, A, lat, lon):
    c = A["comps"]
    if df is None or df.empty:
        return {"ok": False, "n": 0}
    for r in c["ltr_radius_km"]:
        sub = df[(df.beds == beds) & (df.dist_km <= r)]
        if len(sub) >= c["ltr_min_comps"]:
            break
    s = _trim(sub.price, c["outlier_trim_pct"])
    if s.empty:
        return {"ok": False, "n": 0}
    return {"ok": True, "n": int(len(sub)), "radius_km": r, "median": float(s.median()),
            "p25": float(s.quantile(.25)), "p75": float(s.quantile(.75)),
            "comps": sub.sort_values("dist_km").head(15)}


def room_estimate(town, state, zipcode, lat, lon, A):
    cl = craigslist.search(town, state, "roo", postal=zipcode, radius_mi=3 if zipcode else None)
    df = pd.DataFrame(cl["rows"])
    if df.empty:
        return {"ok": False, "n": 0, "url": cl["url"]}
    df = df[pd.to_numeric(df.price, errors="coerce").between(400, 4000)].drop_duplicates(subset=["title", "price"])
    same = _drop_other_town(df, town)
    note = "rooms posted in this town"
    if len(same) >= 5:
        df = same
    else:
        note = f"only {len(same)} room posts name {town}; widened to all posts in the Craigslist search radius (poster-stated towns vary)"
    df["dist_km"] = [haversine_km(lat, lon, a, b) if pd.notna(a) else np.nan for a, b in zip(df.lat, df.lon)]
    df = df[df.dist_km <= 5]
    s = _trim(df.price, A["comps"]["outlier_trim_pct"])
    if s.empty:
        return {"ok": False, "n": 0, "url": cl["url"]}
    return {"ok": True, "n": int(len(df)), "median": float(s.median()), "p25": float(s.quantile(.25)),
            "p75": float(s.quantile(.75)), "url": cl["url"], "note": note, "comps": df.sort_values("dist_km").head(10)}


def reconcile_rent(free, rc, safmr, beds, A, gap_flag=0.20):
    """Compare the free-source comp median with RentCast's AVM. Prefer the estimate built on MORE comps;
    flag gaps > 20%. Falls back to HUD SAFMR when neither exists."""
    f_ok, r_ok = bool(free.get("ok")), bool(rc and rc.get("ok"))
    cmp = {"free_ok": f_ok, "free_median": free.get("median"), "free_n": free.get("n", 0),
           "rentcast_ok": r_ok, "rentcast_rent": (rc or {}).get("rent"), "rentcast_low": (rc or {}).get("low"),
           "rentcast_high": (rc or {}).get("high"), "rentcast_n": (rc or {}).get("n", 0), "rentcast_status": (rc or {}).get("status"),
           "gap_pct": None, "big_gap": False, "chosen": None}
    if f_ok and r_ok:
        cmp["gap_pct"] = round((rc["rent"] - free["median"]) / free["median"], 3)
        cmp["big_gap"] = abs(cmp["gap_pct"]) > gap_flag
        use_rc = rc["n"] > free["n"]
        cmp["chosen"] = "rentcast" if use_rc else "free"
        if cmp["big_gap"]:
            cmp["note_en"] = (f"Rent estimates disagree by {abs(cmp['gap_pct']):.0%}: free-source comps ${free['median']:,.0f} (n={free['n']}) vs RentCast ${rc['rent']:,.0f} (n={rc['n']}). "
                              f"Using the one with more comps ({'RentCast' if use_rc else 'free comps'}); verify with a local agent.")
            cmp["note_es"] = (f"Los estimados de renta difieren {abs(cmp['gap_pct']):.0%}: comparables gratuitos ${free['median']:,.0f} (n={free['n']}) vs RentCast ${rc['rent']:,.0f} (n={rc['n']}). "
                              f"Se usa el que tiene más comparables ({'RentCast' if use_rc else 'comparables gratuitos'}); verifique con un agente local.")
        if use_rc:
            return float(rc["rent"]), f"RentCast rent AVM ({rc['n']} comps; more than the {free['n']} free-source comps)", cmp
        return float(free["median"]), f"median asking rent of {free['n']} nearby same-bedroom listings (more comps than RentCast's {rc['n']})", cmp
    if f_ok:
        cmp["chosen"] = "free"
        return float(free["median"]), "median asking rent of nearby same-bedroom listings", cmp
    if r_ok:
        cmp["chosen"] = "rentcast"
        return float(rc["rent"]), f"RentCast rent AVM ({rc['n']} comps; no free-source comps found)", cmp
    v = (safmr or {}).get(f"{min(beds, 4)}br")
    cmp["chosen"] = "hud_safmr" if v else None
    return v, "HUD SAFMR (no listing comps found)", cmp


def mtr_rate(raw_monthly, ltr_rent, A, n=None):
    """Mid-term monthly rate = IAB 28+ night listed nightly x 30.4 x (1 - monthly discount), capped at
    ltr_rent x premium cap. Both factors are ASSUMPTIONS in assumptions.yaml (mtr section)."""
    t = A["mtr"]
    if not raw_monthly:
        return None, "no 28+ night comps"
    disc = raw_monthly * (1 - t.get("monthly_discount_on_listed_nightly", 0.2))
    if ltr_rent:
        cap = ltr_rent * t.get("max_premium_over_ltr", 1.5)
        if disc > cap:
            return cap, f"capped at {t.get('max_premium_over_ltr', 1.5)}x long-term rent (${cap:,.0f}); raw Inside Airbnb 28+night proxy was ${disc:,.0f}/mo after discount"
    return disc, f"Inside Airbnb 28+ night listings{'' if n is None else f' (n={n})'}: listed nightly x 30.4 less {t.get('monthly_discount_on_listed_nightly', 0.2):.0%} monthly discount"



STR_COLS = ["name", "neighbourhood_cleansed", "bedrooms", "price_num", "estimated_occupancy_l365d", "estimated_revenue_l365d", "number_of_reviews_ltm",
            "minimum_nights", "dist_km", "license", "listing_url", "picture_url", "dataset"]


def _recs(df, n, cols=STR_COLS):
    if df is None or not len(df):
        return []
    return df.head(n)[[c for c in cols if c in df.columns]].to_dict("records")


def _iab_pack(res, n=10):
    res = dict(res or {})
    df = res.pop("comps", None)
    res["comps"] = _recs(df, n)
    return res


def _extra_comps(lat, lon, town, state, zipcode, own, beds, ltr_df, safmr, A, units_total=None, units_for=(1, 2, 3)):
    """Comps the compare view needs beyond the whole-home ones. All Inside Airbnb work is local pandas (no network)."""
    rad, mn, rv = tuple(A["comps"]["str_radius_km"]), A["comps"]["str_min_comps"], A["comps"]["str_active_min_reviews_ltm"]
    out = {"room_str": _iab_pack(iab.comps(lat, lon, None, room_type="Private room", radii=rad, min_n=mn, min_reviews_ltm=rv, state=state)),
           "room_mtr": _iab_pack(iab.mtr_comps(lat, lon, None, state=state, room_type="Private room"), 8)}
    whole = iab.mtr_comps(lat, lon, beds, state=state)
    out["mtr_levels"] = {k: whole.get(k) for k in ("monthly_equiv_p25", "monthly_equiv_median", "monthly_equiv_p75", "n")}
    if own == "multi-family":
        out["units_total"] = int(units_total or 2)
        units = {}
        for b in units_for:
            e = rent_estimate(ltr_df, b, A, lat, lon)
            units[b] = {"ltr": {k: v for k, v in e.items() if k != "comps"}, "ltr_comps": e["comps"].head(8).to_dict("records") if e.get("ok") else [],
                        "hud": (safmr or {}).get(f"{b}br"),
                        "str": _iab_pack(iab.comps(lat, lon, b, radii=rad, min_n=mn, min_reviews_ltm=rv, state=state)),
                        "mtr": _iab_pack(iab.mtr_comps(lat, lon, b, state=state), 8)}
        out["units"] = units
    try:
        out["drive"] = cmpmod.drive(lat, lon, town)
    except Exception:
        out["drive"] = None
    return out

# ------------------------------------------------------------------ A) property analysis
def analyze_property(address, options=None):
    o = options or {}
    load_env()
    http.STATUS.clear()
    A = load_assumptions(o.get("assumptions_path"), o.get("assumption_overrides"))
    warnings = []
    g = geocode(address)
    use_rc = bool(o.get("use_rentcast", True)) and rentcast.available()
    facts, fsrc, rc_facts_meta = listing.get_facts(address, o.get("listing_url"), o.get("overrides"), use_rentcast=use_rc)
    lat = float(facts.get("lat") or (g or {}).get("lat") or 0)
    lon = float(facts.get("lon") or (g or {}).get("lon") or 0)
    if not lat:
        return {"ok": False, "error": "Could not geocode address", "sources_status": list(http.STATUS)}
    town = o.get("town") or (g or {}).get("town") or ""
    zipcode = o.get("zip") or (g or {}).get("zip") or ""
    state = o.get("state", "nj")
    beds = int(facts["beds"]) if facts.get("beds") not in (None, "") else int(o.get("beds") or 2)   # 0 = studio
    price = float(facts.get("price") or 0)
    own = (facts.get("ownership") or "").lower()
    missing = [k for k in ("price", "beds", "hoa_monthly") if facts.get(k) in (None, "") and not (k == "hoa_monthly" and own in ("single-family", "multi-family"))]
    if missing:
        warnings.append("Missing listing facts: " + ", ".join(missing) + " — pass overrides or a listing_url.")
    rules = str_rules.rules_for(town)
    rates = _rates(A)

    # --- benchmarks
    safmr = hud.safmr(zipcode)
    acs = census.median_rent_by_beds(zipcode)
    # --- LTR comps
    ltr_df, ltr_used = _ltr_rows(town, state, zipcode, lat, lon, include_rentcast=bool(o.get("rentcast_rental_listings")) and use_rc)
    rent = rent_estimate(ltr_df, beds, A, lat, lon)
    rc_avm = rentcast.rent_estimate(address, beds, facts.get("baths"), facts.get("sqft"), own) if use_rc else None
    room = room_estimate(town, state, zipcode, lat, lon, A)
    rent_mid, rent_basis, rent_cmp = reconcile_rent(rent, rc_avm, safmr, beds, A)
    if rent_cmp.get("big_gap"):
        warnings.append(rent_cmp["note_en"])
    # --- STR comps
    strc = iab.comps(lat, lon, beds, radii=tuple(A["comps"]["str_radius_km"]), min_n=A["comps"]["str_min_comps"],
                     min_reviews_ltm=A["comps"]["str_active_min_reviews_ltm"], state=state)
    str_comps_df = strc.pop("comps", None) if strc.get("ok") else None
    comp_juris = sorted(set(str_comps_df.dataset.str.split("/").str[1])) if str_comps_df is not None and len(str_comps_df) else []
    if strc.get("ok") and town and not any(town.lower().replace(" ", "-") in j for j in comp_juris):
        warnings.append(f"No Inside Airbnb dataset covers {town}. STR comps are a PROXY from {', '.join(comp_juris)} "
                        f"(comps up to {strc['radius_km']:.1f} km away) — different market and different STR law; use only as a rough reference.")
    mtr = iab.mtr_comps(lat, lon, beds, state=state)
    mtr_df = mtr.pop("comps", None)
    # --- extra comps for the compare view: a furnished ROOM you host, and (2-4 family) the OTHER unit by size
    extra = _extra_comps(lat, lon, town, state, zipcode, own, beds, ltr_df, safmr, A, o.get("units_total"))
    manual = airbnb_manual.parse_saved_search(o["airbnb_saved_html"]) if o.get("airbnb_saved_html") else None
    bnb = bnbcalc.parse_analysis(o["bnbcalc_url"]) if o.get("bnbcalc_url") else None

    # --- FHA eligibility
    fha_info = {"eligible": None, "note": ""}
    if "co-op" in own or "coop" in own or "cooperative" in own:
        fha_info = {"eligible": False, "note_en": "Co-op: FHA generally does NOT insure co-op share loans (Section 203(n) exists but almost no lenders offer it). Expect a conventional co-op share loan (often 10-25% down) plus co-op BOARD approval; many co-ops restrict subletting and roommates/boarders.",
                    "note_es": "Cooperativa (co-op): FHA generalmente NO asegura préstamos de acciones de co-op (existe la Sección 203(n) pero casi ningún prestamista la ofrece). Espere un préstamo convencional de co-op (a menudo 10-25% de enganche) y aprobación de la JUNTA; muchas co-ops limitan subarriendos y compañeros de cuarto."}
    elif "condo" in own:
        lk = fha.lookup_zip(zipcode) if zipcode else None
        street = address.split(",")[0]
        hits = fha.match_building((lk or {}).get("rows"), street) if lk else []
        fha_info = {"eligible": bool(hits and any("Approved" in h["raw"] for h in hits)), "matches": hits,
                    "zip_list_count": len((lk or {}).get("rows", [])), "source": fha.SEARCH,
                    "note_en": "Condo must be on HUD's FHA-approved list, or obtain a Single-Unit Approval (possible if the building meets HUD rules).",
                    "note_es": "El condominio debe estar en la lista aprobada por FHA de HUD, o conseguir una Aprobación de Unidad Individual."}

    # --- scenarios
    scen = []
    cc_owner, cnotes = carrying_costs(facts, A, "owner")
    warnings += cnotes
    rooms = max(beds - 1, 0) if A["roommate"]["rooms_rented_out"] == "auto" else min(int(A["roommate"]["rooms_rented_out"]), max(beds - 1, 0))   # never more roommates than spare bedrooms
    room_rent = room["median"] if room.get("ok") else (rent_mid or 0) * A["roommate"]["room_rent_fallback_share"]
    room_basis = "median Craigslist room-share asking rent nearby" if room.get("ok") else f"ASSUMPTION {A['roommate']['room_rent_fallback_share']:.0%} of unit rent per room"
    income_annual = float(o.get("income_annual") or 0) or None
    income_m = income_annual / 12 if income_annual else None
    if price:
        is_coop = fha_info.get("eligible") is False and "co-op" in own
        if is_coop:
            lc = loan_costs(price, A["financing"]["owner_conv_down_pct"], rates["owner_conv"], A["financing"]["term_years"], A=A)
            label = "Owner-occupied (co-op share loan, FHA not available) + roommates"
            label_es = "Vivienda propia (préstamo de co-op, sin FHA) + compañeros de cuarto"
        else:
            lc = loan_costs(price, A["financing"]["fha_down_pct"], rates["fha"], A["financing"]["term_years"], fha=True, A=A)
            label = "FHA owner-occupied + roommates"
            label_es = "FHA vivienda propia + compañeros de cuarto"
        costs = {"principal_interest": lc["principal_interest"], "mortgage_insurance": lc["mortgage_insurance"], **cc_owner}
        total = sum(costs.values())
        piti_hoa = total - cc_owner["utilities"] - cc_owner["repairs_reserve"]
        scen.append({"key": "owner_roommates", "label_en": label, "label_es": label_es, "legal": True,
                     "loan": lc, "costs": costs, "total_cost": total,
                     "income": {"roommate_rent": round(rooms * room_rent)}, "rooms_rented": rooms,
                     "room_rent_each": round(room_rent), "room_rent_basis": room_basis,
                     "net_monthly": round(rooms * room_rent - total), "own_net_housing_cost": round(total - rooms * room_rent),
                     "front_end_dti": round(piti_hoa / income_m, 3) if income_m else None,
                     "caveat_en": ("Co-op boards often restrict roommates/boarders — confirm in the house rules before counting roommate income." if "co-op" in own else "Confirm condo bylaws allow roommates/boarders."),
                     "caveat_es": ("Las juntas de co-op a menudo restringen compañeros de cuarto — confírmelo en las reglas antes de contar ese ingreso." if "co-op" in own else "Confirme que los estatutos del condominio permitan compañeros de cuarto."),
                     "dti_note_en": "Lenders usually do NOT count roommate income for qualifying. FHA guideline front-end ~31% (AUS can approve higher).",
                     "dti_note_es": "Los prestamistas normalmente NO cuentan el ingreso de compañeros de cuarto para calificar. Guía FHA ~31% (el sistema automatizado puede aprobar más)."})
        # conventional investment LTR
        lc2 = loan_costs(price, A["financing"]["investment_down_pct"], rates["investment"], A["financing"]["term_years"], A=A)
        cc_inv, _ = carrying_costs(facts, A, "landlord")
        eff_rent = (rent_mid or 0) * (1 - A["ownership_costs"]["vacancy_pct_ltr"] - A["ownership_costs"]["mgmt_pct_ltr"])
        costs2 = {"principal_interest": lc2["principal_interest"], "mortgage_insurance": lc2["mortgage_insurance"], **cc_inv}
        if "utilities" not in [x.lower() for x in facts.get("hoa_includes") or []]:
            costs2["utilities"] = 0  # tenant pays
        t2 = sum(costs2.values())
        noi = eff_rent * 12 - (t2 - lc2["principal_interest"] - lc2["mortgage_insurance"]) * 12
        scen.append({"key": "investment_ltr", "label_en": "Conventional investment loan, rent whole unit long-term",
                     "label_es": "Préstamo de inversión convencional, alquiler a largo plazo de la unidad completa",
                     "legal": True, "caveat_en": ("Most co-ops do not allow investor purchases or open-ended subletting — check the proprietary lease/house rules." if "co-op" in own else "Check condo bylaws for rental caps/minimum lease terms."),
                     "caveat_es": ("La mayoría de las co-ops no permiten compras por inversionistas ni subarriendo indefinido — revise el contrato de arrendamiento propietario/reglas." if "co-op" in own else "Revise los estatutos del condominio sobre límites de alquiler/plazos mínimos."),
                     "loan": lc2, "costs": costs2, "total_cost": round(t2), "income": {"rent_after_vacancy": round(eff_rent)},
                     "rent_basis": rent_basis, "net_monthly": round(eff_rent - t2),
                     "cap_rate": round(noi / price, 4) if price else None,
                     "cash_on_cash": round((eff_rent - t2) * 12 / lc2["cash_to_close_est"], 4)})
        # STR
        s = strc.get("summary", {}) if strc.get("ok") else {}
        legal_owner = rules.get("str_legal_for_owner")
        if s.get("n") and legal_owner:
            occ = min(s["occ_median_sf_model"] or 0, A["str"]["occupancy_cap"])
            nights = occ * 365
            if rules.get("status") == "owner_occupied_permit_only":
                nights = min(nights, 60)
                cap_note = "Whole-unit unhosted stays capped at 60 nights/yr (owner-occupied permit town)."
            else:
                cap_note = ""
            revenue = nights * s["adr_median"]
            op = str_operating(revenue, nights, beds, A, utilities_included="utilities" in [x.lower() for x in facts.get("hoa_includes") or []])
            costs3 = {"principal_interest": lc["principal_interest"], "mortgage_insurance": lc["mortgage_insurance"], **cc_owner, **op}
            t3 = sum(costs3.values())
            scen.append({"key": "str", "label_en": "Short-term rental (owner permit rules applied)", "label_es": "Alquiler a corto plazo (reglas de permiso aplicadas)",
                         "legal": True, "caveat_en": cap_note + " Condo/co-op bylaws must also allow STR.",
                         "caveat_es": "Los estatutos del condominio/co-op también deben permitir STR.",
                         "revenue_annual": round(revenue), "booked_nights": round(nights), "adr": round(s["adr_median"]),
                         "costs": costs3, "total_cost": round(t3), "net_monthly": round(revenue / 12 - t3)})
        else:
            scen.append({"key": "str", "label_en": "Short-term rental", "label_es": "Alquiler a corto plazo", "legal": False,
                         "skipped_reason_en": f"Not computed: STR is not legal here for this property ({rules.get('status')}). {rules.get('summary_en','')}",
                         "skipped_reason_es": f"No calculado: el STR no es legal aquí para esta propiedad. {rules.get('summary_es','')}"})
        # MTR (legal alternative)
        mrate, mbasis = mtr_rate(mtr.get("monthly_equiv_median") if mtr.get("ok") else None, rent_mid, A)
        if mrate:
            gross, opm = mtr_operating(mrate, beds, A)
            util_inc = "utilities" in [x.lower() for x in facts.get("hoa_includes") or []]
            if util_inc:
                opm["utilities"] = 0
            costs4 = {"principal_interest": lc2["principal_interest"], "mortgage_insurance": lc2["mortgage_insurance"], **cc_inv, **opm}
            t4 = sum(costs4.values())
            scen.append({"key": "mtr", "label_en": "Mid-term furnished rental (30+ nights) on investment loan",
                         "label_es": "Alquiler amueblado de mediano plazo (30+ noches) con préstamo de inversión",
                         "legal": True, "caveat_en": f"Monthly rate: {mbasis}. Occupancy {A['mtr']['occupancy']:.0%} is an ASSUMPTION.",
                         "caveat_es": f"Tarifa mensual: {mbasis}. La ocupación de {A['mtr']['occupancy']:.0%} es un SUPUESTO.", "mtr_rate": round(mrate),
                         "revenue_monthly": gross, "costs": costs4, "total_cost": round(t4), "net_monthly": round(gross - t4)})

    bp = o.get("building_policy") or {}
    income_check = None
    if bp.get("income_multiple") and scen:
        o1 = scen[0]
        maint = float(facts.get("hoa_monthly") or 0)
        income_check = {"multiple": bp["income_multiple"],
                        "required_income_maintenance_only": round(maint * 12 * bp["income_multiple"]),
                        "required_income_with_mortgage": round((maint + o1["costs"]["principal_interest"] + o1["costs"]["mortgage_insurance"]) * 12 * bp["income_multiple"]),
                        "buyer_income": income_annual}
        warnings.insert(0, f"Building income rule {bp['income_multiple']}:1 -> needs about ${income_check['required_income_maintenance_only']:,.0f}/yr on maintenance alone "
                           f"(${income_check['required_income_with_mortgage']:,.0f} incl. mortgage)" + (f" vs the income entered (${income_annual:,.0f})." if income_annual else "."))
    out = {
        "ok": True, "kind": "property", "coop_income_check": income_check, "brand": "BellaZu", "generated": dt.datetime.now().isoformat(timespec="minutes"),
        "address": address, "geo": g, "town": town, "zip": zipcode, "lat": lat, "lon": lon,
        "facts": facts, "fact_sources": fsrc, "building_policy": o.get("building_policy"),
        "str_rules": rules, "rates": rates, "fha": fha_info,
        "benchmarks": {"hud_safmr": safmr, "acs_median_gross_rent": acs, "rentcast_avm": ({k: v for k, v in rc_avm.items() if k != "comps"} if rc_avm else None)},
        "rent_compare": rent_cmp, "rentcast": {"enabled": use_rc, "facts": rc_facts_meta, "avm_status": (rc_avm or {}).get("status"), "avm_comps": (rc_avm or {}).get("comps", [])[:15], "usage": rentcast.usage()},
        "income_annual": income_annual,
        "ltr": {"sources_used": ltr_used, "estimate": {k: v for k, v in rent.items() if k != "comps"},
                "basis": rent_basis, "comps": rent.get("comps").to_dict("records") if rent.get("ok") else []},
        "rooms": {k: v for k, v in room.items() if k != "comps"} | {"comps": room["comps"].to_dict("records") if room.get("ok") else []},
        "str": {**strc, "method": iab.__doc__.strip(),
                "comps": _recs(str_comps_df, 20)},
        "mtr": {**mtr, "comps": _recs(mtr_df, 10)},
        "airbnb_manual": manual, "bnbcalc": bnb, "extra": extra,
        "scenarios": scen, "assumptions": A, "warnings": warnings,
        "sources_status": list(http.STATUS),
    }
    return _clean(out)


# ------------------------------------------------------------------ B) arbitrage scan
def scan_arbitrage(town, options=None):
    o = options or {}
    load_env()
    http.STATUS.clear()
    A = load_assumptions(o.get("assumptions_path"), o.get("assumption_overrides"))
    tn = towns.normalize(town)            # forgiving: case, ', NJ', 'Ft Lee', 'WNY', small typos
    state = tn["state"] if tn["match"] != "none" or "state" not in o else o["state"]
    tname = tn["name"] or (town or "").split(",")[0].strip()
    base = {"town_input": tn["typed"], "town_match": tn["match"], "town_suggestions": tn["suggestions"]}
    if not tname:
        return {"ok": False, "error": "no town given", "error_kind": "unknown_town", **base, "sources_status": list(http.STATUS)}
    g = geocode(f"{tname}, {state.upper()}")
    if not g or (tn["match"] == "none" and g.get("osm_type") not in ("city", "town", "village", "municipality", "hamlet", "suburb", "borough", "county")):
        return {"ok": False, "error": "could not find that town", "error_kind": "unknown_town", **base, "sources_status": list(http.STATUS)}
    rules = str_rules.rules_for(tname)
    beds_ok = A["arbitrage"]["beds"]
    rows, used = [], []
    rc = rentcom.search(tname, state, pages=A["arbitrage"]["max_pages_rentcom"])
    used.append({"source": "Rent.com", "ok": rc["ok"], "url": rc["url"], "n": len(rc["rows"])}); rows += rc["rows"]
    cl = craigslist.search(tname, state, "apa", min(beds_ok), max(beds_ok))
    used.append({"source": "Craigslist", "ok": cl["ok"], "url": cl["url"], "n": len(cl["rows"])}); rows += cl["rows"]
    rf = redfin.rentals(tname, state.upper())
    used.append({"source": "Redfin", "ok": rf["ok"], "url": rf.get("url"), "n": len(rf["rows"]), "note": rf.get("note", "")}); rows += rf["rows"]
    use_rc = bool(o.get("use_rentcast", True)) and rentcast.available()
    if use_rc:
        d, s = rentcast.rental_listings(tname, state)
        rows += d
        used.append({"source": "RentCast", "ok": bool(d), "n": len(d), "note": s})
    df = pd.DataFrame(rows)
    if df.empty:
        return _clean({"ok": False, "error": "no rental listings fetched", "error_kind": "no_listings", "town": tname, **base, "sources_used": used, "sources_status": list(http.STATUS)})
    df["price"] = pd.to_numeric(df.price, errors="coerce")
    df = df[df.price.between(900, 15000) & df.beds.isin(beds_ok) & df.lat.notna()]
    bb = g.get("bbox") or []
    if len(bb) == 4:  # [south, north, west, east] + ~0.5 km margin
        m = 0.005
        df = df[df.lat.between(bb[0] - m, bb[1] + m) & df.lon.between(bb[2] - m, bb[3] + m)]
    df = _drop_other_town(_dedupe(df), tname).head(A["arbitrage"]["max_listings"]).reset_index(drop=True)

    # STR universe (load once)
    ds = iab.nearby_datasets(g["lat"], g["lon"], state=state)
    frames = [iab.load(st, c, d) for _, st, c, d in ds]
    frames = [f for f in frames if f is not None]
    if not frames:
        return _clean({"ok": False, "error": "no Inside Airbnb data near " + town, "sources_status": list(http.STATUS)})
    U = pd.concat(frames, ignore_index=True)
    act = U[(U.room_type == "Entire home/apt") & U.price_num.notna() & (U.minimum_nights <= 29) &
            (U.number_of_reviews_ltm.fillna(0) >= A["comps"]["str_active_min_reviews_ltm"])].reset_index(drop=True)
    mtrU = U[(U.room_type == "Entire home/apt") & U.price_num.notna() & (U.minimum_nights >= 28)].reset_index(drop=True)
    covered_town = any(tname.lower().replace(" ", "-") in x for x in set(U.dataset))
    alat, alon = np.radians(act.latitude.values), np.radians(act.longitude.values)
    mlat, mlon = np.radians(mtrU.latitude.values), np.radians(mtrU.longitude.values)

    def dist(la, lo, LA, LO):
        la, lo = math.radians(la), math.radians(lo)
        a = np.sin((LA - la) / 2) ** 2 + np.cos(la) * np.cos(LA) * np.sin((LO - lo) / 2) ** 2
        return 2 * 6371 * np.arcsin(np.sqrt(a))

    bed_median = df.groupby("beds").price.median().to_dict()   # area long-term rent by bedrooms (for MTR cap + scam flag)
    out_rows = []
    for _, r in df.iterrows():
        d = dist(r.lat, r.lon, alat, alon)
        comps, used_r = None, None
        for rad in A["comps"]["str_radius_km"]:
            mask = (d <= rad) & (act.bedrooms.values == r.beds)
            if mask.sum() >= A["comps"]["str_min_comps"]:
                comps, used_r = act[mask], rad
                break
        if comps is None:   # PROXY: nearest 15 same-bedroom listings within 15 km
            mask = (d <= 15) & (act.bedrooms.values == r.beds)
            idx = np.where(mask)[0]
            idx = idx[np.argsort(d[idx])][:15]
            comps = act.iloc[idx]
            used_r = float(d[idx].max()) if len(idx) else None
        if len(comps) < 3:
            continue
        occ = min(float((comps.estimated_occupancy_l365d / 365).median()), A["str"]["occupancy_cap"])
        adr = float(comps.price_num.median())
        nights = occ * 365
        rev = adr * nights
        rev_p25 = float(comps.estimated_revenue_l365d.quantile(.25))
        rev_p75 = float(comps.estimated_revenue_l365d.quantile(.75))
        op = str_operating(rev, nights, int(r.beds), A)
        profit = rev / 12 - r.price - sum(op.values())
        # MTR
        dm = dist(r.lat, r.lon, mlat, mlon)
        mm = (dm <= (2.0 if covered_town else 15.0)) & (mtrU.bedrooms.values == r.beds)
        raw = float(mtrU[mm].price_num.median() * 30.4) if mm.sum() >= 3 else adr * 30.4 * A["mtr"]["mtr_discount_vs_str_nightly"]
        mrate, mbasis = mtr_rate(raw, float(bed_median.get(r.beds, r.price)), A, n=int(mm.sum()))
        suspicious = r.price < 0.6 * bed_median.get(r.beds, r.price)
        mg, mop = mtr_operating(mrate, int(r.beds), A)
        mprofit = mg - r.price - sum(mop.values())
        out_rows.append({
            "source": r.source, "title": r.title, "address": r.get("address"), "beds": int(r.beds), "rent": int(r.price),
            "sqft": r.get("sqft"), "url": r.url, "lat": r.lat, "lon": r.lon,
            "str_comps": int(len(comps)), "str_radius_km": round(used_r, 2) if used_r else None,
            "str_comp_basis": "local" if (used_r or 99) <= A["comps"]["str_radius_km"][-1] else "PROXY (nearest-k, farther away)", "adr_median": round(adr), "occ_sf_model": round(occ, 3),
            "str_revenue_annual": round(rev), "str_revenue_p25_p75": f"{rev_p25:,.0f}-{rev_p75:,.0f}",
            **{f"exp_{k}": v for k, v in op.items()},
            "str_profit_monthly": round(profit), "mtr_monthly_rate": round(mrate), "mtr_basis": mbasis,
            "mtr_profit_monthly": round(mprofit),
            "str_legal_tenant": bool(rules.get("str_legal_for_tenant")),
            "check_flag": "rent <60% of area median for this size: verify (possible scam/room/typo)" if suspicious else "",
            "legality_flag": ("LEGAL?" if rules.get("str_legal_for_tenant") else "NOT LEGAL for tenant STR") + f" ({rules.get('status')})",
        })
    res = pd.DataFrame(out_rows)
    if not res.empty:
        sort_col = o.get("sort_by") or ("str_profit_monthly" if rules.get("str_legal_for_tenant") else "mtr_profit_monthly")
        res = res.sort_values(sort_col, ascending=False).reset_index(drop=True)
        res.insert(0, "rank", range(1, len(res) + 1))
    iab_juris = sorted(set(U.dataset))
    covered = covered_town
    out = {"ok": True, "kind": "arbitrage", "brand": "BellaZu", "generated": dt.datetime.now().isoformat(timespec="minutes"),
           "town": tname, "state": state, "geo": g, **base, "str_rules": rules, "sources_used": used,
           "iab_datasets": iab_juris, "iab_covers_town": covered, "sorted_by": (sort_col if not res.empty else None),
           "n_listings_fetched": int(len(rows)), "n_listings_scored": int(len(res)),
           "summary": {
               "median_rent": float(res.rent.median()) if len(res) else None,
               "median_str_profit": float(res.str_profit_monthly.median()) if len(res) else None,
               "share_str_profitable": float((res.str_profit_monthly > 0).mean()) if len(res) else None,
               "median_mtr_profit": float(res.mtr_profit_monthly.median()) if len(res) else None,
               "share_mtr_profitable": float((res.mtr_profit_monthly > 0).mean()) if len(res) else None,
               "by_beds": res.groupby("beds").agg(n=("rent", "size"), rent=("rent", "median"), str_rev=("str_revenue_annual", "median"),
                                                  str_profit=("str_profit_monthly", "median"), mtr_profit=("mtr_profit_monthly", "median")).reset_index().to_dict("records") if len(res) else []},
           "results": res.to_dict("records"), "assumptions": A,
           "caveats_en": ["Rental arbitrage always needs the landlord's WRITTEN permission (lease sublet clause) and building/HOA approval.",
                          "STR revenue = Inside Airbnb San-Francisco-model estimates for same-bedroom active listings nearby; real results vary widely (see P25-P75).",
                          "Listing rents are ASKING rents on the fetch date; Rent.com shows the lowest price per floor plan."],
           "caveats_es": ["El arbitraje de alquiler siempre requiere permiso ESCRITO del dueño (cláusula de subarriendo) y aprobación del edificio/HOA.",
                          "Los ingresos STR son estimaciones del modelo San Francisco de Inside Airbnb para anuncios activos cercanos con igual número de habitaciones; los resultados reales varían mucho (ver P25-P75).",
                          "Las rentas son rentas PEDIDAS en la fecha de consulta; Rent.com muestra el precio más bajo por plano."],
           "rentcast": {"enabled": use_rc, "usage": rentcast.usage()},
           "sources_status": list(http.STATUS)}
    return _clean(out)


# ------------------------------------------------------------------ C) town snapshot (same layout as a home)
def town_snapshot(town, options=None):
    """Everything the town view needs, from free sources. No typical home value is invented: the app asks the user to tap a price."""
    o = options or {}
    load_env()
    http.STATUS.clear()
    A = load_assumptions(o.get("assumptions_path"), o.get("assumption_overrides"))
    tn = towns.normalize(town)
    state = tn["state"] if tn["match"] != "none" else "nj"
    tname = tn["name"] or (town or "").split(",")[0].strip()
    base = {"town_input": tn["typed"], "town_match": tn["match"], "town_suggestions": tn["suggestions"]}
    if not tname:
        return {"ok": False, "error": "no town given", "error_kind": "unknown_town", **base}
    ti = cmpmod.town_info(tname)
    if ti:
        lat, lon, zipcode, g = ti["lat"], ti["lon"], ti.get("zip"), {"lat": ti["lat"], "lon": ti["lon"], "town": tname}
    else:
        g = geocode(f"{tname}, {state.upper()}")
        if not g or (tn["match"] == "none" and g.get("osm_type") not in ("city", "town", "village", "municipality", "hamlet", "suburb", "borough", "county")):
            return {"ok": False, "error": "could not find that town", "error_kind": "unknown_town", **base, "sources_status": list(http.STATUS)}
        lat, lon, zipcode = g["lat"], g["lon"], g.get("zip")
    rules = str_rules.rules_for(tname)
    rates = _rates(A)
    safmr = hud.safmr(zipcode) if zipcode else None
    use_rc = bool(o.get("use_rentcast", False)) and rentcast.available()
    ltr_df, used = _ltr_rows(tname, state, zipcode, lat, lon, include_rentcast=use_rc)
    if not ltr_df.empty:
        ltr_df = ltr_df[(ltr_df.dist_km <= 4) | ltr_df.dist_km.isna()]
    by_beds = {}
    for b in (0, 1, 2, 3):
        e = rent_estimate(ltr_df, b, A, lat, lon)
        by_beds[b] = {"ltr": {k: v for k, v in e.items() if k != "comps"}, "ltr_comps": e["comps"].head(10).to_dict("records") if e.get("ok") else [],
                      "hud": (safmr or {}).get(f"{b}br")}
    room = room_estimate(tname, state, zipcode, lat, lon, A)
    rad, mn, rv = tuple(A["comps"]["str_radius_km"]), A["comps"]["str_min_comps"], A["comps"]["str_active_min_reviews_ltm"]
    for b in (1, 2, 3):
        by_beds[b]["str"] = _iab_pack(iab.comps(lat, lon, b, radii=rad, min_n=mn, min_reviews_ltm=rv, state=state))
        by_beds[b]["mtr"] = _iab_pack(iab.mtr_comps(lat, lon, b, state=state), 8)
    room_str = _iab_pack(iab.comps(lat, lon, None, room_type="Private room", radii=rad, min_n=mn, min_reviews_ltm=rv, state=state))
    room_mtr = _iab_pack(iab.mtr_comps(lat, lon, None, state=state, room_type="Private room"), 8)
    # Airbnb market card: all active whole-home short stays around the town centre (3.5 km), or the nearest 40 if none
    mk = iab.comps(lat, lon, None, radii=(3.5,), min_n=15, min_reviews_ltm=rv, state=state, nearest_k=40)
    mdf = mk.get("comps")
    juris = sorted(set(mdf.dataset.str.split("/").str[1])) if mdf is not None and len(mdf) else []
    covered = any(tname.lower().replace(" ", "-") == j for j in juris)
    market = {"summary": mk.get("summary") or {}, "radius_km": mk.get("radius_km"), "datasets": juris, "covered": covered,
              "n_30plus": int(by_beds[2]["mtr"].get("n") or 0)}
    out = {"ok": True, "kind": "town", "brand": "BellaZu", "generated": dt.datetime.now().isoformat(timespec="minutes"),
           "town": tname, "state": state, "zip": zipcode, "lat": lat, "lon": lon, **base,
           "str_rules": rules, "rates": rates, "hud_safmr": safmr, "by_beds": by_beds,
           "rooms": {k: v for k, v in room.items() if k != "comps"} | {"comps": room["comps"].to_dict("records") if room.get("ok") else []},
           "room_str": room_str, "room_mtr": room_mtr, "market": market, "iab_covers_town": covered,
           "seasonality": cmpmod.seasonality(mk.get("datasets") or []), "drive": cmpmod.drive(town=tname, route=False) if ti else cmpmod.drive(lat, lon, tname),
           "sources_used": used, "assumptions": A, "rentcast": {"enabled": use_rc, "usage": rentcast.usage()},
           "sources_status": list(http.STATUS)}
    return _clean(out)
