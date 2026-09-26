"""BellaZu web app (Streamlit). Simple phone-first UI, English/Spanish, passcode-gated.
Run locally:  APP_PASSCODE=... streamlit run app.py   (or put the values in .streamlit/secrets.toml)
Secrets (st.secrets first, then environment variables):
  APP_PASSCODE (required), RENTCAST_API_KEY (optional), RENTCAST_MONTHLY_CAP / RENTCAST_USED_OFFSET (optional).
Nothing personal lives in this file: every number is typed by the user and kept only in the browser session."""
import hmac, html as H, json, os, pathlib, re, sys, tempfile, time
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def secret(name, default=""):
    """st.secrets first (Streamlit Community Cloud), then os.environ."""
    v = None
    try:
        v = st.secrets.get(name)
    except Exception:          # no secrets.toml -> fine, fall back to the environment
        v = None
    if v in (None, ""):
        v = os.environ.get(name, default)
    return str(v).strip() if v is not None else default


for _k in ("RENTCAST_API_KEY", "RENTCAST_MONTHLY_CAP", "RENTCAST_USED_OFFSET"):   # the engine reads these from os.environ
    _v = secret(_k)
    if _v and not os.environ.get(_k):
        os.environ[_k] = _v

from bellazu import analyze_property, scan_arbitrage          # noqa: E402
from bellazu.render import property_html, arb_html, write_property, write_arbitrage  # noqa: E402
from bellazu.sources import rentcast                          # noqa: E402
from bellazu import simple as S                               # noqa: E402
from bellazu.simple import money                              # noqa: E402

st.set_page_config(page_title="BellaZu", page_icon="🏡", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""<style>
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {display:none !important}
.block-container {padding-top:1.3rem; padding-bottom:4rem; max-width:640px}
input {font-size:16px !important}
.stButton button, .stDownloadButton button, .stFormSubmitButton button {min-height:3.2rem; font-size:1.08rem; font-weight:600; border-radius:999px}
[data-testid="stExpander"] details {border-radius:16px; border-color:#F3D9E0; background:#FFFFFF}
.bz-brand {font-size:2.05rem; font-weight:800; color:#C2466B; letter-spacing:-.4px; line-height:1.1}
.bz-sub {color:#7A6570; font-size:1rem; margin:.15rem 0 1rem; line-height:1.45}
.bz-hello {font-size:1.35rem; font-weight:700; color:#3A2E35; margin:.4rem 0 .2rem}
.bz-addr {font-size:1.02rem; font-weight:600; color:#3A2E35; margin:.2rem 0 .4rem}
.bz-card, .bz-tile, .bz-verdict, .bz-how, .bz-line {box-shadow:0 2px 10px rgba(194,70,107,.08)}
.bz-verdict {border-radius:20px; padding:1rem 1.1rem; margin:.3rem 0 1rem}
.bz-verdict .big {font-size:1.7rem; font-weight:800; line-height:1.15}
.bz-verdict .head {font-size:1.12rem; font-weight:700; margin-top:.35rem; line-height:1.35}
.bz-verdict .why {font-size:1.05rem; margin-top:.25rem; line-height:1.4}
.bz-verdict .next {font-size:.98rem; margin-top:.6rem; padding-top:.55rem; border-top:1px dashed rgba(0,0,0,.15); line-height:1.4}
.bz-good {background:#E6F4EC; color:#1E5E3A} .bz-maybe {background:#FFF1DA; color:#6E4A00} .bz-skip {background:#FBE6EC; color:#8E2B4B}
.bz-tiles {display:grid; grid-template-columns:1fr 1fr; gap:.7rem; margin:.2rem 0 1rem}
.bz-tile {background:#FFFFFF; border:1px solid #F3D9E0; border-radius:18px; padding:.75rem .85rem}
.bz-tile .lbl {font-size:.88rem; color:#7A6570}
.bz-tile .num {font-size:1.5rem; font-weight:800; color:#3A2E35; line-height:1.25}
.bz-tile .sub {font-size:.8rem; color:#7A6570; line-height:1.3}
.bz-tile details {margin-top:.35rem; font-size:.8rem; color:#6B5A63}
.bz-tile summary {color:#C2466B; cursor:pointer; font-weight:600; list-style:none}
.bz-tile summary::-webkit-details-marker {display:none}
.bz-tile details p {margin:.25rem 0 0; line-height:1.35}
.bz-line {font-size:1.02rem; padding:.75rem .9rem; border-radius:16px; background:#F1ECFA; margin:.2rem 0 1rem; line-height:1.4}
.bz-how {background:#FFFFFF; border:1px solid #F3D9E0; border-radius:20px; padding:.9rem 1rem; margin:.3rem 0 1rem}
.bz-how .step {display:flex; gap:.7rem; align-items:center; margin:.45rem 0; font-size:1rem; line-height:1.35}
.bz-how .n {flex:0 0 2rem; height:2rem; border-radius:50%; background:#FBE6EC; color:#C2466B; font-weight:800; display:flex; align-items:center; justify-content:center}
.bz-card {background:#FFFFFF; border:1px solid #F3D9E0; border-radius:18px; padding:.8rem .9rem; margin:.55rem 0}
.bz-card .t {font-weight:600; color:#3A2E35; line-height:1.3}
.bz-card .m {margin:.25rem 0; font-size:1rem}
.bz-card a {color:#C2466B; font-weight:600}
.bz-small {font-size:.85rem; color:#7A6570}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ language helpers
def ES():
    return st.session_state.get("lang", "EN") == "ES"


def L(en, es):
    return es if ES() else en


def P(pair):
    return pair[1] if ES() else pair[0]


def html(s):
    st.markdown(s.replace("$", "&#36;"), unsafe_allow_html=True)


def md(s):
    st.markdown(s.replace("$", "\\$"))


def header():
    top = st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute")
    top.markdown("<div class='bz-brand'>🏡 BellaZu</div>", unsafe_allow_html=True)
    top.segmented_control("Language / Idioma", ["EN", "ES"], key="lang", default="EN", required=True, label_visibility="collapsed")


# ------------------------------------------------------------------ passcode gate
def gate():
    header()
    st.markdown("<div class='bz-hello'>Welcome to BellaZu 💕<br>Bienvenida a BellaZu 💕</div>"
                "<div class='bz-sub'>Your friendly helper for buying your first home. Type your passcode to come in.<br>"
                "Su guía amiga para comprar su primera casa. Escriba su código para entrar.</div>", unsafe_allow_html=True)
    pc = secret("APP_PASSCODE").lower()
    if not pc:
        st.error("This app is not set up yet (missing APP_PASSCODE). / La app aún no está configurada (falta APP_PASSCODE).")
        st.stop()
    n = st.session_state.get("fails", 0)
    if n >= 15:
        st.error("Too many tries. Reload the page later. / Demasiados intentos. Recargue la página más tarde.")
        st.stop()
    with st.form("gate"):
        typed = st.text_input("Passcode / Código", type="password")
        ok = st.form_submit_button("Enter / Entrar", type="primary", width="stretch")
    if ok:
        if hmac.compare_digest(typed.strip().lower().encode(), pc.encode()):
            st.session_state.authed = True
            st.session_state.fails = 0
            st.rerun()
        else:
            st.session_state.fails = n + 1
            time.sleep(min(1 + n, 5))       # slow down guessing
            st.error("Hmm, that passcode didn't work. Try again 💕 / Ese código no funcionó. Intente otra vez 💕")
    st.stop()


if not st.session_state.get("authed"):
    gate()

header()
mode = st.segmented_control("Mode", ["home", "town"], key="mode", default="home", required=True, label_visibility="collapsed", width="stretch",
                            format_func=lambda k: L("🏠 Check a home", "🏠 Revisar una casa") if k == "home" else L("🔑 Find rentals in a town", "🔑 Buscar alquileres en un pueblo"))


# ------------------------------------------------------------------ shared bits
def xlsx_bytes(r, kind):
    with tempfile.TemporaryDirectory() as d:
        files = write_property(r, d) if kind == "property" else write_arbitrage(r, d)
        return pathlib.Path(files["xlsx"]).read_bytes(), pathlib.Path(files["xlsx"]).name


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:50]


def verdict_box(v):
    lvl = v["level"]
    if v.get("title_en"):      # town scan: the title is the rule itself
        big = f"{'🚫' if lvl == 'skip' else '❓'} {v['title_es'] if ES() else v['title_en']}"
        head = ""
    else:
        big = {"good": L("✨ Good deal", "✨ Buen negocio"), "maybe": L("🤔 Maybe", "🤔 Tal vez"), "skip": L("🌷 Skip", "🌷 Mejor no")}[lvl]
        head = {"good": L("Great news, this one could work!", "¡Buenas noticias, esta podría funcionar!"),
                "maybe": L("This one could work, but let's check a few things first.", "Esta podría funcionar, pero revisemos algunas cosas primero."),
                "skip": L("This one's not a fit, and here's why:", "Esta no le conviene, y le explicamos por qué:")}[lvl]
    nxt = v.get("next_es" if ES() else "next_en")
    html(f"<div class='bz-verdict bz-{lvl}'><div class='big'>{H.escape(big)}</div>"
         + (f"<div class='head'>{H.escape(head)}</div>" if head else "")
         + f"<div class='why'>{H.escape(v['es'] if ES() else v['en'])}</div>"
         + (f"<div class='next'>👉 <b>{L('What to do next:', 'Qué hacer ahora:')}</b> {H.escape(nxt)}</div>" if nxt else "") + "</div>")


def tiles(items):
    cells = "".join(f"<div class='bz-tile'><div class='lbl'>{H.escape(a)}</div><div class='num'>{H.escape(b)}</div><div class='sub'>{H.escape(c)}</div>"
                    + (f"<details><summary>{L('What does this mean?', '¿Qué significa?')}</summary><p>{H.escape(t[3])}</p></details>" if len(t) > 3 else "")
                    + "</div>" for t in items for a, b, c in [t[:3]])
    html(f"<div class='bz-tiles'>{cells}</div>")


def rc_usage_line():
    u = rentcast.usage()
    if not u["enabled"]:
        return L("RentCast is off, so only free sources are used.", "RentCast está apagado; solo se usan fuentes gratuitas.")
    s = L(f"RentCast lookups used this month: {u['used']} of {u['free_plan']} (this app's own count).",
          f"Consultas de RentCast usadas este mes: {u['used']} de {u['free_plan']} (conteo de esta app).")
    if u["used"] >= u["cap"]:
        s += " " + L("Monthly limit reached, so free sources are used until next month.", "Se alcanzó el límite mensual; se usan fuentes gratuitas hasta el próximo mes.")
    return s


def addr_from_link(url):
    """Best-effort address from a Zillow/Redfin/Realtor URL slug (the page itself may be blocked)."""
    m = re.search(r"zillow\.com/homedetails/([^/]+)/", url) or re.search(r"redfin\.com/[A-Z]{2}/[^/]+/([^/]+)/", url) \
        or re.search(r"realtor\.com/realestateandhomes-detail/([^/]+)", url)
    if not m:
        return ""
    s = m.group(1).replace("-", " ")
    s = re.sub(r"\b(APT|UNIT)\b", lambda x: x.group(1).title(), s)
    s = re.sub(r"_M\d+.*$", "", s)
    s = re.sub(r"\s([A-Z]{2})\s(\d{5})$", r", \1 \2", s)
    return s


# ------------------------------------------------------------------ Check a home: result
COST_LBL = {"principal_interest": ("Mortgage payment (loan + interest)", "Pago de la hipoteca (préstamo + interés)"),
            "hoa_or_maintenance": ("Building fee (HOA / maintenance)", "Cuota del edificio (HOA / mantenimiento)"),
            "property_tax": ("Property tax", "Impuesto a la propiedad"), "insurance": ("Home insurance", "Seguro de la vivienda"),
            "utilities": ("Utilities (power, gas, internet)", "Servicios (luz, gas, internet)"),
            "repairs_reserve": ("Savings for repairs", "Ahorro para reparaciones")}
TYPE_LBL = {"co-op": ("Co-op", "Co-op"), "condo": ("Condo", "Condo"), "single-family": ("House", "Casa"), "multi-family": ("2 to 4 family", "Multifamiliar"),
            "townhouse": ("Townhouse", "Townhouse")}
INC_LBL = {"taxes": ("taxes", "impuestos"), "utilities": ("utilities", "servicios"), "internet": ("internet", "internet"), "heat/hot water": ("heat and hot water", "calefacción y agua caliente")}


def profit_txt(v):
    if v is None:
        return "?"
    return L(f"about {money(v)}/mo profit", f"unos {money(v)}/mes de ganancia") if v >= 0 else L(f"about {money(-v)}/mo loss", f"unos {money(-v)}/mes de pérdida")


def show_property(r):
    f = r.get("facts") or {}
    sc = S.scenarios(r)
    o = sc.get("owner_roommates")
    rent, rent_src = S.rent_used(r)
    own = (f.get("ownership") or "").lower()
    html(f"<div class='bz-addr'>📍 {H.escape(r['address'])}</div>")
    verdict_box(S.verdict_property(r))

    kind = P(TYPE_LBL.get(own, (own.title(), own.title()))) if own else ""
    beds = f.get("beds")
    price_sub = ", ".join(x for x in [kind, (L(f"{beds} bedrooms", f"{beds} habitaciones") if beds else "")] if x)
    if o:
        n = int(o.get("rooms_rented") or 0)
        cost_sub = L(f"{money(o['own_net_housing_cost'])} with {S.roommates_txt(n)[0]}", f"{money(o['own_net_housing_cost'])} con {S.roommates_txt(n)[1]}") if n else L("living there", "viviendo allí")
        ln = o["loan"]
        cash_sub = L(f"{money(ln['down_payment'])} down + {money(ln['closing_costs_est'])} fees", f"{money(ln['down_payment'])} inicial + {money(ln['closing_costs_est'])} de cierre")
    tiles([(L("Price", "Precio"), money(f.get("price")) if f.get("price") else "?", price_sub,
            L("The asking price of the home. You can often offer a bit less.", "El precio que piden por la casa. A veces se puede ofrecer un poco menos.")),
           (L("Your monthly cost", "Su costo mensual"), money(o["total_cost"]) if o else "?", cost_sub if o else L("add the price", "agregue el precio"),
            L("Everything you'd pay each month to live there: mortgage, building fee, insurance and more.", "Todo lo que pagaría cada mes para vivir allí: hipoteca, cuota del edificio, seguro y más.")),
           (L("Cash to close", "Dinero para cerrar"), money(o["loan"]["cash_to_close_est"]) if o else "?", cash_sub if o else "",
            L("The money you need on closing day, including the down payment and fees.", "El dinero que necesita el día del cierre, con el pago inicial y los gastos.")),
           (L("Rent it could earn", "Renta posible"), (money(rent) if rent else "?"), L("a month, renting the whole home", "al mes, alquilando toda la casa"),
            L("What a tenant would likely pay each month to rent the whole home.", "Lo que un inquilino probablemente pagaría al mes por toda la casa."))])
    icon, en, es = S.airbnb_line(r.get("str_rules") or {}, "owner")
    html(f"<div class='bz-line'>{icon} {H.escape(es if ES() else en)}</div>")
    st.download_button(L("⬇️ Download your full report", "⬇️ Descargar su reporte completo"), property_html(r).encode(),
                       f"BellaZu_Report_{safe_name(r['address'])}.html", "text/html", key="dl_prop", type="primary", width="stretch", on_click="ignore")
    with st.expander(L("See details", "Ver detalles")):
        property_details(r, f, sc, o, rent, rent_src, own)


def property_details(r, f, sc, o, rent, rent_src, own):
    A = r.get("assumptions") or {}
    fi = A.get("financing", {})
    # --- the home
    st.markdown(f"#### {L('🏡 The home', '🏡 La casa')}")
    inc = [P(INC_LBL.get(x, (x, x))) for x in (f.get("hoa_includes") or [])]
    lines = [L(f"Price: {money(f.get('price'))}", f"Precio: {money(f.get('price'))}") if f.get("price") else L("Price: unknown", "Precio: no se sabe"),
             L("Bedrooms", "Habitaciones") + f": {f.get('beds') or '?'}" + (" · " + L("Bathrooms", "Baños") + f": {f.get('baths')}" if f.get("baths") else ""),
             L("Building fee", "Cuota del edificio") + f": {money(f.get('hoa_monthly')) + L('/mo', '/mes') if f.get('hoa_monthly') else L('unknown', 'no se sabe')}"
             + (L(f" (includes {', '.join(inc)})", f" (incluye {', '.join(inc)})") if inc else "")]
    if f.get("taxes_annual"):
        lines.append(L("Property taxes", "Impuestos") + f": {money(f.get('taxes_annual'))}" + L("/year", "/año"))
    srcs = sorted({("you" if v == "user input" else (v.split("/")[2] if str(v).startswith("http") else v)) for v in (r.get("fact_sources") or {}).values()} - {"parsed from listing description"})
    lines.append(L("Where these came from: ", "De dónde salen: ") + ", ".join(L("what you typed", "lo que usted escribió") if s == "you" else s for s in srcs))
    md("\n".join(f"- {x}" for x in lines))

    # --- monthly costs
    if o:
        st.markdown(f"#### {L('💵 Your monthly cost if you live there', '💵 Su costo mensual si vive allí')}")
        c = o["costs"]
        fha = not ("co-op" in own and (r.get("fha") or {}).get("eligible") is False)
        mi_lbl = L("FHA insurance fee (required with a small down payment)", "Seguro FHA (obligatorio con poco pago inicial)") if fha else \
            L("Mortgage insurance (down payment under 20%)", "Seguro hipotecario (pago inicial menor al 20%)")
        rows = []
        for k in ["principal_interest", "mortgage_insurance", "hoa_or_maintenance", "property_tax", "insurance", "utilities", "repairs_reserve"]:
            v = c.get(k) or 0
            if k == "property_tax" and not v and "taxes" in (f.get("hoa_includes") or []):
                rows.append(f"- {P(COST_LBL[k])}: {L('included in building fee', 'incluido en la cuota')}")
            elif k == "utilities" and not v and "utilities" in (f.get("hoa_includes") or []):
                rows.append(f"- {P(COST_LBL[k])}: {L('included in building fee', 'incluido en la cuota')}")
            elif v:
                rows.append(f"- {mi_lbl if k == 'mortgage_insurance' else P(COST_LBL[k])}: {money(v)}")
        rows.append(f"- **{L('Total', 'Total')}: {money(o['total_cost'])}{L('/mo', '/mes')}**")
        md("\n".join(rows))
        ln = o["loan"]
        md(L(f"Cash to close: {money(ln['cash_to_close_est'])} = {money(ln['down_payment'])} down payment + about {money(ln['closing_costs_est'])} in closing costs. "
             f"Loan {money(ln['loan_amount'])} at {ln['rate_pct']:.2f}% for {fi.get('term_years', 30)} years.",
             f"Dinero para cerrar: {money(ln['cash_to_close_est'])} = {money(ln['down_payment'])} de pago inicial + unos {money(ln['closing_costs_est'])} de gastos de cierre. "
             f"Préstamo de {money(ln['loan_amount'])} al {ln['rate_pct']:.2f}% por {fi.get('term_years', 30)} años."))
        d = o.get("front_end_dti")
        if d is not None:
            md(L(f"Housing would take {d:.0%} of the income you entered. Lenders usually want this under about 31% to 43%. They normally don't count roommate rent.",
                 f"La vivienda se llevaría el {d:.0%} del ingreso que puso. Los prestamistas suelen querer menos de 31% a 43%. Normalmente no cuentan la renta de compañeros."))
        else:
            st.caption(L("Add your income under Add details to see if a lender would likely approve the payment.",
                         "Agregue su ingreso en Agregar detalles para ver si un prestamista aprobaría el pago."))

    # --- loan type
    fh = r.get("fha") or {}
    st.markdown(f"#### {L('🔑 Your loan', '🔑 Su préstamo')}")
    if fh.get("eligible") is False:
        md(L(f"FHA loans (the low down payment kind) almost never work for co-ops. This assumes a regular co-op loan with {fi.get('owner_conv_down_pct', .1):.0%} down. The co-op board must also approve you.",
             f"Los préstamos FHA (los de poco pago inicial) casi nunca sirven para co-ops. Esto asume un préstamo normal de co-op con {fi.get('owner_conv_down_pct', .1):.0%} inicial. La junta de la co-op también tiene que dar su aprobación."))
    elif "condo" in own:
        found = L("is on", "está en") if fh.get("eligible") else L("was not found on", "no apareció en")
        md(L(f"This assumes an FHA loan with {fi.get('fha_down_pct', .035):.1%} down. For FHA, the building must be on HUD's approved condo list. This building {found} the list we checked.",
             f"Esto asume un préstamo FHA con {fi.get('fha_down_pct', .035):.1%} inicial. Para FHA, el edificio debe estar en la lista de condos aprobados por HUD. Este edificio {found} la lista que revisamos."))
    else:
        md(L(f"This assumes an FHA loan with {fi.get('fha_down_pct', .035):.1%} down (the usual first-time buyer loan).",
             f"Esto asume un préstamo FHA con {fi.get('fha_down_pct', .035):.1%} inicial (el préstamo usual para primeros compradores)."))

    # --- roommates
    if o and o.get("rooms_rented"):
        st.markdown(f"#### {L('👭 Roommates', '👭 Compañeros de cuarto')}")
        ro = r.get("rooms") or {}
        basis = L(f"typical room rent nearby, from {ro.get('n')} Craigslist posts", f"renta típica de un cuarto cerca, de {ro.get('n')} anuncios de Craigslist") if ro.get("ok") \
            else L("an estimate based on the rent for the whole home", "un estimado según la renta de toda la casa")
        md(L(f"Renting {o['rooms_rented']} rooms at about {money(o['room_rent_each'])} each ({basis}) brings in {money(o['income']['roommate_rent'])}/mo, so your share is {money(o['own_net_housing_cost'])}/mo.",
             f"Alquilar {o['rooms_rented']} cuartos a unos {money(o['room_rent_each'])} cada uno ({basis}) trae {money(o['income']['roommate_rent'])}/mes, así que su parte es {money(o['own_net_housing_cost'])}/mes."))
        st.caption(L("Co-op boards often limit roommates. Check the building rules first." if "co-op" in own else "Check that the building rules allow roommates.",
                     "Las juntas de co-op a menudo limitan compañeros. Revise las reglas primero." if "co-op" in own else "Confirme que las reglas del edificio permitan compañeros."))

    # --- building rules
    ic, bp = r.get("coop_income_check"), r.get("building_policy") or {}
    if ic or bp:
        st.markdown(f"#### {L('📋 Building rules', '📋 Reglas del edificio')}")
        if ic:
            md(L(f"The board wants your yearly income to be {ic['multiple']:g} times the housing cost: about {money(ic['required_income_maintenance_only'])} for the building fee alone, "
                 f"or {money(ic['required_income_with_mortgage'])} counting the mortgage too." + (f" You entered {money(ic['buyer_income'])}." if ic.get("buyer_income") else ""),
                 f"La junta quiere que su ingreso anual sea {ic['multiple']:g} veces el costo de vivienda: unos {money(ic['required_income_maintenance_only'])} solo por la cuota, "
                 f"o {money(ic['required_income_with_mortgage'])} contando la hipoteca." + (f" Usted puso {money(ic['buyer_income'])}." if ic.get("buyer_income") else "")))
        note = bp.get("es" if ES() else "en")
        if note and bp.get("source") != "user input":
            md(S.plain(note))

    # --- rent estimate
    rc = r.get("rent_compare") or {}
    st.markdown(f"#### {L('📊 Rent estimate', '📊 Estimado de renta')}")
    src_name = {"rentcast": "RentCast", "free": L("nearby listings", "anuncios cercanos"), "hud": L("HUD fair rent for this ZIP code", "renta justa de HUD para este código postal")}.get(rent_src, "?")
    md(L(f"We used **{money(rent)}/mo** ({src_name}).", f"Usamos **{money(rent)}/mes** ({src_name}).") if rent else L("No rent estimate found.", "No se encontró estimado de renta."))
    lines = []
    if rc.get("free_ok"):
        lines.append(L(f"Nearby listings (free sources): {money(rc['free_median'])}/mo, from {rc['free_n']} listings",
                       f"Anuncios cercanos (fuentes gratuitas): {money(rc['free_median'])}/mes, de {rc['free_n']} anuncios"))
    if rc.get("rentcast_ok"):
        rng = L(f", range {money(rc.get('rentcast_low'))} to {money(rc.get('rentcast_high'))}", f", rango {money(rc.get('rentcast_low'))} a {money(rc.get('rentcast_high'))}") if rc.get("rentcast_low") else ""
        lines.append(L(f"RentCast: {money(rc['rentcast_rent'])}/mo, from {rc['rentcast_n']} rentals{rng}", f"RentCast: {money(rc['rentcast_rent'])}/mes, de {rc['rentcast_n']} alquileres{rng}"))
    else:
        why = {"quota": L("monthly limit reached", "límite mensual alcanzado"), "not_found": L("no estimate for this address", "sin estimado para esta dirección"),
               "no_key": L("not set up", "no configurado"), None: L("not used", "no usado")}.get(rc.get("rentcast_status"), L("not available", "no disponible"))
        lines.append(f"RentCast: {why}")
    md("\n".join(f"- {x}" for x in lines))
    g = S.rent_gap_line(r)
    if g:
        st.caption("⚠️ " + P(g).replace("$", "\\$"))
    comps = [c for c in (r.get("ltr") or {}).get("comps", [])][:5]
    rcc = ((r.get("rentcast") or {}).get("avm_comps") or [])[:5]
    for title, rows in ((L("Nearby listings", "Anuncios cercanos"), comps), (L("RentCast examples", "Ejemplos de RentCast"), rcc)):
        if rows:
            items = []
            for c in rows:
                bd = f"{int(c['beds'])} {L('bd', 'hab')}" if c.get("beds") is not None else ""
                url = c.get("url") if str(c.get("url", "")).startswith("http") else None
                name = H.escape(S.listing_name(c))[:48]
                items.append(f"<li>{money(c.get('price'))} · {bd} · {S.miles(c.get('dist_km'))} · " + (f"<a href='{H.escape(url)}' target='_blank'>{name}</a>" if url else name) + "</li>")
            html(f"<div class='bz-small'><b>{title}</b><ul>{''.join(items)}</ul></div>")

    # --- other ways
    st.markdown(f"#### {L('✨ Other ways to use this home', '✨ Otras formas de usar esta casa')}")
    inv, mtr, strs = sc.get("investment_ltr"), sc.get("mtr"), sc.get("str")
    lines = []
    if inv:
        lines.append(L(f"Rent it all to one tenant (investment loan, {fi.get('investment_down_pct', .25):.0%} down, {money(inv['loan']['cash_to_close_est'])} to close): {profit_txt(inv['net_monthly'])}",
                       f"Alquilarla completa a un inquilino (préstamo de inversión, {fi.get('investment_down_pct', .25):.0%} inicial, {money(inv['loan']['cash_to_close_est'])} para cerrar): {profit_txt(inv['net_monthly'])}"))
    if mtr:
        m = A.get("mtr", {})
        lines.append(L(f"Rent it furnished for 30+ days at a time (same loan): {profit_txt(mtr['net_monthly'])}. We estimate {money(mtr['mtr_rate'])}/mo from nearby furnished monthly listings "
                       f"(at most {m.get('max_premium_over_ltr', 1.5):g} times normal rent), rented {m.get('occupancy', .8):.0%} of the time.",
                       f"Alquilarla amueblada por 30+ días (mismo préstamo): {profit_txt(mtr['net_monthly'])}. Calculamos {money(mtr['mtr_rate'])}/mes con anuncios amueblados mensuales cercanos "
                       f"(máximo {m.get('max_premium_over_ltr', 1.5):g} veces la renta normal), alquilada el {m.get('occupancy', .8):.0%} del tiempo."))
    if strs:
        lines.append(L("Airbnb (under 30 nights): not allowed here, so we didn't count it.", "Airbnb (menos de 30 noches): no se permite aquí, así que no lo contamos.") if not strs.get("legal")
                     else L(f"Short-term rental with the town's limits: {profit_txt(strs['net_monthly'])}", f"Alquiler corto con los límites del pueblo: {profit_txt(strs['net_monthly'])}"))
    if lines:
        md("\n".join(f"- {x}" for x in lines))
        if "co-op" in own:
            st.caption(L("Most co-ops don't allow buying to rent out. Check the house rules.", "La mayoría de las co-ops no permiten comprar para alquilar. Revise las reglas."))
    else:
        st.caption(L("Add the price to see these.", "Agregue el precio para ver esto."))

    # --- airbnb rules
    sr = r.get("str_rules") or {}
    st.markdown(f"#### {L('🏙️ Airbnb rules in this town', '🏙️ Reglas de Airbnb en este pueblo')}")
    md(S.plain(sr.get("summary_es" if ES() else "summary_en", "")))
    links = []
    for x in sr.get("sources", []):
        mm = re.search(r"https?://\S+", x)
        if mm:
            links.append(f"[{mm.group(0).split('/')[2]}]({mm.group(0).rstrip(')')})")
    if links or sr.get("last_verified"):
        st.caption(L("Source: ", "Fuente: ") + ", ".join(links) + (L(f" (checked {sr.get('last_verified')})", f" (revisado {sr.get('last_verified')})") if sr.get("last_verified") else ""))

    # --- things to check
    w = S.plain_warnings(r)
    if w:
        st.markdown(f"#### {L('🔍 Things to double-check', '🔍 Cosas para confirmar')}")
        md("\n".join(f"- {P(x)}" for x in w))

    glossary()

    # --- verdict rules + assumptions
    st.markdown(f"#### {L('🧮 How we got these numbers', '🧮 Cómo calculamos esto')}")
    rt = r.get("rates") or {}
    oc = A.get("ownership_costs", {})
    wk = re.search(r"week of (\d{4}-\d{2}-\d{2})", rt.get("source", ""))
    items = [L(f"Interest rate {rt.get('base', 0):.2f}%: the U.S. weekly average from Freddie Mac" + (f" (week of {wk.group(1)})" if wk else "") + f". Investment loans cost {fi.get('investment_rate_adjust', .75):.2f}% more.",
               f"Tasa de interés {rt.get('base', 0):.2f}%: el promedio semanal de EE.UU. de Freddie Mac" + (f" (semana del {wk.group(1)})" if wk else "") + f". Los préstamos de inversión cuestan {fi.get('investment_rate_adjust', .75):.2f}% más."),
             L(f"Down payment: {fi.get('fha_down_pct', .035):.1%} for FHA, {fi.get('owner_conv_down_pct', .1):.0%} for a co-op loan, {fi.get('investment_down_pct', .25):.0%} for an investment loan. Closing costs {fi.get('closing_cost_pct', .03):.0%} of the price.",
               f"Pago inicial: {fi.get('fha_down_pct', .035):.1%} con FHA, {fi.get('owner_conv_down_pct', .1):.0%} con préstamo de co-op, {fi.get('investment_down_pct', .25):.0%} con préstamo de inversión. Gastos de cierre {fi.get('closing_cost_pct', .03):.0%} del precio."),
             L(f"FHA insurance: {fi.get('fha_upfront_mip_pct', 0):.2%} added to the loan plus {fi.get('fha_annual_mip_pct', 0):.2%} a year. Home insurance {money(oc.get('ho6_insurance_monthly'))}/mo. Repairs savings {oc.get('maintenance_reserve_pct_of_price', 0):.1%} of the price a year.",
               f"Seguro FHA: {fi.get('fha_upfront_mip_pct', 0):.2%} sumado al préstamo más {fi.get('fha_annual_mip_pct', 0):.2%} al año. Seguro de vivienda {money(oc.get('ho6_insurance_monthly'))}/mes. Ahorro para reparaciones {oc.get('maintenance_reserve_pct_of_price', 0):.1%} del precio al año."),
             L("Verdict: Skip if the income you entered is below the board rule or housing would take over 45% of it, or if even with roommates it costs more than the home's rent. "
               "Good deal if living there costs no more than that rent. Otherwise Maybe.",
               "Veredicto: Mejor no si el ingreso que puso no alcanza la regla de la junta o la vivienda se lleva más del 45%, o si aun con compañeros cuesta más que la renta de la casa. "
               "Buen negocio si vivir allí cuesta lo mismo o menos que esa renta. Si no, Tal vez.")]
    md("\n".join(f"- {x}" for x in items))
    ok_src = sorted({s["source"].split(":")[0] for s in r.get("sources_status", []) if s.get("ok")})
    bad_src = sorted({s["source"].split(":")[0] for s in r.get("sources_status", []) if not s.get("ok")} - set(ok_src))
    st.caption(L("Data from: ", "Datos de: ") + ", ".join(ok_src) + ((L(". Could not reach: ", ". No se pudo consultar: ") + ", ".join(bad_src)) if bad_src else "") + ".")
    try:
        xb, xn = xlsx_bytes(r, "property")
        st.download_button(L("⬇️ Spreadsheet (Excel)", "⬇️ Hoja de cálculo (Excel)"), xb, xn, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dlx_prop", width="stretch", on_click="ignore")
    except Exception as e:
        st.caption(f"Excel: {e.__class__.__name__}")
    st.caption(L("Estimates from public data, not financial, legal or lending advice. Confirm with your lender, agent and the town.",
                 "Estimados con datos públicos; no es asesoría financiera, legal ni hipotecaria. Confirme con su prestamista, agente y el municipio."))


GLOSSARY = [
    (("Down payment", "Pago inicial (down payment)"), ("The part of the price you pay yourself. The bank lends you the rest.", "La parte del precio que usted paga. El banco le presta el resto.")),
    (("HOA / building fee", "HOA / cuota del edificio"), ("A monthly fee for the building: cleaning, repairs, doorman, and sometimes taxes and utilities.", "Una cuota mensual del edificio: limpieza, arreglos, portero y a veces impuestos y servicios.")),
    (("Co-op", "Co-op (cooperativa)"), ("You buy shares in the building instead of the apartment itself. A board must approve you and often limits renting out.", "Usted compra acciones del edificio en vez del apartamento. Una junta debe aprobarle y a menudo limita alquilar.")),
    (("FHA loan", "Préstamo FHA"), ("A government-backed loan for first-time buyers. You can put down as little as 3.5%, plus a small insurance fee.", "Un préstamo respaldado por el gobierno para primeros compradores. Puede dar desde 3.5% inicial, más un pequeño seguro.")),
    (("Closing costs", "Gastos de cierre"), ("Fees you pay on closing day: lawyer, bank, title and inspection. Often 2% to 5% of the price.", "Cargos que paga el día del cierre: abogado, banco, título e inspección. Suelen ser 2% a 5% del precio.")),
    (("30+ day rental", "Alquiler de 30+ días"), ("Renting a furnished home for a month or more, like to traveling nurses. It's allowed in many towns that ban Airbnb.", "Alquilar una casa amueblada por un mes o más, por ejemplo a enfermeras viajeras. Se permite en muchos pueblos que prohíben Airbnb.")),
    (("Pre-qualify", "Precalificar"), ("A quick check with a lender that tells you how much you could borrow. It's free and doesn't commit you.", "Una revisión rápida con un prestamista que le dice cuánto le podrían prestar. Es gratis y no le compromete.")),
]


def glossary():
    st.markdown(f"#### {L('📖 Words to know', '📖 Palabras clave')}")
    md("\n".join(f"- **{P(w)}:** {P(d)}" for w, d in GLOSSARY))


def how_it_works():
    steps = [L("Type or paste an address", "Escriba o pegue una dirección"), L("We check the numbers for you", "Revisamos los números por usted"),
             L("You get a simple answer", "Usted recibe una respuesta sencilla")]
    html("<div class='bz-how'><b>" + L("How it works ✨", "Cómo funciona ✨") + "</b>"
         + "".join(f"<div class='step'><div class='n'>{i}</div><div>{H.escape(t)}</div></div>" for i, t in enumerate(steps, 1)) + "</div>")


def example():
    """Optional example home from the BELLAZU_EXAMPLE secret (JSON with address + details, or a plain address). Never hard-coded."""
    raw = secret("BELLAZU_EXAMPLE")
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) and d.get("address") else None
    except ValueError:
        return {"address": raw}


def use_example():
    ex = example() or {}
    ss = st.session_state
    ss.addr = ex.get("address", "")
    for k, w in (("price", "price"), ("hoa", "hoa"), ("taxes", "taxes"), ("beds", "beds")):
        if ex.get(k) is not None:
            ss[w] = int(ex[k])
    if ex.get("type") in ("condo", "co-op", "single-family", "multi-family"):
        ss.own = ex["type"]
    if ex.get("includes"):
        ss.inc = [x for x in ex["includes"] if x in INC_LBL]
    if ex.get("board_multiple"):
        ss.mult = float(ex["board_multiple"])
    if ex.get("link"):
        ss.link = ex["link"]
    ss.auto_go = True


# ------------------------------------------------------------------ Check a home: page
def home_page():
    for k, v in (("price", 0), ("hoa", 0), ("taxes", 0), ("beds", 0), ("mult", 0.0), ("income", 0), ("down", 0.0), ("use_rc", rentcast.available())):
        st.session_state.setdefault(k, v)
    res_box = st.container()
    r = st.session_state.get("prop")
    if r and r.get("ok"):
        st.divider()
        st.markdown(f"**{L('Want to check another home? 🏡', '¿Quiere revisar otra casa? 🏡')}**")
    else:
        html(f"<div class='bz-hello'>{L('Let us check this home together 🏡', 'Revisemos esta casa juntas 🏡')}</div>".replace("Let us", "Let's"))
        how_it_works()
    addr = st.text_input(L("Home address", "Dirección de la casa"), placeholder=L("e.g. 123 Main St Apt 4, Fort Lee, NJ 07024", "ej. 123 Main St Apt 4, Fort Lee, NJ 07024"), key="addr")
    with st.expander(L("Add details (optional)", "Agregar detalles (opcional)")):
        st.caption(L("Anything you type here is used instead of what we find online. Leave 0 if you don't know.",
                     "Lo que escriba aquí se usa en lugar de lo que encontremos en internet. Deje 0 si no sabe."))
        link = st.text_input(L("Listing link (Zillow, Redfin...)", "Link del anuncio (Zillow, Redfin...)"), key="link")
        price = st.number_input(L("Price ($)", "Precio ($)"), min_value=0, max_value=20_000_000, step=5000, key="price")
        hoa = st.number_input(L("Monthly building fee, HOA or maintenance ($)", "Cuota mensual del edificio, HOA o mantenimiento ($)"), min_value=0, max_value=50_000, step=25, key="hoa")
        taxes = st.number_input(L("Property taxes per year ($)", "Impuestos por año ($)"), min_value=0, max_value=200_000, step=100, key="taxes")
        beds = st.number_input(L("Bedrooms", "Habitaciones"), min_value=0, max_value=10, step=1, key="beds")
        types = ["", "condo", "co-op", "single-family", "multi-family"]
        own = st.selectbox(L("Type of home", "Tipo de vivienda"), types, key="own",
                           format_func=lambda k: L("I don't know", "No sé") if not k else P(TYPE_LBL[k]))
        inc = st.multiselect(L("The building fee includes", "La cuota del edificio incluye"), list(INC_LBL), key="inc", format_func=lambda k: P(INC_LBL[k]))
        mult = st.number_input(L("Co-op/condo board income rule (e.g. 4 means income must be 4 times housing costs; 0 if none)",
                                 "Regla de ingreso de la junta (ej. 4 = el ingreso debe ser 4 veces el costo de vivienda; 0 si no hay)"), min_value=0.0, max_value=10.0, step=0.5, key="mult")
        income = st.number_input(L("Your yearly income before taxes ($). Not saved.", "Su ingreso anual antes de impuestos ($). No se guarda."), min_value=0, max_value=5_000_000, step=1000, key="income")
        down = st.number_input(L("Down payment (% of price). 0 = usual minimum.", "Pago inicial (% del precio). 0 = el mínimo usual."), min_value=0.0, max_value=100.0, step=0.5, key="down")
        use_rc = st.checkbox(L("Use RentCast for a better rent estimate (uses 1 to 3 of the monthly lookups; repeats are free)",
                               "Usar RentCast para un mejor estimado de renta (usa 1 a 3 consultas del mes; repetir es gratis)"),
                             disabled=not rentcast.available(), key="use_rc")
    go = st.button(L("Check this home 🏡", "Revisar esta casa 🏡"), type="primary", key="go_prop", width="stretch")
    if example() and not (r and r.get("ok")):
        st.button(L("✨ Try an example home", "✨ Probar con una casa de ejemplo"), key="ex_btn", width="stretch", on_click=use_example)
    go = go or st.session_state.pop("auto_go", False)

    if go:
        a = addr.strip() or (addr_from_link(link.strip()) if link.strip() else "")
        if not a:
            with res_box:
                st.warning(L("Type an address first, and we'll take it from there 💕", "Primero escriba una dirección y nos encargamos del resto 💕"))
        else:
            ov = {"price": price or None, "hoa_monthly": hoa or None, "taxes_annual": taxes or None, "beds": int(beds) or None,
                  "ownership": own or None, "hoa_includes": inc or None}
            bp = {"en": "Board income rule entered by the user.", "es": "Regla de ingreso de la junta ingresada por el usuario.",
                  "source": "user input", "income_multiple": float(mult)} if mult else None
            opts = {"listing_url": [link.strip()] if link.strip() else None, "overrides": ov, "income_annual": income or None,
                    "building_policy": bp, "use_rentcast": bool(use_rc)}
            if down:
                opts["assumption_overrides"] = {"financing": {"fha_down_pct": down / 100, "owner_conv_down_pct": down / 100}}
            key = json.dumps([a.lower(), opts], sort_keys=True, default=str)
            cache = st.session_state.setdefault("prop_cache", {})
            if key in cache:
                r = cache[key]
            else:
                with res_box, st.spinner(L("Checking the numbers for you... this takes about 20 to 60 seconds ✨", "Revisando los números por usted... toma unos 20 a 60 segundos ✨")):
                    try:
                        r = analyze_property(a, opts)
                    except Exception as e:  # never show a stack trace to the user
                        r = {"ok": False, "error": f"{e.__class__.__name__}"}
                if r.get("ok"):
                    cache[key] = r
            st.session_state.prop = r
            st.rerun()
    with res_box:
        if r and not r.get("ok"):
            st.warning(L("Hmm, we couldn't find that address. Try adding the town and ZIP code.", "No encontramos esa dirección. Intente agregar el pueblo y el código postal.")
                       + f" ({r.get('error')})")
        elif r:
            show_property(r)


# ------------------------------------------------------------------ Town scan
def show_town(a):
    v = S.verdict_town(a)
    verdict_box(v)
    s = a.get("summary") or {}
    if s.get("share_mtr_profitable") is not None:
        md(L(f"We checked {a['n_listings_scored']} rentals. About {s['share_mtr_profitable']:.0%} could make a profit as furnished 30+ day rentals.",
             f"Revisamos {a['n_listings_scored']} alquileres. Cerca del {s['share_mtr_profitable']:.0%} podría dar ganancia como alquiler amueblado de 30+ días."))
    top = S.top_rentals(a, 5)
    if not top:
        st.info(L("No rentals to show.", "No hay alquileres para mostrar."))
    else:
        st.markdown(f"#### {L('✨ Top 5 for furnished 30+ day renting', '✨ Los 5 mejores para alquiler amueblado de 30+ días')}")
        for x in top:
            url = x.get("url") if str(x.get("url", "")).startswith("http") else None
            lk = (L("See on map", "Ver en el mapa") if "google.com/maps" in url else L("See listing", "Ver anuncio")) if url else ""
            p = x.get("mtr_profit_monthly")
            ptxt = (L(f"Could earn about {money(p)}/mo", f"Podría ganar unos {money(p)}/mes") if p >= 0 else L(f"Would lose about {money(-p)}/mo", f"Perdería unos {money(-p)}/mes"))
            html(f"<div class='bz-card'><div class='t'>🏠 {H.escape(S.listing_name(x))}</div>"
                 f"<div class='m'>{L('Rent', 'Renta')} <b>{money(x['rent'])}</b>{L('/mo', '/mes')} · {x['beds']} {L('bd', 'hab')}</div>"
                 f"<div class='m'>💵 <b>{ptxt}</b></div>"
                 + (f"<a href='{H.escape(url)}' target='_blank'>{lk}</a>" if url else "") + "</div>")
        st.caption(L("Profit = furnished monthly rate minus rent, cleaning, utilities, insurance, furniture and fees. You need the landlord's written OK.",
                     "Ganancia = tarifa mensual amueblada menos renta, limpieza, servicios, seguro, muebles y comisiones. Necesita permiso escrito del dueño."))
    with st.expander(L("See details", "Ver detalles")):
        town_details(a)


def town_details(a):
    import pandas as pd
    sr = a.get("str_rules") or {}
    legal_t = bool(sr.get("str_legal_for_tenant"))
    st.markdown(f"#### {L('📋 All rentals we checked', '📋 Todos los alquileres revisados')}")
    rows = []
    for x in a.get("results") or []:
        row = {L("Rental", "Alquiler"): S.listing_name(x), L("Beds", "Hab"): x["beds"], L("Rent", "Renta"): x["rent"],
               L("30+ day profit/mo", "Ganancia 30+ días/mes"): x["mtr_profit_monthly"]}
        if legal_t:
            row[L("Airbnb profit/mo", "Ganancia Airbnb/mes")] = x["str_profit_monthly"]
        row[L("Note", "Nota")] = L("rent looks too low, check it", "renta muy baja, verifique") if x.get("check_flag") else ""
        row[L("From", "Fuente")] = x.get("source")
        row["Link"] = x.get("url") if str(x.get("url", "")).startswith("http") else None
        rows.append(row)
    if rows:
        df = pd.DataFrame(rows).sort_values(L("30+ day profit/mo", "Ganancia 30+ días/mes"), ascending=False)
        st.dataframe(df, hide_index=True, width="stretch", height=360,
                     column_config={"Link": st.column_config.LinkColumn("Link", display_text=L("open", "abrir")),
                                    L("Rent", "Renta"): st.column_config.NumberColumn(format="$%d"),
                                    L("30+ day profit/mo", "Ganancia 30+ días/mes"): st.column_config.NumberColumn(format="$%d"),
                                    **({L("Airbnb profit/mo", "Ganancia Airbnb/mes"): st.column_config.NumberColumn(format="$%d")} if legal_t else {})})
    nflag = sum(1 for x in a.get("results") or [] if x.get("check_flag"))
    if nflag:
        st.caption(L(f"{nflag} rentals have a rent far below the area's usual (maybe a room, a typo or a scam). They're left out of the top 5.",
                     f"{nflag} alquileres tienen una renta muy por debajo de lo normal (quizás un cuarto, un error o una estafa). No están en los 5 mejores."))
    by = (a.get("summary") or {}).get("by_beds") or []
    if by:
        st.markdown(f"#### {L('🏠 Typical rent by size', '🏠 Renta típica por tamaño')}")
        md("\n".join(L(f"- {b['beds']} bedroom: {money(b['rent'])}/mo ({b['n']} rentals), typical 30+ day result {profit_txt(b['mtr_profit'])}",
                       f"- {b['beds']} habitación: {money(b['rent'])}/mes ({b['n']} alquileres), resultado típico 30+ días {profit_txt(b['mtr_profit'])}") for b in by))
    st.markdown(f"#### {L('🏙️ Airbnb rules in this town', '🏙️ Reglas de Airbnb en este pueblo')}")
    md(S.plain(sr.get("summary_es" if ES() else "summary_en", "")))
    links = [f"[{m.group(0).split('/')[2]}]({m.group(0).rstrip(')')})" for m in (re.search(r"https?://\S+", x) for x in sr.get("sources", [])) if m]
    if links:
        st.caption(L("Source: ", "Fuente: ") + ", ".join(links) + (L(f" (checked {sr.get('last_verified')})", f" (revisado {sr.get('last_verified')})") if sr.get("last_verified") else ""))
    st.markdown(f"#### {L('🧮 How we estimate profit', '🧮 Cómo calculamos la ganancia')}")
    A = a.get("assumptions") or {}
    m = A.get("mtr", {})
    md("\n".join(f"- {x}" for x in [
        L(f"Furnished monthly rate: from nearby Airbnb listings that require 28+ night stays, capped at {m.get('max_premium_over_ltr', 1.5):g} times the area's normal rent.",
          f"Tarifa mensual amueblada: de anuncios de Airbnb cercanos con estadías de 28+ noches, con un máximo de {m.get('max_premium_over_ltr', 1.5):g} veces la renta normal."),
        L(f"Rented {m.get('occupancy', .8):.0%} of the time (our guess, there's no public data). Minus rent, cleaning, utilities, insurance, furniture spread over 3 years, and platform fees.",
          f"Alquilado el {m.get('occupancy', .8):.0%} del tiempo (estimado nuestro; no hay datos públicos). Menos renta, limpieza, servicios, seguro, muebles repartidos en 3 años y comisiones."),
        L("Rents are asking prices on the day we looked.", "Las rentas son precios pedidos el día que buscamos."),
        L("Always get the landlord's written permission and the building's OK.", "Siempre consiga permiso escrito del dueño y la aprobación del edificio."),
    ]))
    if not a.get("iab_covers_town"):
        st.caption(L("Airbnb price data comes from nearby cities, so treat it as rough.", "Los datos de Airbnb vienen de ciudades cercanas; tómelos como aproximados."))
    glossary()
    used = [f"{u['source']} ({u.get('n', 0)})" for u in a.get("sources_used") or []]
    st.caption(L("Rentals from: ", "Alquileres de: ") + ", ".join(used) + ". " + L("Airbnb data: Inside Airbnb.", "Datos de Airbnb: Inside Airbnb."))
    st.download_button(L("⬇️ Download your full report", "⬇️ Descargar su reporte completo"), arb_html(a).encode(), f"BellaZu_Town_{safe_name(a['town'])}.html", "text/html",
                       key="dl_town", type="primary", width="stretch", on_click="ignore")
    try:
        xb, xn = xlsx_bytes(a, "arbitrage")
        st.download_button(L("⬇️ Full list (Excel)", "⬇️ Lista completa (Excel)"), xb, xn, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dlx_town", width="stretch", on_click="ignore")
    except Exception as e:
        st.caption(f"Excel: {e.__class__.__name__}")


def town_page():
    res_box = st.container()
    a = st.session_state.get("arb")
    if a and a.get("ok"):
        st.divider()
        st.markdown(f"**{L('Want to look at another town? 🔑', '¿Quiere ver otro pueblo? 🔑')}**")
    else:
        html(f"<div class='bz-hello'>{L('Find rentals you could rent out 🔑', 'Encuentre alquileres que podría subarrendar 🔑')}</div>"
             f"<div class='bz-sub'>{L('Type a town and we will show you the rules first, then the best options.', 'Escriba un pueblo y le mostramos primero las reglas, y luego las mejores opciones.')}</div>")
    town = st.text_input(L("Town", "Pueblo"), placeholder=L("e.g. Jersey City", "ej. Jersey City"), key="town")
    with st.expander(L("More options", "Más opciones")):
        state = st.selectbox(L("State", "Estado"), ["nj", "ny"], format_func=str.upper, key="state")
        use_rc2 = st.checkbox(L("Use RentCast rental listings (1 lookup per town; repeats within 3 days are free)",
                                "Usar anuncios de RentCast (1 consulta por pueblo; repetir en 3 días es gratis)"),
                              value=rentcast.available(), disabled=not rentcast.available(), key="use_rc2")
    go = st.button(L("Find rentals 🔑", "Buscar alquileres 🔑"), type="primary", key="go_scan", width="stretch")
    if go:
        t = town.strip()
        if not t:
            with res_box:
                st.warning(L("Type a town first.", "Primero escriba un pueblo."))
        else:
            key = json.dumps([t.lower(), state, bool(use_rc2)])
            cache = st.session_state.setdefault("arb_cache", {})
            if key in cache:
                a = cache[key]
            else:
                with res_box, st.spinner(L("Looking at rentals for you... about 20 to 60 seconds ✨", "Buscando alquileres por usted... unos 20 a 60 segundos ✨")):
                    try:
                        a = scan_arbitrage(t, {"state": state, "use_rentcast": bool(use_rc2)})
                    except Exception as e:
                        a = {"ok": False, "error": f"{e.__class__.__name__}"}
                if a.get("ok"):
                    cache[key] = a
            st.session_state.arb = a
            st.rerun()
    with res_box:
        if a and not a.get("ok"):
            st.warning(L("We couldn't check that town. Check the spelling.", "No pudimos revisar ese pueblo. Revise cómo lo escribió.") + f" ({a.get('error')})")
        elif a:
            show_town(a)


# ------------------------------------------------------------------ page
if mode == "town":
    town_page()
else:
    home_page()

st.write("")
with st.expander(L("About BellaZu", "Sobre BellaZu"), icon="ℹ️"):
    md(L("BellaZu helps first-time buyers in North Jersey check a home and find rentals, using free public data "
         "(Inside Airbnb, HUD, Census, Freddie Mac, OpenStreetMap, Craigslist, Rent.com, Redfin and, if set up, RentCast).\n\n"
         "**Privacy:** what you type stays in this browser session. Nothing is saved to an account.\n\n"
         "**Important:** these are estimates, not financial, legal or lending advice.",
         "BellaZu ayuda a primeros compradores en el norte de NJ a revisar una casa y buscar alquileres, con datos públicos gratuitos "
         "(Inside Airbnb, HUD, Censo, Freddie Mac, OpenStreetMap, Craigslist, Rent.com, Redfin y, si está configurado, RentCast).\n\n"
         "**Privacidad:** lo que escribe se queda en esta sesión del navegador. No se guarda en ninguna cuenta.\n\n"
         "**Importante:** son estimados, no asesoría financiera, legal ni hipotecaria."))
    st.caption(rc_usage_line())
    if st.button(L("Check which data sources work from this server", "Revisar qué fuentes funcionan desde este servidor"), key="probe"):
        import requests
        from bellazu.http import UA_BROWSER
        checks = [("Craigslist", "https://www.craigslist.org/search/city/fort-lee-nj?cat=apa", "cl-static-search-result"),
                  ("Rent.com", "https://www.rent.com/new-jersey/fort-lee-apartments", "__NEXT_DATA__"),
                  ("Redfin", "https://www.redfin.com/city/6283/NJ/Fort-Lee/apartments-for-rent", "application/ld+json"),
                  ("Zillow", "https://www.zillow.com/fort-lee-nj/rentals/", "__NEXT_DATA__"),
                  ("Inside Airbnb", "https://insideairbnb.com/get-the-data/", "jersey-city"),
                  ("Census Reporter", "https://api.censusreporter.org/1.0/data/show/latest?table_ids=B25031&geo_ids=86000US07024", "B25031"),
                  ("FRED", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US", "MORTGAGE30US"),
                  ("OpenStreetMap", "https://nominatim.openstreetmap.org/search?q=Fort+Lee,+NJ&format=json&limit=1", "lat")]
        rows = []
        for name, url, needle in checks:
            try:
                ua = "BellaZu/0.1 (personal real-estate research; low volume)" if "nominatim" in url else UA_BROWSER
                rr = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"}, timeout=30)
                rows.append({"source": name, "works": "yes" if rr.status_code == 200 and needle.encode() in rr.content else "no", "http": rr.status_code})
            except Exception as e:
                rows.append({"source": name, "works": "no", "http": e.__class__.__name__})
            time.sleep(1.2)
        st.dataframe(rows, hide_index=True, width="stretch")
    if st.button(L("Log out", "Salir"), key="logout", type="tertiary"):
        for k in list(st.session_state.keys()):
            if k != "lang":
                del st.session_state[k]
        st.rerun()
