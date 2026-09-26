"""One compare view for a home or a town: 'Buy & live' / '+ long-term tenant' / '+ Airbnb or 30+ day', all on the SAME
owner-occupied loan. Presentation math on analyze_property() / town_snapshot() output plus the town tables in data/.
Every number traces to an engine value, a table with a source, or an assumption in assumptions.yaml."""
import functools, json, math, pathlib
import requests
from .finance import pmt, str_operating, mtr_operating

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
MIDTOWN = (40.7580, -73.9855)
CROSS = [("Lincoln Tunnel", "Lincoln Tunnel"), ("George Washington Bridge", "GWB"), ("Holland Tunnel", "Holland Tunnel")]
TOLL_LINKS = ["https://www.panynj.gov/bridges-tunnels/en/tolls.html", "https://congestionreliefzone.mta.info/tolling"]


# ------------------------------------------------------------------ town tables
@functools.lru_cache(1)
def towns_meta():
    try:
        return json.loads((DATA / "towns_meta.json").read_text())
    except Exception:
        return {"_meta": {"first_home": [], "next_homes": []}, "towns": {}}


def town_key(name):
    n = (name or "").lower().replace("township", "").replace("city of", "").replace("town of", "").replace(", nj", "").strip()
    for k in towns_meta()["towns"]:
        if k.lower() == n:
            return k
    return None


def town_info(name):
    k = town_key(name)
    return dict(towns_meta()["towns"][k], name=k) if k else None


def town_caution(name):
    """(level, [en, es]) from the safety screen (NJSP UCR violent crime vs NJ average): 'exclude' (>= 1.5x), 'above' (1.0-1.5x), or (None, None)."""
    ti = town_info(name or "")
    if ti and ti.get("caution"):
        return (ti.get("safety") or {}).get("level"), ti["caution"]
    ox = ((towns_meta()["_meta"].get("safety") or {}).get("other_excluded") or {})
    for k, v in ox.items():
        if k.lower() == (name or "").strip().lower():
            return "exclude", v["caution"]
    return None, None


def town_tax_rate(name):
    ti = town_info(name or "")
    return (ti or {}).get("eff_tax")


def mode_towns(mode):
    m = towns_meta()["_meta"]
    return list(m.get("first_home" if mode == "first" else "next_homes") or [])


@functools.lru_cache(1)
def seasonality_table():
    try:
        return json.loads((DATA / "seasonality.json").read_text())
    except Exception:
        return {}


def seasonality(datasets):
    """Busy/slow months index for the Inside Airbnb city that the comps came from (JC or Newark)."""
    t = seasonality_table()
    ds = " ".join(datasets or [])
    for city in ("jersey-city", "newark"):
        if city in ds and city in t:
            return dict(t[city], city=city, method=t["_meta"]["method"], source=t["_meta"]["source"])
    return None


# ------------------------------------------------------------------ drive time
def rush_range(off):
    base = off * 1.683
    return [int(round((base + 5) / 5) * 5), int(round((base + 45) / 5) * 5)]


@functools.lru_cache(512)
def _osrm(lat3, lon3):
    try:
        u = f"https://router.project-osrm.org/route/v1/driving/{lon3},{lat3};{MIDTOWN[1]},{MIDTOWN[0]}?overview=false&steps=true"
        d = requests.get(u, timeout=6, headers={"User-Agent": "BellaZu/0.1 (personal, low volume)"}).json()
        r = d["routes"][0]
        names = " | ".join(str(s.get("name", "")) for l in r["legs"] for s in l["steps"])
        cross = next((short for full, short in CROSS if full in names), None)
        return round(r["duration"] / 60), round(r["distance"] / 1609.34, 1), cross
    except Exception:
        return None


def drive(lat=None, lon=None, town=None, route=True):
    """Typical drive to Midtown (Times Square). Off-peak from OSRM for this exact spot when reachable, else the town table."""
    t = town_info(town) if town else None
    r = _osrm(round(float(lat), 3), round(float(lon), 3)) if (route and lat and lon) else None
    if r:
        off, mi, cross = r
        src = "route"
    elif t:
        off, mi, cross, src = t["drive_offpeak_min"], t["drive_miles"], t["crossing"], "town"
    else:
        return None
    return {"min": off, "miles": mi, "rush": rush_range(off), "crossing": cross, "source": src,
            "transit": (t or {}).get("transit"), "town": (t or {}).get("name"), "tolls": TOLL_LINKS,
            "method": towns_meta()["_meta"].get("rush_method", "")}


def drive_text(d, es=False):
    if not d:
        return None
    via = f" · {'por' if es else 'via'} {d['crossing']}" if d.get("crossing") else ""
    lo, hi = d["rush"]
    if es:
        return f"🚗 Unos {d['min']} min a Midtown · {lo}-{hi} en hora pico{via}"
    return f"🚗 About {d['min']} min to Midtown · {lo}-{hi} at rush hour{via}"


# ------------------------------------------------------------------ rules for this home
def days30(rules):
    mn = rules.get("min_nights_allowed") or 0
    return mn if mn >= 30 else 30


def airbnb_ok(rules, ptype, mode):
    """True = allowed for an owner who lives there (with the town's permit); False = not allowed; None = unknown/unclear.
    mode: 'room' (hosted room in the home you live in) or 'unit' (the other unit of your 2-4 family)."""
    s = rules.get("status") or "unknown"
    types = rules.get("str_types")
    if s.startswith("banned") and not types:
        return False
    if s in ("unknown", "no_dedicated_ordinance_pending") or rules.get("confidence") == "low":
        return None if not (types and ptype not in types) else False
    if s.startswith("banned") and types:          # e.g. West New York: owner-occupied 2-4 family only, disputed
        return None if ptype in types and mode == "unit" else False
    if s in ("owner_occupied_permit_only", "permit_required", "registration_required_host_present"):
        if types and ptype not in types:
            return False
        if mode == "room" and types:               # towns that allow only a whole unit of a 2-5 family
            return False
        return True
    return None


def nights_cap(rules, mode):
    caps = [rules.get("max_nights_year")]
    if mode == "unit":
        caps.append(rules.get("unhosted_cap_nights"))
    caps = [c for c in caps if c]
    return min(caps) if caps else None


# ------------------------------------------------------------------ helpers
LV = ("low", "typ", "high")


def _lv(p25, med, p75):
    if not med:
        return None
    return {"low": p25 or med, "typ": med, "high": p75 or med}


def pick(levels, key, sel):
    """levels: {'low','typ','high'} dict; sel['lvl'][key] in low|typ|high|own; sel['own'][key] is the typed value."""
    lvl = (sel.get("lvl") or {}).get(key, "typ")
    own = (sel.get("own") or {}).get(key)
    if lvl == "own" and own:
        return float(own)
    if not levels:
        return float(own) if own else None
    return float(levels.get(lvl if lvl in LV else "typ") or levels["typ"])


def balance_after(loan, rate_pct, years, months):
    r = rate_pct / 100 / 12
    p = pmt(loan, rate_pct, years)
    if r == 0:
        return loan - p * months
    return loan * (1 + r) ** months - p * ((1 + r) ** months - 1) / r


def five_years(loan, price, cash_in, pay, growth):
    bal = balance_after(loan["loan_amount"], loan["rate_pct"], 30, 60)
    paid_down = loan["loan_amount"] - bal
    gain = price * ((1 + growth) ** 5 - 1)
    return {"principal_paid": round(paid_down), "value_gain": round(gain), "value_5y": round(price * (1 + growth) ** 5),
            "equity_5y": round(price * (1 + growth) ** 5 - bal), "paid_5y": round(cash_in + pay * 60), "growth": growth}


# ------------------------------------------------------------------ core compare
def _room_short(A, rules, ptype, room_str, room_mtr, room_rent_typ, sel):
    """Best legal short/30+ option for ONE furnished room you host. Returns dict or None."""
    opts = []
    ok = airbnb_ok(rules, ptype, "room")
    s = (room_str or {}).get("summary") or {}
    if ok and s.get("n"):
        occ = min(s.get("occ_median_sf_model") or 0, A["str"]["occupancy_cap"])
        nights = occ * 365
        cap = nights_cap(rules, "room")
        if cap:
            nights = min(nights, cap)
        levels = _lv(*(x * nights if x else None for x in (s.get("adr_p25"), s.get("adr_median"), s.get("adr_p75"))))
        rev = pick(levels, "str", sel)
        R = A.get("room", {})
        cost = rev * A["str"]["platform_fee_pct"] / 12 + nights / A["str"]["avg_stay_nights"] * R.get("cleaning_per_turn", 45) / 12 \
            + nights * A["str"]["supplies_per_booked_night"] / 12 + R.get("insurance_monthly", 40) + R.get("furnishing_cost", 1500) / 36
        opts.append({"kind": "airbnb", "gross": rev / 12, "costs": cost, "net": rev / 12 - cost, "levels": levels, "nights": round(nights),
                     "cap": cap, "n": s.get("n"), "adr": s.get("adr_median")})
    m = room_mtr or {}
    if m.get("ok") and m.get("monthly_equiv_median"):
        disc = 1 - A["mtr"]["monthly_discount_on_listed_nightly"]
        levels = _lv(*(x * disc if x else None for x in (m.get("monthly_equiv_p25"), m.get("monthly_equiv_median"), m.get("monthly_equiv_p75"))))
        capv = (room_rent_typ or 0) * A["mtr"]["max_premium_over_ltr"]
        if capv:
            levels = {k: min(v, capv) for k, v in levels.items()}
        rate = pick(levels, "mtr", sel)
        R = A.get("room", {})
        gross = rate * A["mtr"]["occupancy"]
        cost = gross * A["mtr"]["platform_fee_pct"] + A["mtr"]["turnovers_per_year"] * R.get("cleaning_per_turn", 45) / 12 \
            + R.get("insurance_monthly", 40) + R.get("furnishing_cost", 1500) / 36
        opts.append({"kind": "mtr", "rate": rate, "gross": gross, "costs": cost, "net": gross - cost, "levels": levels, "n": m.get("n"),
                     "capped": bool(capv and m.get("monthly_equiv_median") * disc > capv)})
    return opts


def _unit_short(A, rules, ptype, ub, unit, unit_rent_typ, sel, util_inc=False):
    opts = []
    ok = airbnb_ok(rules, ptype, "unit")
    s = (unit.get("str") or {}).get("summary") or {}
    if ok and s.get("n"):
        occ = min(s.get("occ_median_sf_model") or 0, A["str"]["occupancy_cap"])
        nights = occ * 365
        cap = nights_cap(rules, "unit")
        if cap:
            nights = min(nights, cap)
        levels = _lv(*(x * nights if x else None for x in (s.get("adr_p25"), s.get("adr_median"), s.get("adr_p75"))))
        rev = pick(levels, "str", sel)
        op = str_operating(rev, nights, ub, A, utilities_included=util_inc)
        c = sum(op.values())
        opts.append({"kind": "airbnb", "gross": rev / 12, "costs": c, "costs_detail": op, "net": rev / 12 - c, "levels": levels,
                     "nights": round(nights), "cap": cap, "n": s.get("n"), "adr": s.get("adr_median")})
    m = unit.get("mtr") or {}
    if m.get("ok") and m.get("monthly_equiv_median"):
        disc = 1 - A["mtr"]["monthly_discount_on_listed_nightly"]
        levels = _lv(*(x * disc if x else None for x in (m.get("monthly_equiv_p25"), m.get("monthly_equiv_median"), m.get("monthly_equiv_p75"))))
        capv = (unit_rent_typ or 0) * A["mtr"]["max_premium_over_ltr"]
        if capv:
            levels = {k: min(v, capv) for k, v in levels.items()}
        rate = pick(levels, "mtr", sel)
        gross, op = mtr_operating(rate, ub, A)
        c = sum(op.values())
        opts.append({"kind": "mtr", "rate": rate, "gross": gross, "costs": c, "costs_detail": op, "net": gross - c, "levels": levels,
                     "n": m.get("n"), "capped": bool(capv and m.get("monthly_equiv_median") * disc > capv)})
    return opts


def fix_keys(o):
    """JSON round-trips turn {0: 150} tables into {'0': 150}; turn digit keys back into ints."""
    if isinstance(o, dict):
        return {(int(k) if isinstance(k, str) and k.isdigit() else k): fix_keys(v) for k, v in o.items()}
    return o


def compare(base, sel):
    """base: {'A', 'rules', 'ptype', 'total_cost', 'loan', 'price', 'beds', 'room_rent': levels|None, 'room_str', 'room_mtr',
    'units': {b: {'ltr': levels, 'str', 'mtr'}}, 'util_inc'}; sel: {'rent_out': room|unit|none, 'rooms', 'unit_beds', 'units_n', 'lvl', 'own', 'growth'}."""
    A, rules, ptype = fix_keys(base["A"]), base["rules"], base["ptype"]
    cost = base["total_cost"]
    ro = sel.get("rent_out") or "none"
    out = {"cost": round(cost), "rent_out": ro, "cols": [], "levels": {}, "notes": []}
    col1 = {"key": "live", "pay": round(cost), "income": 0}
    col2 = {"key": "long", "pay": None, "income": None}
    col3 = {"key": "short", "pay": None, "income": None, "kind": None}
    d30 = days30(rules)
    out["days30"] = d30
    if ro == "room":
        n = max(int(sel.get("rooms") or 1), 1)
        lv = base.get("room_rent")
        rent_each = pick(lv, "rent", sel)
        out["levels"]["rent"] = lv
        if rent_each:
            col2.update(pay=round(cost - n * rent_each), income=round(n * rent_each), each=round(rent_each), n=n)
        opts = _room_short(A, rules, ptype, base.get("room_str"), base.get("room_mtr"), (lv or {}).get("typ"), sel)
        airbnb_allowed = airbnb_ok(rules, ptype, "room")
    elif ro == "unit":
        ub = int(sel.get("unit_beds") or 2)
        n = max(int(sel.get("units_n") or 1), 1)
        unit = (base.get("units") or {}).get(ub) or (base.get("units") or {}).get(str(ub)) or {}
        lv = unit.get("ltr")
        rent_u = pick(lv, "rent", sel)
        out["levels"]["rent"] = lv
        if rent_u:
            vac = A["ownership_costs"]["vacancy_pct_ltr"]
            inc = n * rent_u * (1 - vac)
            col2.update(pay=round(cost - inc), income=round(inc), each=round(rent_u), n=n)
            share = A.get("fha_rules", {}).get("rent_share_counted", 0.75)
            out["qualify"] = {"counted": round(share * n * rent_u), "share": share, "fair_rent": round(n * rent_u)}
            if base.get("units_total", 2) >= 3:
                ded = A.get("fha_rules", {}).get("self_sufficiency_deduct", 0.25)
                net_all = (n + 1) * rent_u * (1 - ded)
                out["qualify"]["self_sufficiency"] = {"piti": round(base.get("piti") or 0), "net_rent_all": round(net_all),
                                                      "passes": bool(base.get("piti") and base["piti"] <= net_all)}
        opts = _unit_short(A, rules, ptype, ub, unit, (lv or {}).get("typ"), sel, base.get("util_inc"))
        opts = [dict(o, net=o["net"] * n, gross=o["gross"] * n, costs=o["costs"] * n) for o in opts]
        airbnb_allowed = airbnb_ok(rules, ptype, "unit")
    else:
        opts, airbnb_allowed = [], airbnb_ok(rules, ptype, "room")
    for o in opts:
        out["levels"]["str" if o["kind"] == "airbnb" else "mtr"] = o["levels"]
    if opts:
        best = max(opts, key=lambda o: o["net"])
        col3.update(pay=round(cost - best["net"]), income=round(best["net"]), kind=best["kind"], best=best, options=opts)
    out["airbnb_allowed"] = airbnb_allowed
    out["cols"] = [col1, col2, col3]
    # cash in / cash out (feature 5)
    loan = base.get("loan")
    if loan and base.get("price"):
        furn = 0
        if col3.get("kind"):
            if ro == "room":
                furn = A.get("room", {}).get("furnishing_cost", 1500) * max(int(sel.get("rooms") or 1), 1)
            else:
                from .config import by_beds
                furn = by_beds(A["str"]["furnishing_cost_by_beds"], int(sel.get("unit_beds") or 2)) * max(int(sel.get("units_n") or 1), 1)
        g = float(sel.get("growth", 0.02))
        out["cash"] = {"cash_to_close": loan["cash_to_close_est"], "down": loan["down_payment"], "closing": loan["closing_costs_est"], "furniture": round(furn),
                       "five": {c["key"]: five_years(loan, base["price"], loan["cash_to_close_est"] + (furn if c["key"] == "short" else 0), c["pay"], g)
                                for c in (col1, col2, col3) if c.get("pay") is not None}}
    return out


# ------------------------------------------------------------------ adapters
def _unit_levels(u):
    e = (u or {}).get("ltr") or {}
    hud = (u or {}).get("hud")
    if e.get("ok") and hud and e.get("median") and e.get("p25") and e["median"] > 1.4 * hud:
        # listings here are mostly new luxury buildings; an older 2-family unit rents nearer HUD's fair rent.
        # low = HUD fair rent, typical = halfway between HUD and the cheapest quarter of listings, high = listing median
        return {"low": hud, "typ": round((hud + min(e["p25"], e["median"])) / 2), "high": e["median"], "skewed": True}
    if e.get("ok"):
        return _lv(e.get("p25"), e.get("median"), e.get("p75"))
    if u and u.get("hud"):
        return {"low": u["hud"] * 0.9, "typ": u["hud"], "high": u["hud"] * 1.1, "hud": True}
    return None


def base_from_property(r):
    """Build the compare inputs from analyze_property() output."""
    sc = {s["key"]: s for s in r.get("scenarios") or []}
    o = sc.get("owner_roommates")
    if not o:
        return None
    f = r.get("facts") or {}
    ptype = (f.get("ownership") or "").lower()
    ro = r.get("rooms") or {}
    room_lv = _lv(ro.get("p25"), ro.get("median"), ro.get("p75")) if ro.get("ok") else \
        ({"low": o["room_rent_each"] * .9, "typ": o["room_rent_each"], "high": o["room_rent_each"] * 1.1, "estimate": True} if o.get("room_rent_each") else None)
    ex = r.get("extra") or {}
    units = {int(b): dict(u, ltr=_unit_levels(u)) for b, u in (ex.get("units") or {}).items()}
    c = o["costs"]
    piti = c.get("principal_interest", 0) + c.get("mortgage_insurance", 0) + c.get("property_tax", 0) + c.get("insurance", 0) + c.get("hoa_or_maintenance", 0)
    return {"A": r["assumptions"], "rules": r.get("str_rules") or {}, "ptype": ptype, "total_cost": o["total_cost"], "loan": o["loan"],
            "price": f.get("price"), "beds": f.get("beds"), "room_rent": room_lv, "room_str": ex.get("room_str"), "room_mtr": ex.get("room_mtr"),
            "units": units, "units_total": ex.get("units_total", 2), "piti": piti,
            "util_inc": "utilities" in [x.lower() for x in f.get("hoa_includes") or []]}


def default_sel(r_or_base, mode="first"):
    b = r_or_base
    ptype = b.get("ptype", "")
    beds = int(b.get("beds") or 2)
    if ptype == "multi-family":
        ro, ub = "unit", min(max(beds // 2, 1), 3)
    else:
        ro, ub = ("room" if beds >= 2 else "none"), 2
    return {"rent_out": ro, "rooms": 1, "unit_beds": ub, "units_n": 1 if b.get("units_total", 2) < 3 else 2,
            "lvl": {"rent": "typ", "mtr": "typ", "str": "typ"}, "own": {}, "growth": 0.02}


# ------------------------------------------------------------------ town: the user taps a price and a size
TOWN_SIZES = ["1", "2", "3", "2fam"]
PRICE_CHIPS = [250_000, 300_000, 350_000, 400_000, 460_000]


def base_from_town(snap, price, size, down_pct=None):
    """Same compare inputs for a town, at the price the user tapped. Taxes use the fallback rate (flagged); HOA unknown (flagged)."""
    from .finance import loan_costs, carrying_costs
    A = fix_keys(snap["assumptions"])
    fi = A["financing"]
    rt = snap.get("rates") or {}
    lc = loan_costs(price, down_pct if down_pct is not None else fi["fha_down_pct"], rt.get("fha", 6.5), fi["term_years"], fha=True, A=A)
    two = size == "2fam"
    beds = 4 if two else int(size)
    facts = {"price": price, "beds": beds, "ownership": "multi-family" if two else "single-family", "hoa_monthly": 0}
    trate = town_tax_rate(snap.get("town"))
    if trate:
        facts["taxes_annual"] = round(price * trate)
    cc, _ = carrying_costs(facts, A, "owner")
    costs = {"principal_interest": lc["principal_interest"], "mortgage_insurance": lc["mortgage_insurance"], **cc}
    bb = {int(k): v for k, v in (snap.get("by_beds") or {}).items()}
    ro = snap.get("rooms") or {}
    room_lv = _lv(ro.get("p25"), ro.get("median"), ro.get("p75")) if ro.get("ok") else None
    if not room_lv:
        whole = _unit_levels(bb.get(beds if beds <= 3 else 3))
        if whole:
            share = A["roommate"]["room_rent_fallback_share"]
            room_lv = {k: v * share for k, v in whole.items() if k in LV} | {"estimate": True}
    units = {b: dict(bb[b], ltr=_unit_levels(bb[b])) for b in (1, 2, 3) if b in bb}
    piti = sum(costs[k] for k in ("principal_interest", "mortgage_insurance", "property_tax", "insurance", "hoa_or_maintenance"))
    return {"A": A, "rules": snap.get("str_rules") or {}, "ptype": facts["ownership"], "total_cost": sum(costs.values()), "costs": costs, "loan": lc,
            "price": price, "beds": beds, "room_rent": room_lv, "room_str": snap.get("room_str"), "room_mtr": snap.get("room_mtr"),
            "units": units, "units_total": 2, "piti": piti, "util_inc": False, "tax_fallback": not trate, "tax_rate": trate or A["ownership_costs"]["property_tax_rate_fallback"]}


def town_rank(mode, price=350_000, rate_pct=None):
    """Town list for a mode, each with drive time and what you'd pay a month on a 2-family at `price` renting the other
    unit at HUD's fair rent for the town's ZIP (2 bedrooms). first: sorted by drive rank + cost rank; next: by cost only."""
    from .finance import loan_costs, carrying_costs
    from .config import load_assumptions
    from .sources import hud
    A = load_assumptions()
    fi = A["financing"]
    lc = loan_costs(price, fi["fha_down_pct"], 6.5 if rate_pct is None else rate_pct, fi["term_years"], fha=True, A=A)
    rows = []
    for t in mode_towns(mode):
        ti = town_info(t)
        if not ti:
            continue
        f_ = {"price": price, "beds": 4, "ownership": "multi-family"}
        if ti.get("eff_tax"):
            f_["taxes_annual"] = round(price * ti["eff_tax"])
        cc, _ = carrying_costs(f_, A, "owner")
        cost = lc["principal_interest"] + lc["mortgage_insurance"] + sum(cc.values())
        sf = hud.safmr(ti.get("zip")) or {}
        rent2 = sf.get("2br")
        pay = round(cost - rent2 * (1 - A["ownership_costs"]["vacancy_pct_ltr"])) if rent2 else None
        rows.append({"town": t, "drive": drive(town=t, route=False), "hud_2br": rent2, "zip": ti.get("zip"), "pay_2fam": pay, "caution": ti.get("caution")})
    ok = [r for r in rows if r["pay_2fam"] is not None]
    if mode == "first":
        dr = {r["town"]: i for i, r in enumerate(sorted(ok, key=lambda r: r["drive"]["min"]))}
        pr = {r["town"]: i for i, r in enumerate(sorted(ok, key=lambda r: r["pay_2fam"]))}
        ok.sort(key=lambda r: (dr[r["town"]] + pr[r["town"]], r["drive"]["min"]))
    else:
        ok.sort(key=lambda r: r["pay_2fam"])
    return {"rows": ok + [r for r in rows if r["pay_2fam"] is None], "price": price, "rate_pct": lc["rate_pct"]}


# ------------------------------------------------------------------ bilingual labels shared by the app and the reports
def _m(v):
    if v is None:
        return "?"
    v = round(float(v))
    return f"-${abs(v):,}" if v < 0 else f"${v:,}"


def airbnb_badge(ok, d30):
    if ok is True:
        return ("⚠️ Airbnb only with a town permit", "⚠️ Airbnb solo con permiso del municipio")
    if ok is False:
        return (f"🚫 No Airbnb · ✓ {d30}+ day OK", f"🚫 Sin Airbnb · ✓ {d30}+ días sí")
    return (f"❓ Airbnb rules unclear · ✓ {d30}+ day", f"❓ Reglas de Airbnb no claras · ✓ {d30}+ días")


def labels(out, first_mode=True):
    """[(title, pay_label, pay_value, sub, badge, star)] per column, each text an (en, es) pair."""
    ro = out["rent_out"]
    c1, c2, c3 = out["cols"]
    d30 = out.get("days30", 30)

    def pay(c):
        p = c.get("pay")
        if p is None:
            return (("You pay", "Usted paga"), "—")
        if p < 0:
            return (("You earn", "Usted gana"), "+" + _m(-p))
        return (("You pay", "Usted paga"), _m(p))

    cols = []
    lbl, v = pay(c1)
    cols.append({"key": "live", "title": ("Buy & live", "Comprar y vivir"), "pay_lbl": lbl, "pay": v, "sub": ("a month, just you", "al mes, solo usted"),
                 "badge": ("✓ FHA, you live there", "✓ FHA, usted vive allí"), "star": False})
    t2 = {"room": ("+ Roommate", "+ Compañero"), "unit": ("+ Tenant", "+ Inquilino")}.get(ro, ("+ Long-term tenant", "+ Inquilino"))
    lbl, v = pay(c2)
    if c2.get("income") is None:
        sub2 = ("tap what you'd rent out", "toque qué alquilaría")
    elif ro == "unit":
        sub2 = (f"after {_m(c2['income'])} rent", f"con {_m(c2['income'])} de renta")
    else:
        sub2 = (f"after {_m(c2['income'])} rent", f"con {_m(c2['income'])} de renta")
    b2 = ("✓ Legal · the lender won't count it", "✓ Legal · el banco no lo cuenta") if ro == "room" else \
        (("✓ Legal · 75% can count for the loan", "✓ Legal · 75% cuenta para el préstamo") if ro == "unit" else ("—", "—"))
    cols.append({"key": "long", "title": t2, "pay_lbl": lbl, "pay": v, "sub": sub2, "badge": b2, "star": bool(first_mode)})
    kind = c3.get("kind")
    t3 = ("+ Airbnb", "+ Airbnb") if kind == "airbnb" else ((f"+ {d30}+ day", f"+ {d30}+ días") if kind == "mtr" else ("+ Airbnb or 30+ day", "+ Airbnb o 30+ días"))
    lbl, v = pay(c3)
    if c3.get("income") is None:
        sub3 = ("tap what you'd rent out", "toque qué alquilaría") if ro == "none" else ("no data nearby", "sin datos cerca")
    else:
        sub3 = (f"after {_m(c3['income'])} left from guests", f"con {_m(c3['income'])} netos de huéspedes")
    cols.append({"key": "short", "title": t3, "pay_lbl": lbl, "pay": v, "sub": sub3, "badge": airbnb_badge(out.get("airbnb_allowed"), d30), "star": False})
    return cols
