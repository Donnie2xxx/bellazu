"""Rendering (separate from core). Bilingual HTML (EN/ES toggle, phone-friendly), Markdown, XLSX, CSV, JSON."""
import json, re, html as H, datetime as dt, pathlib
import pandas as pd
from .i18n import t, COST

CSS = """@import url('https://fonts.googleapis.com/css2?family=League+Gothic&family=Inter:wght@300;400;500;600;700&family=Instrument+Serif&display=swap');
:root{--ink:#141414;--mute:#6F6F6F;--line:#E6E0E2;--rose:#D8567C;--rose2:#FBE7ED;--paper:#FFFFFF;--good:#1E7A4B;--bad:#B3264F}
body{font-family:Inter,-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:860px;margin:0 auto;padding:18px 18px 40px;color:var(--ink);font-size:15px;line-height:1.55;background:var(--paper)}
.brand{font-family:'Instrument Serif',Georgia,serif;font-size:30px;line-height:1;padding:6px 0 12px;border-bottom:1px solid var(--ink);margin-bottom:18px}.brand i{font-style:normal;color:var(--rose)}
h1{font-family:'League Gothic',Impact,sans-serif;font-weight:400;text-transform:uppercase;font-size:46px;line-height:.95;letter-spacing:.01em;margin:.1em 0 .25em}
h2{font-family:'League Gothic',Impact,sans-serif;font-weight:400;text-transform:uppercase;font-size:28px;line-height:1;letter-spacing:.01em;margin:1.4em 0 .5em;padding-top:.7em;border-top:1px solid var(--line)}
ul{padding-left:1.1em}li{margin:.35em 0}
table{border-collapse:collapse;width:100%;margin:.5em 0 .8em;font-size:.9em}td,th{border-bottom:1px solid var(--line);padding:8px 8px;text-align:left;vertical-align:top}
th{font-size:.72em;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);font-weight:500;border-bottom:1px solid var(--ink)}.num{text-align:right;font-variant-numeric:tabular-nums}
.neg{color:var(--bad);font-weight:600}.pos{color:var(--good);font-weight:600}
.box{background:var(--rose2);border:1px solid #F3C6D3;border-radius:18px;padding:12px 16px;margin:.8em 0}.bad{background:#FDEEF2;border-color:#F0B8C8}.ok{background:#EAF6EF;border-color:#BFE3CD}
.small{font-size:.8em;color:var(--mute)}
.toggle{position:sticky;top:0;background:var(--paper);padding:8px 0;z-index:9;display:flex;gap:6px}.toggle button{padding:8px 14px;border:1px solid var(--ink);background:var(--paper);color:var(--ink);border-radius:100px;
 text-transform:uppercase;letter-spacing:.06em;font-size:.72em;font-family:inherit;cursor:pointer}.toggle button:hover{background:var(--ink);color:var(--paper)}
body.only-en .es{display:none}body.only-es .en{display:none}body.both div.es{display:block;color:var(--mute);margin-top:2px}body.both span.es{display:inline}
body.both span.es:before{content:" / "}a{color:var(--rose);word-break:break-word}
@media(max-width:600px){body{padding:14px}h1{font-size:38px}table{font-size:.8em}td,th{padding:6px 4px}}
@media print{.toggle{display:none}body{max-width:none}}"""
JS = "<script>function L(m){document.body.className=m;try{localStorage.bz=m}catch(e){}};try{if(localStorage.bz)L(localStorage.bz)}catch(e){}</script>"


PLAIN = [("≈ ", "about "), ("≈", "about "), ("~$", "about $"), (" ~", " about "), ("ASSUMPTIONS", "Estimates"), ("ASSUMPTION", "Estimate"),
         ("SUPUESTOS", "Estimados"), ("SUPUESTO", "Estimado"), ("PROXY", "Rough guide"), (" — ", ": "), (" -> ", " to "), ("→", "to"),
         ("⚠️", ""), ("NOT ", "not "), ("Arbitrage Scan", "Rental Finder"), ("Análisis de Arbitraje", "Buscador de Alquileres"),
         ("(edit assumptions.yaml)", ""), ("(editar assumptions.yaml)", ""), ("edit assumptions.yaml", "our standard estimates"),
         ("Principal & interest", "Mortgage payment (loan + interest)"), ("MIP/PMI", "required with a small down payment"),
         ("Furniture (amortized)", "Furniture (spread over 3 years)"), ("Muebles (amortizados)", "Muebles (repartidos en 3 años)"),
         ("NET per month", "Left over each month"), ("NETO por mes", "Queda cada mes"), ("STR insurance", "Short-stay insurance"),
         ("Short-term rental comps (Inside Airbnb)", "Nearby Airbnb listings (Inside Airbnb)"), ("Room-rent comps", "Room rents nearby"),
         ("Comparables de alquiler a corto plazo", "Anuncios de Airbnb cercanos"), ("Comparables de renta por cuarto", "Rentas de cuartos cercanas"),
         ("Long-term rent estimate", "What a tenant would pay"), ("Reference rents", "Reference rents"), ("Referencias", "Rentas de referencia"),
         ("STR profit/mo", "Airbnb profit/mo"), ("STR rev/yr", "Airbnb income/yr"), ("STR profit", "Airbnb profit"), ("30+night", "30+ night"),
         ("Rentals ranked by estimated STR profit", "Rentals ranked by estimated profit"), ("ganancia STR estimada", "ganancia estimada"),
         ("comps", "similar listings"), ("Comps", "Similar listings"), ("LTR", "long-term rent"), (" STR ", " Airbnb-style "), ("(STR)", "(Airbnb-style)"),
         ("Median rent", "Typical rent"), ("median", "typical"), ("mediana", "típica"), ("range (25th-75th pct)", "usual range"), ("rango (percentil 25-75)", "rango usual"),
         ("Ownership type", "Type of home"), ("Tipo de propiedad", "Tipo de vivienda"), ("Cash to close (est.)", "Cash to close (estimate)"),
         ("Efectivo para cerrar (est.)", "Dinero para cerrar (estimado)"), ("unknown / desconocido", "not found / no encontrado")]


def _plain_text(t):
    for a, b in PLAIN:
        t = t.replace(a, b)
    return re.sub(r"[ \t]{2,}", " ", t)


def plainify(doc):
    """Plain-language pass over the visible text of a report (never touches tags, attributes, URLs or numbers)."""
    head, sep, body = doc.partition("<body")
    es_fix = lambda t: t.replace("≈ ", "aprox. ").replace("≈", "aprox. ").replace("~$", "aprox. $").replace(" ~", " aprox. ")
    body = re.sub(r'(<(\w+) class="es">)(.*?)(</\2>)', lambda m: m.group(1) + re.sub(r">([^<]+)<", lambda n: ">" + es_fix(n.group(1)) + "<", ">" + m.group(3) + "<")[1:-1] + m.group(4), body, flags=re.S)
    body = re.sub(r">([^<]+)<", lambda m: ">" + _plain_text(m.group(1)) + "<", body)
    head = re.sub(r"<title>(.*?)</title>", lambda m: "<title>" + _plain_text(m.group(1)) + "</title>", head, flags=re.S)
    return head + sep + body


def _open(title, lang):
    cls = {"en": "only-en", "es": "only-es"}.get(lang, "both")
    return (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><base target='_blank'>"
            f"<title>{title}</title><style>{CSS}</style></head><body class='{cls}'><div class='brand'>Bella<i>Zu</i></div>"
            "<div class='toggle'><button onclick=\"L('only-en')\">English</button><button onclick=\"L('only-es')\">Español</button><button onclick=\"L('both')\">EN + ES</button></div>")


def money(v, dec=0):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"-${abs(v):,.{dec}f}" if v < 0 else f"${v:,.{dec}f}"


def pct(v):
    return "—" if v is None else f"{v:.0%}"


def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:60]


def bi(en, es, tag="span"):
    return f'<{tag} class="en">{en}</{tag}><{tag} class="es">{es}</{tag}>'


def bk(key, tag="span"):
    return bi(H.escape(t(key, "en")), H.escape(t(key, "es")), tag)


def _table(headers, rows, num_cols=()):
    h = "<table><tr>" + "".join(f"<th>{x}</th>" for x in headers) + "</tr>"
    for r in rows:
        h += "<tr>" + "".join(f'<td class="{"num" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
    return h + "</table>"


def safe_url(u):
    u = str(u or "")
    return H.escape(u) if u.startswith(("http://", "https://")) else "#"


def _src_link(s):
    if not s:
        return ""
    s = str(s)
    if " ; " in s:
        return " · ".join(_src_link(x.strip()) for x in s.split(" ; "))
    if s.startswith("http"):
        return f'<a href="{safe_url(s)}">{H.escape(s.split("/")[2])}</a>'
    return H.escape(s)


def _rule_src(x):
    m = re.search(r"https?://\S+", x)
    if not m:
        return H.escape(x)
    u = m.group(0).rstrip(")")
    label = x.replace(m.group(0), "").strip(" :()") or u.split("/")[2]
    return f'<a href="{safe_url(u)}">{H.escape(label[:60])}</a>'


# ------------------------------------------------------------------ property
INC_ES = {"taxes": "impuestos", "utilities": "servicios (luz, gas, calefacción)", "internet": "internet", "heat/hot water": "calefacción/agua caliente"}


def property_bullets(r):
    f, sc = r["facts"], {s["key"]: s for s in r["scenarios"]}
    out = []
    inc = ", ".join(f.get("hoa_includes") or [])
    inc_es = ", ".join(INC_ES.get(x, x) for x in (f.get("hoa_includes") or []))
    out.append((f"Listed at {money(f.get('price'))}; {f.get('beds') or '?'} bd / {f.get('baths') or '?'} ba {f.get('ownership') or ''}; maintenance/HOA {money(f.get('hoa_monthly'))}/mo" + (f" (includes {inc})." if inc else "."),
                f"Precio {money(f.get('price'))}; {f.get('beds') or '?'} hab / {f.get('baths') or '?'} baños {f.get('ownership') or ''}; mantenimiento/HOA {money(f.get('hoa_monthly'))}/mes" + (f" (incluye {inc_es})." if inc else ".")))
    fh = r.get("fha") or {}
    if fh.get("eligible") is False:
        out.append((fh["note_en"], fh["note_es"]))
    o = sc.get("owner_roommates")
    if o:
        d = o.get("front_end_dti")
        inc = r.get("income_annual")
        if d is not None and inc:
            out.append((f"Living there: total cost {money(o['total_cost'])}/mo, cash to close ≈ {money(o['loan']['cash_to_close_est'])}. Housing payment = {d:.0%} of the {money(inc)}/yr income entered "
                        + ("— far above the ~31-43% lenders usually allow; qualifying is unlikely." if d > 0.45 else ("— high; a lender may push back." if d > 0.36 else "— within typical guidelines.")),
                        f"Viviendo allí: costo total {money(o['total_cost'])}/mes, efectivo para cerrar ≈ {money(o['loan']['cash_to_close_est'])}. El pago de vivienda = {d:.0%} del ingreso ingresado de {money(inc)}/año "
                        + ("— muy por encima del ~31-43% que suelen permitir los prestamistas; es poco probable calificar." if d > 0.45 else ("— alto; el prestamista podría objetar." if d > 0.36 else "— dentro de lo normal."))))
        else:
            out.append((f"Living there: total cost {money(o['total_cost'])}/mo, cash to close ≈ {money(o['loan']['cash_to_close_est'])}. Enter your annual income to see the housing-payment ratio lenders check.",
                        f"Viviendo allí: costo total {money(o['total_cost'])}/mes, efectivo para cerrar ≈ {money(o['loan']['cash_to_close_est'])}. Ingrese su ingreso anual para ver la proporción que revisan los prestamistas."))
        out.append((f"With {o['rooms_rented']} roommate(s) at ~{money(o['room_rent_each'])} each ({o['room_rent_basis']}), your own housing cost ≈ {money(o['own_net_housing_cost'])}/mo.",
                    f"Con {o['rooms_rented']} compañero(s) a ~{money(o['room_rent_each'])} c/u, su costo propio de vivienda ≈ {money(o['own_net_housing_cost'])}/mes."))
    ic = r.get("coop_income_check")
    if ic:
        bi_ = ic.get("buyer_income")
        short = bi_ is not None and bi_ < ic['required_income_with_mortgage']
        out.append((f"Building rule {ic['multiple']}:1 income-to-housing-cost: needs ≈ {money(ic['required_income_maintenance_only'])}/yr on maintenance alone ({money(ic['required_income_with_mortgage'])} with the mortgage)"
                    + (f" vs {money(bi_)} entered." + (" The board would likely reject." if short else "") if bi_ else "."),
                    f"Regla del edificio {ic['multiple']}:1 ingreso/costo: requiere ≈ {money(ic['required_income_maintenance_only'])}/año solo por mantenimiento ({money(ic['required_income_with_mortgage'])} con hipoteca)"
                    + (f" vs {money(bi_)} ingresado." + (" La junta probablemente rechazaría." if short else "") if bi_ else ".")))
    rc = r.get("rent_compare") or {}
    if rc.get("rentcast_ok"):
        g = rc.get("gap_pct")
        out.append((f"RentCast rent estimate {money(rc['rentcast_rent'])}/mo (range {money(rc.get('rentcast_low'))}–{money(rc.get('rentcast_high'))}, {rc['rentcast_n']} comps)"
                     + (f" vs free-source comps {money(rc['free_median'])} (n={rc['free_n']}); gap {g:+.0%}" + (" ⚠️ BIG GAP" if rc.get('big_gap') else "") if g is not None else "")
                     + f". Using: {'RentCast' if rc.get('chosen') == 'rentcast' else ('free comps' if rc.get('chosen') == 'free' else rc.get('chosen'))} (more comps).",
                     f"Estimado de renta RentCast {money(rc['rentcast_rent'])}/mes (rango {money(rc.get('rentcast_low'))}–{money(rc.get('rentcast_high'))}, {rc['rentcast_n']} comparables)"
                     + (f" vs comparables gratuitos {money(rc['free_median'])} (n={rc['free_n']}); diferencia {g:+.0%}" + (" ⚠️ GRAN DIFERENCIA" if rc.get('big_gap') else "") if g is not None else "")
                     + f". Se usa: {'RentCast' if rc.get('chosen') == 'rentcast' else ('comparables gratuitos' if rc.get('chosen') == 'free' else rc.get('chosen'))} (más comparables)."))
    le = r["ltr"]["estimate"]
    inv = sc.get("investment_ltr")
    if inv and rc.get("chosen") == "rentcast":
        out.append((f"Long-term rent used: {money(rc['rentcast_rent'])}/mo (RentCast, {rc['rentcast_n']} comps — more than the {rc.get('free_n', 0)} free-source comps). As a pure rental on an investment loan: {money(inv['net_monthly'])}/mo.",
                    f"Renta a largo plazo usada: {money(rc['rentcast_rent'])}/mes (RentCast, {rc['rentcast_n']} comparables — más que los {rc.get('free_n', 0)} gratuitos). Como alquiler con préstamo de inversión: {money(inv['net_monthly'])}/mes."))
    elif le.get("ok") and inv:
        out.append((f"Long-term rent estimate {money(le['median'])}/mo (range {money(le['p25'])}–{money(le['p75'])}, {le['n']} same-bedroom listings within {le['radius_km']} km). As a pure rental on an investment loan: {money(inv['net_monthly'])}/mo.",
                    f"Renta estimada a largo plazo {money(le['median'])}/mes (rango {money(le['p25'])}–{money(le['p75'])}, {le['n']} anuncios similares a {le['radius_km']} km). Como alquiler con préstamo de inversión: {money(inv['net_monthly'])}/mes."))
    s = sc.get("str")
    if s and not s.get("legal"):
        out.append((f"Airbnb/short-term: NOT legal here → not computed. {r['str_rules'].get('summary_en','')}", f"Airbnb/corto plazo: NO es legal aquí → no calculado. {r['str_rules'].get('summary_es','')}"))
    elif s:
        out.append((f"Short-term rental (rules applied): {money(s['net_monthly'])}/mo.", f"Alquiler a corto plazo (con reglas): {money(s['net_monthly'])}/mes."))
    m = sc.get("mtr")
    if m:
        out.append((f"Legal alternative — furnished 30+ night rental: ≈ {money(m['net_monthly'])}/mo ({m['caveat_en']})", f"Alternativa legal — alquiler amueblado 30+ noches: ≈ {money(m['net_monthly'])}/mes ({m['caveat_es']})"))
    return out


def _rc_status_text(s):
    return {"no_key": "RentCast not configured", "quota": "RentCast monthly limit reached — free sources used",
            "not_found": "RentCast had no estimate for this address", None: "not requested"}.get(s, f"RentCast unavailable ({s})")


def property_html(r, lang="both"):
    f, fs = r["facts"], r["fact_sources"]
    parts = [_open(f"BellaZu Home Report: {H.escape(r['address'])}", lang),
             f"<h1>{bk('prop_title')}</h1><div><b>{H.escape(r['address'])}</b></div><div class='small'>{bk('generated')}: {r['generated']} ET · BellaZu v0.1</div>",
             f"<h2>{bk('bottom_line')}</h2><ul>" + "".join(f"<li>{bi(H.escape(a), H.escape(b), 'div')}</li>" for a, b in property_bullets(r)) + "</ul>"]
    if r["warnings"]:
        parts.append("<div class='box'><b>" + bk("warnings") + "</b><ul>" + "".join(f"<li>{H.escape(w)}</li>" for w in r["warnings"]) + "</ul></div>")
    rows = []
    for k in ["price", "beds", "baths", "sqft", "hoa_monthly", "taxes_annual", "ownership", "hoa_includes", "status", "year_built"]:
        v = f.get(k)
        if k in ("price", "hoa_monthly", "taxes_annual") and v:
            v = money(float(v))
        if isinstance(v, list):
            v = ", ".join(v)
        rows.append([bk(k), H.escape(str(v)) if v not in (None, "") else "<i>unknown / desconocido</i>", _src_link(fs.get(k))])
    parts.append(f"<h2>{bk('facts')}</h2>" + _table([bk("field"), bk("value"), bk("source")], rows))
    bp = r.get("building_policy")
    parts.append(f"<h2>{bk('building_policy')}</h2>" + (f"<p>{bi(H.escape(bp.get('en','')), H.escape(bp.get('es','')))}<br><span class='small'>{_src_link(bp.get('source'))}</span></p>" if bp else
                 "<p>" + bi("Not found in free sources. Ask the listing agent for the co-op/condo house rules: sublet policy, roommate/boarder rules, minimum lease, board approval, flip tax.",
                           "No encontrado en fuentes gratuitas. Pida al agente las reglas de la co-op/condominio: subarriendo, compañeros de cuarto, plazo mínimo, aprobación de la junta, 'flip tax'.") + "</p>"))
    sr = r["str_rules"]
    cls = "bad" if not sr.get("str_legal_for_owner") else "ok"
    parts.append(f"<h2>{bk('legality')}</h2><div class='box {cls}'>{bi(H.escape(sr.get('summary_en','')), H.escape(sr.get('summary_es','')))}<div class='small'>Sources: " + "; ".join(_rule_src(x) for x in sr.get("sources", [])) + f" · verified {sr.get('last_verified')}</div></div>")
    fh = r.get("fha") or {}
    if fh.get("note_en"):
        parts.append(f"<h2>{bk('fha')}</h2><p>{bi(H.escape(fh['note_en']), H.escape(fh['note_es']))}</p>")
    # LTR
    le = r["ltr"]["estimate"]
    parts.append(f"<h2>{bk('ltr')}</h2>")
    if le.get("ok"):
        parts.append(f"<p><b>{money(le['median'])}</b>/mo · {bk('range')}: {money(le['p25'])}–{money(le['p75'])} · n={le['n']} · ≤{le['radius_km']} km</p>")
    rows = [[H.escape(c["source"]), H.escape(str(c.get("title") or ""))[:48], money(c["price"]), int(c["beds"]) if c.get("beds") is not None else "", int(c["sqft"]) if isinstance(c.get("sqft"), (int, float)) and c.get("sqft") == c.get("sqft") else (c.get("sqft") or ""), f"{c['dist_km']:.1f} km", f"<a href='{safe_url(c.get('url'))}'>link</a>"] for c in r["ltr"]["comps"][:10]]
    if rows:
        parts.append(_table(["Source", "Listing", "Rent", "Bd", "Sqft", "Dist", ""], rows, (2, 3, 4, 5)))
    rc = r.get("rent_compare") or {}
    if rc:
        crow = [[bi("Free-source comps (Craigslist/Rent.com/Redfin)", "Comparables gratuitos (Craigslist/Rent.com/Redfin)"), money(rc.get("free_median")), rc.get("free_n") or 0, "✅" if rc.get("chosen") == "free" else ""],
                [bi("RentCast rent estimate (AVM)", "Estimado de renta RentCast (AVM)"), (money(rc.get("rentcast_rent")) + (f" <span class='small'>({money(rc.get('rentcast_low'))}–{money(rc.get('rentcast_high'))})</span>" if rc.get("rentcast_low") else "")) if rc.get("rentcast_ok") else f"<i>{H.escape(_rc_status_text(rc.get('rentcast_status')))}</i>", rc.get("rentcast_n") or 0, "✅" if rc.get("chosen") == "rentcast" else ""]]
        if rc.get("chosen") == "hud_safmr":
            crow.append([bi("HUD Small Area FMR (fallback)", "HUD Small Area FMR (respaldo)"), money((r["benchmarks"].get("hud_safmr") or {}).get(f"{min(int(f.get('beds') or 2), 4)}br")), "—", "✅"])
        parts.append(_table([bi("Estimate", "Estimado"), bi("Rent/mo", "Renta/mes"), bi("Comps", "Comparables"), bi("Used", "Usado")], crow, (1, 2)))
        if rc.get("big_gap"):
            parts.append(f"<div class='box bad'>{bi(H.escape(rc.get('note_en', '')), H.escape(rc.get('note_es', '')))}</div>")
        parts.append("<p class='small'>" + bi("BellaZu uses the estimate built on more comparable listings.", "BellaZu usa el estimado con más anuncios comparables.") + "</p>")
    rcc = (r.get("rentcast") or {}).get("avm_comps") or []
    if rcc:
        rows = [[H.escape(str(c.get("title") or ""))[:48], money(c.get("price")), int(c["beds"]) if c.get("beds") is not None else "", c.get("sqft") or "", f"{c.get('dist_km') or 0:.1f} km", c.get("days_old") if c.get("days_old") is not None else "", f"<a href='{safe_url(c.get('url'))}'>map</a>"] for c in rcc[:10]]
        parts.append("<p><b>" + bi("RentCast comparables", "Comparables de RentCast") + "</b></p>" + _table(["Address", "Rent", "Bd", "Sqft", "Dist", "Days old", ""], rows, (1, 2, 3, 4, 5)))
    b = r["benchmarks"]
    beds = min(int(f.get("beds") or 2), 4)
    bl = []
    if b.get("hud_safmr"):
        bl.append(f"HUD FY2026 Small Area FMR ZIP {b['hud_safmr']['zip']}, {beds}BR: <b>{money(b['hud_safmr'][f'{beds}br'])}</b> (40th pct gross rent)")
    if b.get("acs_median_gross_rent"):
        a = b["acs_median_gross_rent"]
        bl.append(f"Census {a.get('release')} median gross rent ZIP {r['zip']}, {beds}BR: <b>{money(a.get(f'{beds}br'))}</b> (all tenants, lags market)")
    if b.get("rentcast_avm"):
        bl.append(f"RentCast AVM: <b>{money(b['rentcast_avm'].get('rent'))}</b>")
    parts.append(f"<p class='small'><b>{bk('benchmarks')}:</b> " + " · ".join(bl) + "</p>")
    ro = r["rooms"]
    if ro.get("ok"):
        parts.append(f"<h2>{bk('rooms')}</h2><p>{money(ro['median'])}/mo {bk('median')} · {money(ro['p25'])}–{money(ro['p75'])} · n={ro['n']} (Craigslist rooms & shares) <span class='small'>{H.escape(ro.get('note',''))}</span></p>")
    # STR
    st = r["str"]
    parts.append(f"<h2>{bk('str')}</h2>")
    if st.get("ok"):
        s = st["summary"]
        parts.append(f"<p>n={s['n']} active entire-home listings ≤{st['radius_km']} km (bedrooms rule: {st['bed_rule']}) · datasets: {', '.join(st['datasets'])}<br>"
                     f"Nightly (listed) {bk('median')}: <b>{money(s['adr_median'])}</b> · occupancy (SF model): <b>{pct(s['occ_median_sf_model'])}</b> · revenue/yr: <b>{money(s['revenue_median'])}</b> ({money(s['revenue_p25'])}–{money(s['revenue_p75'])})</p>")
        rows = [[H.escape(str(c.get("neighbourhood_cleansed"))), int(c["bedrooms"]) if c.get("bedrooms") is not None else "", money(c.get("price_num")), c.get("estimated_occupancy_l365d"), money(c.get("estimated_revenue_l365d")), f"{c['dist_km']:.1f}", f"<a href='{safe_url(c.get('listing_url'))}'>airbnb</a>"] for c in st["comps"][:8]]
        parts.append(_table(["Area", "Bd", "Nightly", "Nights/yr", "Rev/yr", "km", ""], rows, (1, 2, 3, 4, 5)))
        parts.append("<p class='small'>" + bi("Method: Inside Airbnb 'San Francisco model' — booked nights = reviews in last 12 months ÷ 50% review rate × max(3, minimum nights), capped at 70%. Price is the listed nightly price for one quoted date window (not realized ADR), excludes cleaning fees.",
                                              "Método: modelo 'San Francisco' de Inside Airbnb — noches reservadas = reseñas de 12 meses ÷ 50% × max(3, noches mínimas), tope 70%. El precio es el precio listado para una fecha (no el ADR real), sin tarifa de limpieza.") + "</p>")
    # scenarios
    sc = r["scenarios"]
    keys = []
    for s in sc:
        for k in (s.get("costs") or {}):
            if k not in keys:
                keys.append(k)
    head = [""] + [bi(H.escape(s["label_en"]), H.escape(s["label_es"])) for s in sc]
    rows = []
    rows.append(["<b>Income / Ingreso</b>"] + [money(sum((s.get("income") or {}).values())) if s.get("income") else (money(s.get("revenue_monthly")) if s.get("revenue_monthly") else (money(s["revenue_annual"] / 12) if s.get("revenue_annual") else "")) for s in sc])
    for k in keys:
        rows.append([bk(k)] + [("-" + money(s["costs"][k])) if s.get("costs") and s["costs"].get(k) else ("" if s.get("legal") else "") for s in sc])
    rows.append([f"<b>{bk('net')}</b>"] + [f"<span class='{'neg' if s['net_monthly'] < 0 else 'pos'}'>{money(s['net_monthly'])}</span>" if s.get("net_monthly") is not None else f"<i>{bk('not_legal')}</i>" for s in sc])
    rows.append([bk("cash_to_close")] + [money(s["loan"]["cash_to_close_est"]) if s.get("loan") else "" for s in sc])
    rows.append(["Rate / Tasa"] + [f"{s['loan']['rate_pct']:.2f}% · {money(s['loan']['down_payment'])} down" if s.get("loan") else "" for s in sc])
    parts.append(f"<h2>{bk('scen')}</h2>" + _table(head, rows, tuple(range(1, len(sc) + 1))))
    cav = [bi(H.escape(s.get("caveat_en", "")), H.escape(s.get("caveat_es", ""))) for s in sc if s.get("caveat_en")]
    cav += [bi(H.escape(s.get("dti_note_en", "")), H.escape(s.get("dti_note_es", ""))) for s in sc if s.get("dti_note_en")]
    parts.append("<ul class='small'>" + "".join(f"<li>{c}</li>" for c in cav) + "</ul>")
    parts.append(_assump_html(r))
    parts.append(_sources_html(r))
    parts.append(f"<p class='small'>{bk('disclaimer')}</p>{JS}</body></html>")
    return plainify("\n".join(parts))


def _assump_html(r):
    A, rt = r["assumptions"], r.get("rates") or {}
    items = []
    if rt:
        items.append(f"30-yr base rate {rt['base']:.2f}% ({H.escape(rt['source'])}); investment +{A['financing']['investment_rate_adjust']:.2f}")
    fi = A["financing"]
    items.append(f"FHA {fi['fha_down_pct']:.1%} down, UFMIP {fi['fha_upfront_mip_pct']:.2%}, annual MIP {fi['fha_annual_mip_pct']:.2%}; owner conventional/co-op {fi['owner_conv_down_pct']:.0%} down; investment {fi['investment_down_pct']:.0%} down; closing {fi['closing_cost_pct']:.0%}")
    s = A["str"]
    items.append(f"STR: platform {s['platform_fee_pct']:.0%}, avg stay {s['avg_stay_nights']} nights, cleaning by beds {s['cleaning_cost_per_turn_by_beds']}, supplies ${s['supplies_per_booked_night']}/night, insurance ${s['insurance_monthly']}/mo, furniture {s['furnishing_cost_by_beds']} over {s['furnishing_amortization_months']} mo, repairs {s['repairs_pct_of_revenue']:.0%}")
    items.append(f"MTR occupancy {A['mtr']['occupancy']:.0%} (assumption), LTR vacancy {A['ownership_costs']['vacancy_pct_ltr']:.0%}")
    return f"<h2>{bk('assump')}</h2><ul class='small'>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def _sources_html(r):
    seen, rows = set(), []
    for s in r.get("sources_status", []):
        k = (s["source"], s["ok"])
        if k in seen:
            continue
        seen.add(k)
        rows.append([H.escape(s["source"]), "✅" if s["ok"] else "❌", H.escape(str(s.get("http") or "")) + " " + H.escape(s.get("note") or ""), _src_link(s["url"])])
    return f"<h2>{bk('sources')}</h2>" + _table(["Source", "OK", "Status", "URL"], rows)


def property_md(r, lang):
    L = lambda k: t(k, lang)
    f, fs = r["facts"], r["fact_sources"]
    m = [f"# {L('prop_title')}", f"**{r['address']}** — {L('generated')} {r['generated']} ET", "", f"## {L('bottom_line')}"]
    m += [f"- {a if lang == 'en' else b}" for a, b in property_bullets(r)]
    if r["warnings"]:
        m += ["", f"**{L('warnings')}:**"] + [f"- {w}" for w in r["warnings"]]
    m += ["", f"## {L('facts')}", f"| {L('field')} | {L('value')} | {L('source')} |", "|---|---|---|"]
    for k in ["price", "beds", "baths", "sqft", "hoa_monthly", "taxes_annual", "ownership", "hoa_includes"]:
        v = f.get(k)
        v = ", ".join(v) if isinstance(v, list) else v
        if k in ("price", "hoa_monthly", "taxes_annual") and v:
            v = money(float(v))
        m.append(f"| {L(k)} | {v if v not in (None, '') else '—'} | {fs.get(k, '')} |")
    sr = r["str_rules"]
    m += ["", f"## {L('legality')}", sr.get("summary_en" if lang == "en" else "summary_es", ""), "Sources: " + "; ".join(sr.get("sources", []))]
    le = r["ltr"]["estimate"]
    m += ["", f"## {L('ltr')}"]
    if le.get("ok"):
        m.append(f"**{money(le['median'])}**/mo ({money(le['p25'])}–{money(le['p75'])}, n={le['n']})")
        m += ["", "| Source | Listing | Rent | Bd | km |", "|---|---|---|---|---|"] + [f"| {c['source']} | {str(c.get('title'))[:40]} | {money(c['price'])} | {int(c['beds']) if c.get('beds') is not None else ''} | {c['dist_km']:.1f} |" for c in r["ltr"]["comps"][:8]]
    st = r["str"]
    if st.get("ok"):
        s = st["summary"]
        m += ["", f"## {L('str')}", f"n={s['n']} · ADR {money(s['adr_median'])} · occ {pct(s['occ_median_sf_model'])} · rev {money(s['revenue_median'])}/yr · datasets {', '.join(st['datasets'])}"]
    m += ["", f"## {L('scen')}", "| | " + " | ".join(s["label_en" if lang == "en" else "label_es"] for s in r["scenarios"]) + " |", "|---" * (len(r["scenarios"]) + 1) + "|"]
    m.append(f"| **{L('net')}** | " + " | ".join(money(s["net_monthly"]) if s.get("net_monthly") is not None else L("not_legal") for s in r["scenarios"]) + " |")
    m.append(f"| {L('total_cost')} | " + " | ".join(money(s.get("total_cost")) for s in r["scenarios"]) + " |")
    m += ["", f"_{L('disclaimer')}_"]
    return "\n".join(m)


# ------------------------------------------------------------------ arbitrage
def arb_bullets(r):
    sr, s = r["str_rules"], r["summary"]
    out = []
    if not sr.get("str_legal_for_tenant"):
        out.append((f"LEGALITY: tenant-operated Airbnb (rental arbitrage) is NOT legal in {r['town']} ({sr.get('status')}). The STR ranking below is for education only. {sr.get('summary_en','')}",
                    f"LEGALIDAD: el Airbnb operado por inquilinos (arbitraje) NO es legal en {r['town']} ({sr.get('status')}). La clasificación STR es solo educativa. {sr.get('summary_es','')}"))
    out.append((f"Scored {r['n_listings_scored']} of {r['n_listings_fetched']} fetched 1–3BR rentals. Median asking rent {money(s['median_rent'])}. Median estimated STR profit {money(s['median_str_profit'])}/mo; {pct(s['share_str_profitable'])} show a positive STR profit.",
                f"Se evaluaron {r['n_listings_scored']} de {r['n_listings_fetched']} alquileres de 1–3 hab. Renta mediana {money(s['median_rent'])}. Ganancia STR estimada mediana {money(s['median_str_profit'])}/mes; {pct(s['share_str_profitable'])} con ganancia positiva."))
    out.append((f"Legal alternative (30+ night furnished rentals, landlord permission required): median {money(s['median_mtr_profit'])}/mo; {pct(s['share_mtr_profitable'])} positive.",
                f"Alternativa legal (amueblado 30+ noches, con permiso del dueño): mediana {money(s['median_mtr_profit'])}/mes; {pct(s['share_mtr_profitable'])} positivos."))
    if not r.get("iab_covers_town"):
        out.append((f"No Inside Airbnb dataset covers {r['town']}; STR estimates use nearby datasets {', '.join(r['iab_datasets'])} as a proxy.",
                    f"No hay datos de Inside Airbnb para {r['town']}; se usan datos cercanos como aproximación."))
    return out


ARB_COLS = ["rank", "source", "title", "beds", "rent", "adr_median", "occ_sf_model", "str_revenue_annual", "str_profit_monthly", "mtr_profit_monthly", "legality_flag", "check_flag", "url"]


def arb_html(r, top=25, lang="both"):
    parts = [_open(f"BellaZu Rental Finder: {H.escape(r['town'])}", lang),
             f"<h1>{bk('arb_title')}: {H.escape(r['town'])}, {r['state'].upper()}</h1><div class='small'>{bk('generated')}: {r['generated']} ET · BellaZu v0.1</div>",
             f"<h2>{bk('bottom_line')}</h2><ul>" + "".join(f"<li>{bi(H.escape(a), H.escape(b), 'div')}</li>" for a, b in arb_bullets(r)) + "</ul>"]
    sr = r["str_rules"]
    parts.append(f"<div class='box {'bad' if not sr.get('str_legal_for_tenant') else 'ok'}'><b>{bk('legality')}</b><br>{bi(H.escape(sr.get('summary_en','')), H.escape(sr.get('summary_es','')))}<div class='small'>" + "; ".join(_rule_src(x) for x in sr.get("sources", [])) + f" · verified {sr.get('last_verified')}</div></div>")
    rows = [[b["beds"], b["n"], money(b["rent"]), money(b["str_rev"]), money(b["str_profit"]), money(b["mtr_profit"])] for b in r["summary"]["by_beds"]]
    parts.append(f"<h2>{bk('by_beds')}</h2>" + _table(["Bd", "n", "Median rent", "STR rev/yr", "STR profit/mo", "30+night profit/mo"], rows, (0, 1, 2, 3, 4, 5)))
    rows = []
    for x in r["results"][:top]:
        rows.append([x["rank"], H.escape(x["source"]), H.escape(str(x["title"]))[:40] + (" ⚠️" if x.get("check_flag") else ""), x["beds"], money(x["rent"]), money(x["adr_median"]), pct(x["occ_sf_model"]),
                     money(x["str_revenue_annual"]), f"<span class='{'neg' if x['str_profit_monthly'] < 0 else 'pos'}'>{money(x['str_profit_monthly'])}</span>",
                     f"<span class='{'neg' if x['mtr_profit_monthly'] < 0 else 'pos'}'>{money(x['mtr_profit_monthly'])}</span>", f"<a href='{safe_url(x.get('url'))}'>link</a>"])
    sb = r.get("sorted_by")
    rk = bi("Rentals ranked by estimated 30+ night (furnished, mid-term) profit — the legal option here", "Alquileres ordenados por ganancia estimada de 30+ noches (amueblado, mediano plazo) — la opción legal aquí") if sb == "mtr_profit_monthly" else bk("ranked")
    parts.append(f"<h2>{rk} (top {top})</h2>" + _table(["#", "Src", "Listing", "Bd", "Rent", "ADR", "Occ", "STR rev/yr", "STR profit/mo", "30+n profit/mo", ""], rows, (0, 3, 4, 5, 6, 7, 8, 9)))
    parts.append("<p class='small'>" + bi("STR profit = STR revenue/12 − rent − platform fees − cleaning − supplies − utilities − STR insurance − furniture (amortized) − repairs. ⚠️ = rent far below area median: verify listing (possible scam, room-only, or typo). Full list in the XLSX/CSV.",
                                          "Ganancia STR = ingreso STR/12 − renta − comisiones − limpieza − suministros − servicios − seguro STR − muebles (amortizados) − reparaciones. ⚠️ = renta muy por debajo de la mediana: verificar anuncio. Lista completa en XLSX/CSV.") + "</p>")
    parts.append(f"<h2>{bk('caveats')}</h2><ul class='small'>" + "".join(f"<li>{bi(H.escape(a), H.escape(b))}</li>" for a, b in zip(r["caveats_en"], r["caveats_es"])) + "</ul>")
    parts.append(_assump_html(r))
    parts.append(_sources_html(r))
    parts.append(f"<p class='small'>{bk('disclaimer')}</p>{JS}</body></html>")
    return plainify("\n".join(parts))


def arb_md(r, lang, top=15):
    L = lambda k: t(k, lang)
    m = [f"# {L('arb_title')}: {r['town']}, {r['state'].upper()}", f"{L('generated')} {r['generated']} ET", "", f"## {L('bottom_line')}"]
    m += [f"- {a if lang == 'en' else b}" for a, b in arb_bullets(r)]
    m += ["", f"## {L('ranked')}", "| # | Listing | Bd | Rent | STR rev/yr | STR profit/mo | 30+n profit/mo |", "|---|---|---|---|---|---|---|"]
    for x in r["results"][:top]:
        m.append(f"| {x['rank']} | [{str(x['title'])[:35]}]({x['url']}) | {x['beds']} | {money(x['rent'])} | {money(x['str_revenue_annual'])} | {money(x['str_profit_monthly'])} | {money(x['mtr_profit_monthly'])} |")
    m += ["", f"_{L('disclaimer')}_"]
    return "\n".join(m)


# ------------------------------------------------------------------ writers
def _flat_assumptions(A):
    rows = []
    for sect, vals in A.items():
        for k, v in vals.items():
            rows.append({"section": sect, "key": k, "value": json.dumps(v) if isinstance(v, (dict, list)) else v})
    return pd.DataFrame(rows)


def _style_xlsx(path):
    """Report look for the spreadsheet: ink header row with rose text, frozen header, readable widths, plain wording (values unchanged)."""
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = load_workbook(path)
    head_fill, head_font = PatternFill("solid", fgColor="141414"), Font(bold=True, color="FFD3DE", name="Calibri")
    for ws in wb.worksheets:
        ws.sheet_properties.tabColor = "D8567C"
        ws.freeze_panes = "A2"
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str):
                    c.value = _plain_text(c.value)
        for c in ws[1]:
            c.fill, c.font = head_fill, head_font
            c.alignment = Alignment(vertical="center", wrap_text=True)
            if isinstance(c.value, str):
                c.value = c.value.replace("_", " ").capitalize()
        for col in ws.columns:
            w = max((len(str(c.value)) for c in col[:200] if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 60)
    wb.save(path)


def write_property(r, outdir):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / f"BellaZu_Property_Report_{slug(r['address'])}_{r['generated'][:10]}"
    files = {}
    (p := base.with_suffix(".html")).write_text(property_html(r)); files["html"] = str(p)
    (p := base.with_suffix(".md")).write_text(property_md(r, "en") + "\n\n---\n\n" + property_md(r, "es")); files["md"] = str(p)
    (p := base.with_suffix(".json")).write_text(json.dumps(r, indent=1, default=str)); files["json"] = str(p)
    sc_rows = []
    for s in r["scenarios"]:
        row = {"scenario_en": s["label_en"], "scenario_es": s["label_es"], "legal": s.get("legal"), "net_monthly": s.get("net_monthly"), "total_cost": s.get("total_cost")}
        row.update({f"cost_{k}": v for k, v in (s.get("costs") or {}).items()})
        row.update({f"income_{k}": v for k, v in (s.get("income") or {}).items()})
        if s.get("loan"): row.update({f"loan_{k}": v for k, v in s["loan"].items()})
        sc_rows.append(row)
    sc = pd.DataFrame(sc_rows)
    (p := base.with_name(base.name + "_scenarios.csv")); sc.to_csv(p, index=False); files["csv"] = str(p)
    p = base.with_suffix(".xlsx")
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        facts = pd.DataFrame([{"field": k, "value": (", ".join(v) if isinstance(v, list) else v), "source": r["fact_sources"].get(k, "")} for k, v in r["facts"].items() if k != "description"])
        facts.to_excel(w, sheet_name="Facts", index=False)
        sc.to_excel(w, sheet_name="Monthly numbers", index=False)
        pd.DataFrame(r["ltr"]["comps"]).to_excel(w, sheet_name="Rentals nearby", index=False)
        pd.DataFrame([{k: v for k, v in (r.get("rent_compare") or {}).items()}]).to_excel(w, sheet_name="Rent estimates", index=False)
        pd.DataFrame((r.get("rentcast") or {}).get("avm_comps") or []).to_excel(w, sheet_name="RentCast examples", index=False)
        pd.DataFrame(r["rooms"].get("comps", [])).to_excel(w, sheet_name="Rooms nearby", index=False)
        pd.DataFrame(r["str"].get("comps", [])).to_excel(w, sheet_name="Airbnb nearby", index=False)
        pd.DataFrame(r["mtr"].get("comps", [])).to_excel(w, sheet_name="30+ night nearby", index=False)
        bm = r["benchmarks"]
        pd.DataFrame([{"benchmark": k, **(v if isinstance(v, dict) else {})} for k, v in bm.items() if v]).to_excel(w, sheet_name="Reference rents", index=False)
        pd.DataFrame([{"field": k, "value": str(v)} for k, v in r["str_rules"].items()]).to_excel(w, sheet_name="Airbnb rules", index=False)
        pd.DataFrame(r["sources_status"]).to_excel(w, sheet_name="Data sources", index=False)
        _flat_assumptions(r["assumptions"]).to_excel(w, sheet_name="Our estimates", index=False)
    _style_xlsx(p)
    files["xlsx"] = str(p)
    return files


def write_arbitrage(r, outdir):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / f"BellaZu_Arbitrage_Scan_{slug(r['town'])}_{r['state'].upper()}_{r['generated'][:10]}"
    files = {}
    (p := base.with_suffix(".html")).write_text(arb_html(r)); files["html"] = str(p)
    (p := base.with_suffix(".md")).write_text(arb_md(r, "en") + "\n\n---\n\n" + arb_md(r, "es")); files["md"] = str(p)
    (p := base.with_suffix(".json")).write_text(json.dumps(r, indent=1, default=str)); files["json"] = str(p)
    df = pd.DataFrame(r["results"])
    (p := base.with_suffix(".csv")); df.to_csv(p, index=False); files["csv"] = str(p)
    p = base.with_suffix(".xlsx")
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Rentals ranked", index=False)
        pd.DataFrame(r["summary"]["by_beds"]).to_excel(w, sheet_name="By bedrooms", index=False)
        pd.DataFrame([{"field": k, "value": str(v)} for k, v in r["str_rules"].items()]).to_excel(w, sheet_name="Airbnb rules", index=False)
        pd.DataFrame(r["sources_used"]).to_excel(w, sheet_name="Sources used", index=False)
        pd.DataFrame(r["sources_status"]).to_excel(w, sheet_name="Data log", index=False)
        _flat_assumptions(r["assumptions"]).to_excel(w, sheet_name="Our estimates", index=False)
    _style_xlsx(p)
    files["xlsx"] = str(p)
    return files
