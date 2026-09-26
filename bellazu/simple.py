"""Plain-language summaries for the simple phone UI (presentation only; no new numbers).
Every figure shown here comes straight from analyze_property() / scan_arbitrage() output.
Each text is an (english, spanish) pair."""
import re

NAVY = "#1F3A5F"


def money(v):
    if v is None or (isinstance(v, float) and v != v):
        return "?"
    v = round(float(v))
    return f"-${abs(v):,}" if v < 0 else f"${v:,}"


def thousands(v):
    return f"${round(float(v) / 1000):,}K"


def miles(km):
    try:
        return f"{float(km) * 0.621:.1f} mi"
    except (TypeError, ValueError):
        return ""


def plain(s):
    """Strip symbols/jargon markers from engine strings before showing them."""
    s = str(s or "")
    for a, b in (("≈ ", "about "), ("≈", "about "), (" -> ", " to "), ("->", " to "), (" → ", " to "), ("→", " to "),
                 ("⚠️", ""), ("ASSUMPTION", "estimate"), ("SUPUESTO", "estimado"), ("PROXY", "rough guide"), ("NOT ", "not "), ("NO ", "no ")):
        s = s.replace(a, b)
    return re.sub(r"\s{2,}", " ", s).strip()


# ------------------------------------------------------------------ property
def rent_used(r):
    """(monthly rent the engine used for the whole home, which source)."""
    rc = r.get("rent_compare") or {}
    ch = rc.get("chosen")
    if ch == "rentcast":
        return rc.get("rentcast_rent"), "rentcast"
    if ch == "free":
        return rc.get("free_median"), "free"
    if ch == "hud_safmr":
        beds = min(int((r.get("facts") or {}).get("beds") or 2), 4)
        return ((r.get("benchmarks") or {}).get("hud_safmr") or {}).get(f"{beds}br"), "hud"
    return None, None


def scenarios(r):
    return {s["key"]: s for s in r.get("scenarios") or []}


def roommates_txt(n):
    return (f"{n} roommate" + ("" if n == 1 else "s"), f"{n} compañero" + ("" if n == 1 else "s"))


def verdict_property(r, star=None):
    """{'level': good|maybe|skip, 'en', 'es'}. Rules (shown to the user under 'See details'):
    skip  = income entered is below the co-op board rule, or housing > 45% of income entered,
            or even with roommates it costs more than renting a similar home;
    maybe = co-op board income rule with no income entered, housing 36-45% of income, missing
            building fee, or costs sit between the two;
    good  = living there costs no more than the rent a similar home gets."""
    sc = scenarios(r)
    o = sc.get("owner_roommates")
    f = r.get("facts") or {}
    if not o:
        return {"level": "maybe", "en": "We need the price to give you an answer.", "es": "Necesitamos el precio para darle una respuesta.",
                "next_en": "Tap 'Add the price' just below and we'll redo the math.", "next_es": "Toque 'Agregar el precio' aquí abajo y volvemos a calcular."}
    rent, _ = rent_used(r)
    inc = r.get("income_annual")
    ic = r.get("coop_income_check")
    own, total, n = o.get("own_net_housing_cost"), o.get("total_cost"), int(o.get("rooms_rented") or 0)
    what = (roommates_txt(n)[0], roommates_txt(n)[1])
    if star and star.get("pay") is not None:      # the compare view's starred column (e.g. renting the other unit of a 2-family)
        own, what, n = star["pay"], star["what"], max(n, 1)
    dti = o.get("front_end_dti")
    red, yellow, green = [], [], []
    if ic and inc and inc < ic["required_income_with_mortgage"]:
        red.append((f"Co-op board wants about {thousands(ic['required_income_with_mortgage'])} a year in income; you entered {thousands(inc)}",
                    f"La junta de la co-op pide unos {thousands(ic['required_income_with_mortgage'])} de ingreso al año; usted puso {thousands(inc)}"))
    if dti is not None and dti > 0.45:
        red.append((f"Housing would take {dti:.0%} of your income, more than lenders usually allow",
                    f"La vivienda se llevaría el {dti:.0%} de su ingreso, más de lo que suelen permitir los prestamistas"))
    if rent and own is not None and own >= rent:
        red.append((f"Even with {what[0]} it costs you {money(own)}/mo, more than renting a place like it",
                    f"Aun con {what[1]} le cuesta {money(own)}/mes, más que alquilar algo parecido"))
    if ic and not inc:
        yellow.append((f"Co-op board wants a yearly income of {thousands(ic['required_income_maintenance_only'])} or more",
                       f"La junta de la co-op pide un ingreso anual de {thousands(ic['required_income_maintenance_only'])} o más"))
    if dti is not None and 0.36 < dti <= 0.45:
        yellow.append((f"Housing would take {dti:.0%} of your income, which is high for lenders",
                       f"La vivienda se llevaría el {dti:.0%} de su ingreso, alto para los prestamistas"))
    if not f.get("hoa_monthly") and any(x in (f.get("ownership") or "") for x in ("condo", "co-op")):
        yellow.append(("We don't know the monthly building fee yet, so costs may be higher",
                       "Aún no sabemos la cuota mensual del edificio; el costo puede ser mayor"))
    if own is not None and own <= 0:
        green.append((f"With {what[0]}, the rent would cover all of your monthly costs", f"Con {what[1]}, la renta cubriría todos sus costos mensuales"))
    elif rent and total is not None and total <= rent:
        green.append((f"Owning costs {money(total)}/mo, less than the {money(rent)}/mo a home like it rents for",
                      f"Comprarla le cuesta {money(total)}/mes, menos que los {money(rent)}/mes de alquiler de algo parecido"))
    board_q = bool(ic and not inc)
    if red:
        lvl, why = "skip", red[0]
        nxt = ("Keep looking and try another address. It's free, and the right home is out there 💕",
               "Siga buscando y pruebe otra dirección. Es gratis, y la casa indicada existe 💕")
    elif yellow:
        lvl, why = "maybe", yellow[0]
        nxt = (("Ask the listing agent about the board's income rule, and add your income in ⚙️ My settings.",
                "Pregunte al agente por la regla de ingreso de la junta y agregue su ingreso en ⚙️ Mis ajustes.") if board_q else
               ("Ask a lender if you pre-qualify, and check the items under See details.",
                "Pregunte a un prestamista si precalifica y revise los puntos en Ver detalles."))
    elif green:
        lvl, why = "good", green[0]
        nxt = ("Ask a lender if you pre-qualify, then ask the agent for the building rules.",
               "Pregunte a un prestamista si precalifica y luego pida al agente las reglas del edificio.")
    else:
        lvl = "maybe"
        why = ((f"Costs you {money(own)}/mo with {what[0]}", f"Le cuesta {money(own)}/mes con {what[1]}") if n
               else (f"Costs you {money(total)}/mo", f"Le cuesta {money(total)}/mes"))
        nxt = ("Ask a lender if you pre-qualify, and check the items under See details.",
               "Pregunte a un prestamista si precalifica y revise los puntos en Ver detalles.")
    return {"level": lvl, "en": why[0], "es": why[1], "next_en": nxt[0], "next_es": nxt[1]}


def _days(rules):
    mn = rules.get("min_nights_allowed") or 0
    return mn if mn >= 30 else 30


def airbnb_line(rules, who="owner"):
    """(icon, en, es) one-liner about short-term rental rules."""
    s = rules.get("status") or "unknown"
    d = _days(rules)
    if s == "unknown":
        return "❓", "Airbnb: We don't have this town's rules. Ask the town first.", "Airbnb: No tenemos las reglas de este pueblo. Pregunte al municipio primero."
    if s.startswith("banned"):
        return "🚫", f"Airbnb: Not allowed here. {d}+ day rentals OK.", f"Airbnb: No se permite aquí. Alquileres de {d}+ días sí."
    if s == "owner_occupied_permit_only":
        if who == "owner":
            return "⚠️", f"Airbnb: Only if you live there and get a town permit. {d}+ day rentals OK.", f"Airbnb: Solo si usted vive allí y saca un permiso. Alquileres de {d}+ días sí."
        return "🚫", f"Airbnb: Not allowed for renters here. {d}+ day rentals OK.", f"Airbnb: No se permite a inquilinos aquí. Alquileres de {d}+ días sí."
    if s.startswith("registration_required"):
        return "⚠️", "Airbnb: Only if the host lives there and registers.", "Airbnb: Solo si el anfitrión vive allí y se registra."
    ok = rules.get("str_legal_for_owner" if who == "owner" else "str_legal_for_tenant")
    if ok:
        return "⚠️", "Airbnb: Rules are unclear here. Check with City Hall first.", "Airbnb: Las reglas no están claras. Consulte al municipio primero."
    return "🚫", f"Airbnb: Not allowed here. {d}+ day rentals OK.", f"Airbnb: No se permite aquí. Alquileres de {d}+ días sí."


FIELD = {"price": ("price", "precio"), "beds": ("bedrooms", "habitaciones"), "hoa_monthly": ("monthly building fee", "cuota mensual del edificio")}


def plain_warnings(r):
    """Engine warnings rewritten as short everyday lines. Returns [(en, es)]."""
    out = []
    rc = r.get("rent_compare") or {}
    for w in r.get("warnings") or []:
        if w.startswith("Building income rule"):
            continue   # shown under Building rules
        if w.startswith("Rent estimates disagree") and rc.get("gap_pct") is not None:
            continue   # shown as one line under Rent estimate
        if w.startswith("Property taxes are included"):
            out.append(("Property taxes are included in the monthly building fee.", "Los impuestos están incluidos en la cuota mensual del edificio."))
        elif w.startswith("TAXES UNKNOWN"):
            pctv = (r.get("assumptions") or {}).get("ownership_costs", {}).get("property_tax_rate_fallback", 0.022)
            out.append((f"We don't know the property taxes, so we used {pctv:.1%} of the price a year. Get the real tax bill.",
                        f"No sabemos los impuestos, así que usamos {pctv:.1%} del precio al año. Pida la factura real de impuestos."))
        elif w.startswith("Missing listing facts"):
            ks = [k.strip() for k in w.split(":", 1)[1].split("—")[0].split(",")]
            en = ", ".join(FIELD.get(k, (k, k))[0] for k in ks if k)
            es = ", ".join(FIELD.get(k, (k, k))[1] for k in ks if k)
            out.append((f"We couldn't find the {en}. Tap 'Fix the home facts' to add it.", f"No encontramos: {es}. Toque 'Corregir datos de la casa' para agregarlo."))
        elif w.startswith("No Inside Airbnb dataset covers"):
            t = r.get("town") or "this town"
            out.append((f"Airbnb price data comes from a nearby city, not {t}, so treat Airbnb numbers as rough.",
                        f"Los datos de Airbnb vienen de una ciudad cercana, no de {t}; tómelos como aproximados."))
        else:
            out.append((plain(w), plain(w)))
    return out


def rent_gap_line(r):
    rc = r.get("rent_compare") or {}
    if not rc.get("big_gap"):
        return None
    used = "RentCast" if rc.get("chosen") == "rentcast" else "the nearby listings"
    used_es = "RentCast" if rc.get("chosen") == "rentcast" else "los anuncios cercanos"
    g = abs(rc["gap_pct"])
    return (f"The two rent estimates differ by {g:.0%}. We used {used} because it had more examples. Ask a local agent.",
            f"Los dos estimados de renta difieren un {g:.0%}. Usamos {used_es} porque tenía más ejemplos. Consulte a un agente local.")


# ------------------------------------------------------------------ town scan
def verdict_town(a):
    sr = a.get("str_rules") or {}
    t, d = a.get("town", ""), _days(sr)
    s = sr.get("status") or "unknown"
    if s == "unknown":
        return {"level": "maybe", "title_en": f"We don't have Airbnb rules for {t} yet", "title_es": f"Aún no tenemos las reglas de Airbnb de {t}",
                "en": "Ask the town before renting anything out, just to be safe.", "es": "Pregunte al municipio antes de alquilar, para estar tranquila."}
    if not sr.get("str_legal_for_tenant"):
        return {"level": "skip", "title_en": f"Airbnb isn't allowed for renters in {t}", "title_es": f"En {t} los inquilinos no pueden hacer Airbnb",
                "en": f"Good news: furnished rentals of {d}+ days are OK, with your landlord's written permission ✨",
                "es": f"Buena noticia: los alquileres amueblados de {d}+ días sí se permiten, con permiso escrito del dueño ✨"}
    return {"level": "maybe", "title_en": f"Airbnb rules for renters in {t} aren't clear", "title_es": f"Las reglas de Airbnb para inquilinos en {t} no están claras",
            "en": "Check with City Hall first. You always need your landlord's written permission.",
            "es": "Consulte primero al municipio. Siempre necesita permiso escrito del dueño."}


def top_rentals(a, n=5):
    good = [x for x in a.get("results") or [] if not x.get("check_flag")]
    return sorted(good, key=lambda x: -(x.get("mtr_profit_monthly") or -1e9))[:n]


def listing_name(x):
    s = str(x.get("address") or "").strip() or str(x.get("title") or "").strip()
    s = re.sub(r"[*_#`]+", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return (s[:70] + "...") if len(s) > 72 else s
