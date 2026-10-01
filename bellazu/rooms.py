"""Rent rooms (house-hacking by the room): monthly income model + the platform guide + the warnings. Pure Python, no Streamlit, no API calls.

Room rent is an ESTIMATE built from two public sources and then capped:
  1. SpareRoom's asking-rent index for rooms in shared homes (NYC boroughs Q2 2026; Hudson County NJ Q2 2025; NY-NJ metro Q2 2026),
  2. minus 12% because SpareRoom reports that living with the owner is on average 12% cheaper (Q2 2025 release),
  3. capped at HUD's FY2026 Small Area Fair Market Rent for the ZIP, divided by the number of bedrooms (HUD publishes no per-room rent; this is a sanity ceiling).
Everything is editable in the app and labeled as an estimate."""

# --- room rent data (asking rents, a month) -------------------------------------------------------------------------------------------
SR_NYC = "https://www.spareroom.com/content/info-statistics/nyc-roommates-ronkonkoma-tarrytown"
SR_2025 = "https://www.spareroom.com/content/info-statistics/nyc-rents-Q2-2025"
OWNER_DISCOUNT = 0.12          # "Living with your landlord is on average 12% cheaper" (SpareRoom, Q2 2025 release, SR_2025)
AREAS = {
    "manhattan": (1847, ("Manhattan", "Manhattan"), "SpareRoom Q2 2026", SR_NYC),
    "bronx": (1169, ("the Bronx", "el Bronx"), "SpareRoom Q2 2026", SR_NYC),
    "brooklyn": (1448, ("Brooklyn", "Brooklyn"), "SpareRoom Q2 2026", SR_NYC),
    "queens": (1266, ("Queens", "Queens"), "SpareRoom Q2 2026", SR_NYC),
    "hudson": (1369, ("Hudson County, NJ", "Condado Hudson, NJ"), "SpareRoom Q2 2025 (older)", SR_2025),
    "westchester": (1323, ("Westchester", "Westchester"), "SpareRoom Q2 2025 (older)", SR_2025),
    "metro": (1515, ("the New York metro area", "el área metropolitana de Nueva York"), "SpareRoom Q2 2026 (metro average)", SR_NYC),
}
_HUDSON_ZIPS = {"07002", "07029", "07030", "07032", "07086", "07087", "07093", "07094", "07047", "07311", "07310"}


def area_for(zip_):
    z = str(zip_ or "").strip()[:5]
    if z.startswith("073") or z in _HUDSON_ZIPS:
        k = "hudson"
    elif z[:3] in ("100", "101", "102"):
        k = "manhattan"
    elif z[:3] == "104":
        k = "bronx"
    elif z[:3] == "112":
        k = "brooklyn"
    elif z[:3] in ("111", "113", "114", "116"):
        k = "queens"
    elif z[:3] in ("105", "106", "107", "108", "109"):
        k = "westchester"
    else:
        k = "metro"
    avg, name, src, url = AREAS[k]
    return {"key": k, "avg": avg, "name": name, "src": src, "url": url}


def _r25(v, up=False):
    import math
    return int((math.ceil if up else math.floor)(float(v) / 25.0) * 25)


def room_rent(zip_, beds, hud_fn=None):
    """Default room rent for one room: SpareRoom area average x (1 - 12%), capped at HUD's per-bedroom share. Returns a dict (all numbers are estimates)."""
    a = area_for(zip_)
    mkt = _r25(a["avg"] * (1 - OWNER_DISCOUNT))
    cap = None
    try:
        h = hud_fn(zip_, beds) if hud_fn and beds else None
        if h:
            cap = _r25(float(h) / max(int(beds), 1))
    except Exception:
        cap = None
    val = min(mkt, cap) if cap else mkt
    return {"rent": val, "market": mkt, "hud_share": cap, "capped": bool(cap and cap < mkt), "area": a}


# --- platforms -----------------------------------------------------------------------------------------------------------------------
# fee model per option: pct of collected rent, flat a month per room (listing cost spread over the year), both estimates
PLAT = {
    "direct": {"pct": 0.0, "flat": 0.0, "n": ("Direct (Zelle / check), no platform", "Directo (Zelle / cheque), sin plataforma")},
    "spareroom": {"pct": 0.0, "flat": 14.0, "n": ("SpareRoom (free ad + a paid boost now and then)", "SpareRoom (anuncio gratis + un impulso pagado de vez en cuando)")},
    "roommates": {"pct": 0.0, "flat": 14.0, "n": ("Roommates.com / Roomster / Roomies (paid plan)", "Roommates.com / Roomster / Roomies (plan pagado)")},
    "ff": {"pct": 0.0, "flat": round(199 / 12, 2), "n": ("Furnished Finder ($199 a year per room listing)", "Furnished Finder ($199 al año por anuncio de cuarto)")},
    "zillow": {"pct": 0.0, "flat": 0.0, "n": ("Zillow Rental Manager (free; renters pay $35 to apply)", "Zillow Rental Manager (gratis; el inquilino paga $35 por aplicar)")},
    "avail": {"pct": 0.0, "flat": 0.0, "n": ("Avail / Apartments.com (free plan; renter pays card/ACH fees)", "Avail / Apartments.com (plan gratis; el inquilino paga los cargos)")},
    "padsplit": {"pct": 0.08 + (10 / 30) / 12, "flat": 0.0, "n": ("PadSplit (8% + first 10 days of each new member, spread over a year)", "PadSplit (8% + los primeros 10 días de cada miembro nuevo, repartidos en un año)")},
    "airbnb": {"pct": 0.155, "flat": 0.0, "n": ("Airbnb monthly stays (15.5% host fee)", "Airbnb estadías mensuales (cargo al anfitrión 15.5%)")},
}
PLAT_ORDER = ["direct", "spareroom", "roommates", "ff", "zillow", "avail", "padsplit", "airbnb"]

DEFAULTS = {"vac": 10, "plat": "direct", "util": 40, "furn": 25, "ins": 20}
# util: extra electric/gas/water/internet for one more person, a month. furn: ~$600 of furniture per room over 24 months. ins: landlord endorsement on the home policy (ask the insurer). All estimates.


def calc(total, ap, rooms, rent_each, vac_pct, plat, util_room, furn_room, ins_flat, base_tag, price=None, max_price=None):
    """Monthly effect of renting `rooms` rooms. total = the home's monthly total (what the benchmark counts), ap = the benchmark.
    base_tag = the home's tag WITHOUT room income ('ok' green, 'monthly', 'over', 'unk').
    The tag returned never turns green unless the home was already green without room income:
      ok (green, same as base) | rooms_only (yellow: at or under the benchmark only with room income) | monthly (yellow: still above) | over (red: price above the cap) | unk (gray)."""
    P = PLAT.get(plat) or PLAT["direct"]
    rooms = max(int(rooms or 0), 0)
    gross = rooms * float(rent_each or 0)
    vac = gross * float(vac_pct) / 100.0
    occupied = gross - vac
    fee = occupied * P["pct"] + P["flat"] * rooms
    adds = rooms * (float(util_room) + float(furn_room)) + (float(ins_flat) if rooms else 0.0)
    net = occupied - fee - adds
    after = float(total) - net
    if rooms == 0:
        tag = base_tag
    elif base_tag in ("over", "unk"):
        tag = base_tag
    elif base_tag == "ok":
        tag = "ok"
    else:
        tag = "rooms_only" if after <= ap + 0.5 else "monthly"
    if tag == "ok" and float(total) > ap + 0.5:      # belt and braces: never green when the home itself is above the benchmark
        tag = "monthly"
    return {"rooms": rooms, "gross": round(gross), "vacancy": round(vac), "fee": round(fee), "adds": round(adds), "net": round(net),
            "total": round(float(total)), "after": round(after), "ap": round(ap), "gap": round(after - ap), "tag": tag,
            "lender_total": round(float(total)), "break_even_rent": None}


def break_even(total, ap, rooms, vac_pct, plat, util_room, furn_room, ins_flat):
    """Room rent each that brings the monthly total down to the benchmark (None if no rooms)."""
    if rooms < 1 or total <= ap:
        return None
    P = PLAT.get(plat) or PLAT["direct"]
    need = (total - ap) + rooms * (util_room + furn_room) + ins_flat + P["flat"] * rooms
    k = rooms * (1 - vac_pct / 100.0) * (1 - P["pct"])
    return round(need / k) if k > 0 else None


# --- text ----------------------------------------------------------------------------------------------------------------------------
U_FHA = "https://www.hud.gov/sites/documents/41551c1hsgh.pdf"
U_BOARD = "https://www.hud.gov/sites/default/files/OCHCO/documents/2025-04hsgml.pdf"
U_LL18 = "https://www.nyc.gov/site/specialenforcement/hosting-STRs/what-is-local-law-18.page"
U_768 = "https://ag.ny.gov/resources/government-organizations/law-enforcement-guidance/unlawful-evictions"
U_NJREG = "https://www.nj.gov/dca/codes/publications/pdf_lti/landlord_idnty_law.pdf"
U_NJLEAD = "https://www.nj.gov/dca/codes/resources/leadpaint.shtml"
U_IRS = "https://www.irs.gov/publications/p527"

WARN = [
    ("**FHA needs you to live there at least 1 year, not 1 month.** HUD: at least one borrower must move in within 60 days of closing and keep living there for at least one year. Renting rooms is fine while you live there; moving out early and renting the whole home can put the loan in trouble. Ask your lender in writing.",
     "**FHA exige que usted viva ahí al menos 1 año, no 1 mes.** HUD: al menos un prestatario debe mudarse en los 60 días después del cierre y seguir viviendo ahí al menos un año. Alquilar cuartos está bien mientras usted viva ahí; mudarse antes y alquilar toda la casa puede poner el préstamo en problemas. Pregunte a su banco por escrito.", U_FHA),
    ("**Lenders usually don't count room rent to qualify.** FHA can count boarder income only after a 12-month history (9 of the last 12 months documented, a written agreement, capped at 30% of your income). A brand-new rental doesn't count. So this page shows your payment WITH and WITHOUT room income, and green only means green without it.",
     "**Los bancos normalmente no cuentan la renta de cuartos para calificar.** FHA puede contar ingreso de inquilinos de cuarto solo con 12 meses de historial (9 de los últimos 12 meses documentados, contrato escrito, tope de 30% de su ingreso). Un alquiler nuevo no cuenta. Por eso aquí se muestra su pago CON y SIN ese ingreso, y verde solo significa verde sin él.", U_BOARD),
    ("**Stays of 30+ days make the person a tenant with rights.** In New York, anyone who has lived there 30 days (or has any rent agreement, even oral) cannot be removed without a court case. Changing locks, shutting off utilities or removing belongings is a crime (RPAPL 768) with fines of $1,000-$10,000 and a possible misdemeanor. Evicting takes weeks to months. NJ also bars lock-outs (N.J.S.A. 2A:39-1).",
     "**Estadías de 30+ días convierten a la persona en inquilino con derechos.** En Nueva York, quien lleva 30 días (o tiene cualquier acuerdo de renta, aunque sea oral) no puede ser sacado sin un caso en corte. Cambiar cerraduras, cortar servicios o sacar sus cosas es un delito (RPAPL 768) con multas de $1,000 a $10,000 y posible delito menor. Desalojar toma semanas o meses. NJ también prohíbe sacar a alguien por la fuerza (N.J.S.A. 2A:39-1).", U_768),
    ("**NYC short stays (under 30 days):** you may host only if you live in the home during the stay, at most 2 guests, and you must register under Local Law 18; rent-stabilized, public-housing and banned buildings can't register. Renting an entire home under 30 days is illegal in NYC. Rooms for 30+ days don't need that registration, but NYC also limits roomers (state law counts up to 4 boarders in a \"family\"; NYC treats more than 2 roomers in an apartment as rooming-house use). Verify with the Department of Buildings.",
     "**Estadías cortas en NYC (menos de 30 días):** solo puede hospedar si usted vive en la casa durante la estadía, máximo 2 huéspedes, y debe registrarse (Ley Local 18); edificios con renta estabilizada, vivienda pública o prohibidos no pueden registrarse. Alquilar toda la casa por menos de 30 días es ilegal en NYC. Los cuartos por 30+ días no necesitan ese registro, pero NYC también limita los inquilinos de cuarto (la ley estatal cuenta hasta 4 en una \"familia\"; NYC trata más de 2 en un apartamento como casa de cuartos). Verifique con el Departamento de Edificios.", U_LL18),
    ("**Co-op and condo rules come first.** Many co-ops ban or limit roommates and sublets (board approval, fees, waiting years); condos may cap rentals. Get the proprietary lease / bylaws and ask the board in writing before you count any room.",
     "**Primero las reglas del co-op y del condominio.** Muchos co-ops prohíben o limitan compañeros de cuarto y subarriendos (aprobación de la junta, cargos, años de espera); los condominios pueden limitar alquileres. Pida el contrato / estatutos y pregunte a la junta por escrito antes de contar un cuarto.", None),
    ("**NJ:** an owner-occupied 2-family is exempt from landlord registration only if it is lead-safe/lead-free certified, built in 1978 or later, or a seasonal rental; otherwise register with the state. NJ's lead-paint rule (P.L. 2021 c.182) covers rentals built before 1978, including owner-occupied ones: inspect at tenant turnover or every 3 years. NJ's Anti-Eviction Act good-cause rules do not apply to owner-occupied buildings with up to 2 rental units, but court process is still required. A house with many rooms for rent can be treated as a licensed rooming house (up to $25,000 penalty).",
     "**NJ:** una casa de 2 familias ocupada por su dueño solo queda exenta del registro de propietarios si tiene certificado libre de plomo, se construyó en 1978 o después, o es alquiler de temporada; si no, hay que registrarla con el estado. La regla de plomo de NJ (P.L. 2021 c.182) cubre alquileres de antes de 1978, también los ocupados por el dueño: inspección al cambiar de inquilino o cada 3 años. Las reglas de causa justa de la Ley Anti-Desalojo de NJ no aplican a edificios ocupados por su dueño con hasta 2 unidades en alquiler, pero igual se necesita proceso en corte. Una casa con muchos cuartos en alquiler puede considerarse casa de huéspedes con licencia (multa hasta $25,000).", U_NJREG),
    ("**Insurance:** tell your insurer. A normal homeowner/condo policy may not cover tenants' belongings, liability from a paying roomer, or lost rent. Ask for a landlord or room-rental endorsement (this page assumes about $20 a month).",
     "**Seguro:** avise a su aseguradora. Una póliza normal de casa o condominio puede no cubrir las cosas de los inquilinos, la responsabilidad por un inquilino que paga, ni la renta perdida. Pida una cobertura de arrendador o de alquiler de cuartos (esta página supone unos $20 al mes).", None),
    ("**Taxes:** room rent is taxable income (IRS Schedule E). You can deduct the rented share of mortgage interest, taxes, utilities and repairs, and depreciate that share. Amounts here are before income tax. Talk to a tax preparer before you start.",
     "**Impuestos:** la renta de cuartos es ingreso sujeto a impuestos (Anexo E del IRS). Puede deducir la parte alquilada del interés, impuestos, servicios y reparaciones, y depreciar esa parte. Los montos aquí son antes de impuestos. Hable con un preparador de impuestos antes de empezar.", U_IRS),
    ("**Tenants who can't qualify for a normal lease** (credit, documents or income problems) are a higher risk of missed rent, and a missed month still needs a court case to end. Use a written agreement, ID check, a deposit within the legal limit (NY: 1 month; NJ: 1.5 months), receipts for every payment, and a clear house-rules page. Treat applicants equally and never refuse by race, national origin, religion, family status or other protected reasons; city and state laws can be stricter than federal ones.",
     "**Inquilinos que no califican para un contrato normal** (problemas de crédito, documentos o ingresos) tienen más riesgo de no pagar, y un mes sin pagar igual necesita un caso en corte. Use contrato escrito, verificación de identidad, un depósito dentro del límite legal (NY: 1 mes; NJ: 1.5 meses), recibos de cada pago y una hoja de reglas de la casa. Trate igual a todos los solicitantes y nunca rechace por raza, origen nacional, religión, situación familiar u otras razones protegidas; las leyes de la ciudad y del estado pueden ser más estrictas que las federales.", None),
]

# name, how payment works (en/es), fees (en/es), notes (en/es), url
PLATFORMS = [
    ("SpareRoom (USA)",
     "Listing and matching only. Does NOT collect rent or deposits (it says it never will). Pay tenant directly.", "Solo anuncios y contactos. NO cobra renta ni depósitos (dice que nunca lo hará). Se le paga directo.",
     "Free ad. Paid boost $14/7 days, $25/14, $28/28, $149/6 months, $199/year. ID verification $15 for 12 months.", "Anuncio gratis. Impulso pagado $14/7 días, $25/14, $28/28, $149/6 meses, $199/año. Verificación de identidad $15 por 12 meses.",
     "Active in NY and NJ (Hudson County, NYC pages). Landlords and live-in owners welcome; no credit check.", "Activa en NY y NJ (Condado Hudson, páginas de NYC). Sirve a dueños que viven en la casa; sin revisión de crédito.",
     "https://www.spareroom.com/content/info-faq/how-the-site-works/"),
    ("Roomies.com",
     "Listing site. No in-app rent collection found.", "Sitio de anuncios. No se encontró cobro de renta en la app.",
     "ID check $5, credit check $10 (needs SSN), background check $15 (via Certn/Stripe). Listing price not verified.", "Verificación de identidad $5, crédito $10 (pide SSN), antecedentes $15 (vía Certn/Stripe). Precio de anuncio no verificado.",
     "Says it is the largest US roommate finder; shows rooms in many states. NY/NJ coverage not checked.", "Dice ser el mayor buscador de compañeros de cuarto en EE. UU. Cobertura NY/NJ no verificada.",
     "https://www.roomies.com/verifications"),
    ("Roommates.com",
     "Listing and messaging app. No in-app rent collection found.", "App de anuncios y mensajes. No se encontró cobro de renta en la app.",
     "Paid plans (App Store): 7 days $7, 30 days $14, 6 months $40, 1 year $56; ID verification $3.99, free with a paid plan.", "Planes pagados (App Store): 7 días $7, 30 días $14, 6 meses $40, 1 año $56; verificación $3.99, gratis con plan pagado.",
     "Nationwide US. Auto-renews until cancelled.", "En todo EE. UU. Se renueva solo hasta cancelar.",
     "https://apps.apple.com/us/app/roommates-com/id6741871869"),
    ("Roomster",
     "Marketplace. Rent, deposit and terms are arranged directly with the tenant (its own guide says so).", "Mercado de anuncios. La renta, depósito y términos se arreglan directo con el inquilino (su propia guía lo dice).",
     "Posting a room is free; messaging beyond the basics may need a weekly/monthly subscription. Free ID and address validation.", "Publicar un cuarto es gratis; más mensajes pueden requerir suscripción semanal o mensual. Validación de identidad y dirección gratis.",
     "Active in the US. You are responsible for local taxes, permits and fair-housing laws (its terms).", "Activa en EE. UU. Usted es responsable de impuestos, permisos y leyes de vivienda justa (según sus términos).",
     "https://roomster.com/how-roomster-works"),
    ("Roomi",
     "Says it supports in-app booking and payment (\"get paid with a seamless in-app booking system\").", "Dice tener reservas y pagos dentro de la app (\"cobre con un sistema de reservas en la app\").",
     "Reported 1-10% fee when booked online (a 2017-era investor profile; current fee not verified). ID/background checks are paid.", "Se reportó 1-10% si se reserva en línea (perfil para inversionistas de 2017; cargo actual no verificado). Verificaciones pagadas.",
     "Still on the App Store (Roomi Inc.) and NYC listings were updated in Sept 2026, but its rating is 2.1/5 and reviewers call it a \"ghost town\". Verify before relying on it.", "Sigue en la App Store (Roomi Inc.) y había anuncios de NYC actualizados en sept 2026, pero su calificación es 2.1/5 y usuarios dicen que está vacía. Verifique antes de depender de ella.",
     "https://apps.apple.com/us/app/roommates-by-roomi/id690346626"),
    ("Furnished Finder",
     "Listing site for 30+ day furnished stays. Optional online payments (Baselane, bank transfer). Otherwise tenant pays you directly.", "Sitio para estadías amuebladas de 30+ días. Pagos en línea opcionales (Baselane, transferencia). Si no, el inquilino le paga directo.",
     "$199 a year per listing (a private room counts), $149 per extra unit. No commission. Auto-renews.", "$199 al año por anuncio (un cuarto cuenta), $149 por unidad extra. Sin comisión. Se renueva solo.",
     "Aimed at traveling nurses and workers, not at people without documents or credit.", "Dirigido a enfermeras y trabajadores que viajan, no a personas sin documentos o crédito.",
     "https://support.furnishedfinder.com/hc/en-us/articles/43700974504475-Furnished-Finder-2026-Pricing-and-FAQs"),
    ("Airbnb (monthly / 28+ nights)",
     "Pays through Airbnb. Stays over 28 nights: first 30 nights paid 24 h after check-in, then monthly installments.", "Se cobra por Airbnb. Estadías de más de 28 noches: primeras 30 noches 24 h después de llegar, luego cuotas mensuales.",
     "Host-only fee 15.5% (the old ~3% split-fee is being phased out).", "Cargo al anfitrión 15.5% (el cargo dividido de ~3% se está eliminando).",
     "Verifies guest identity, but hosts can't run a credit check. NYC: whole-home stays under 30 days are illegal; a host-present room under 30 days needs Local Law 18 registration.", "Verifica la identidad del huésped, pero el anfitrión no puede revisar crédito. NYC: toda la casa por menos de 30 días es ilegal; un cuarto con anfitrión presente por menos de 30 días requiere registro (Ley Local 18).",
     "https://www.airbnb.com/help/article/1857"),
    ("Zillow Rental Manager",
     "Free online rent collection (one-time and recurring) for landlords; renters may pay processing fees.", "Cobro de renta en línea gratis para el dueño (único y recurrente); el inquilino puede pagar cargos de proceso.",
     "Listing free (rooms allowed); premium $39.99 for up to 90 days. Screening free for you: renter pays $35 (credit + background).", "Anuncio gratis (acepta cuartos); premium $39.99 por hasta 90 días. Revisión gratis para usted: el inquilino paga $35 (crédito + antecedentes).",
     "Lease builder not offered in NY or NJ (you upload your own). A credit check screens out the people you want to help.", "El generador de contratos no está en NY ni NJ (sube el suyo). Una revisión de crédito deja fuera a la gente que usted quiere ayudar.",
     "https://help.zillowrentalmanager.com/hc/en-us/articles/360021666594-Paying-for-your-Zillow-Rental-Manager-listings"),
    ("Apartments.com Rental Manager",
     "Online rent collection: bank (ACH) free; card/Apple Pay/Google Pay carries a 2.75% fee paid by the tenant.", "Cobro en línea: banco (ACH) gratis; tarjeta/Apple Pay/Google Pay con cargo de 2.75% que paga el inquilino.",
     "Basic listing free (rooms allowed); premium ads cost extra.", "Anuncio básico gratis (acepta cuartos); anuncios premium cuestan extra.",
     "Fee figures are from Apartments.com's search summary; the page itself timed out when fetched. Verify on the site.", "Las cifras vienen del resumen de búsqueda de Apartments.com; la página no cargó al consultarla. Verifique en el sitio.",
     "https://www.apartments.com/rental-manager/online-rent-collection"),
    ("Avail (Realtor.com)",
     "Online rent collection with autopay, late fees and income tracking; deposits to you in 3-5 business days.", "Cobro en línea con pago automático, recargos y registro de ingresos; el dinero llega en 3-5 días hábiles.",
     "Free plan: tenant pays $2.50 per bank transfer or 3.5% on card. Unlimited Plus $9 per unit/month. Screening paid by applicant or you (about $30-$75).", "Plan gratis: el inquilino paga $2.50 por transferencia o 3.5% con tarjeta. Unlimited Plus $9 por unidad/mes. La revisión la paga el solicitante o usted (unos $30-$75).",
     "Active (not discontinued). Built for whole units; usable for a room with a written agreement.", "Activa (no descontinuada). Hecha para unidades completas; sirve para un cuarto con contrato escrito.",
     "https://www.avail.com/education/articles/should-you-collect-rent-with-zelle-venmo-paypal-or-avail"),
    ("PadSplit",
     "Pays through PadSplit: residents pay weekly in the app, you get a monthly payout. Handles screening and collection.", "Se paga por PadSplit: los residentes pagan cada semana en la app, usted recibe un pago mensual. Hace la revisión y el cobro.",
     "100% of a new member's first 10 days + 8% of all payments.", "100% de los primeros 10 días de cada miembro nuevo + 8% de todos los pagos.",
     "No minimum credit score, which fits your goal. Announced its New York metro launch on Oct 1, 2026 and is seeking owner-occupied homes; check whether your address is served and whether your zoning/building allows a shared-room model.", "No pide puntaje de crédito mínimo, lo cual encaja con su meta. Anunció su llegada al área de Nueva York el 1 de oct de 2026 y busca casas ocupadas por su dueño; verifique si atienden su dirección y si el zonificado/edificio permite el modelo.",
     "https://www.padsplit.com/help/article/what-is-padsplits-fee-model-for-hosts-24614775906324"),
    ("Craigslist (rooms & shares)",
     "No payments in the site. Cash/Zelle/check directly.", "Sin pagos en el sitio. Efectivo/Zelle/cheque directo.",
     "Rooms & shares: free. NYC apartment ads: $5.", "Cuartos y compartidos: gratis. Anuncios de apartamentos en NYC: $5.",
     "No screening or protection; scams are common, so meet in person and verify ID.", "Sin revisión ni protección; las estafas son comunes: reúnase en persona y verifique la identidad.",
     "https://www.craigslist.org/about/help/posting_fees"),
    ("Facebook (Marketplace / groups)",
     "No payments for rentals. Direct only; Facebook doesn't protect rental deposits.", "Sin pagos para alquileres. Solo directo; Facebook no protege depósitos de renta.",
     "Free.", "Gratis.",
     "No identity or ownership checks; Meta removes some housing posts for fair-housing reasons (secondary sources, not Meta's own page). Good for community groups, risky for money.", "Sin verificación de identidad ni de propiedad; Meta quita algunas publicaciones de vivienda por razones de vivienda justa (fuentes secundarias). Útil en grupos de la comunidad, riesgoso con dinero.",
     "https://scamencyclopedia.org/guides/rental-scams-on-facebook-marketplace"),
    ("Bungalow, Common (co-living)",
     "DEFUNCT. Not available.", "YA NO EXISTEN. No disponibles.",
     "n/a", "n/a",
     "Bungalow wound down its co-living business in early 2023; Common stopped operating in June 2024 (Chapter 7). Don't plan around them.", "Bungalow cerró su negocio de co-living a inicios de 2023; Common dejó de operar en junio de 2024 (Capítulo 7). No cuente con ellas.",
     "https://www.multifamilyexecutive.com/news/common-living-to-cease-operations-immediately_o"),
    ("Flatmates.com.au",
     "Australian service. Not for NY/NJ.", "Servicio de Australia. No sirve para NY/NJ.",
     "n/a", "n/a",
     "Its app appears in the US App Store but serves Australian listings and Australian ID only.", "Su app aparece en la App Store de EE. UU. pero sirve anuncios y documentos de Australia.",
     "https://apps.apple.com/us/app/flatmates/id1489897686"),
]
