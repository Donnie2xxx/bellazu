T = {
    "prop_title": ("BellaZu Property Report", "Reporte de Propiedad BellaZu"),
    "arb_title": ("BellaZu Arbitrage Scan", "Análisis de Arbitraje BellaZu"),
    "generated": ("Generated", "Generado"),
    "bottom_line": ("Bottom line", "En resumen"),
    "facts": ("Listing facts", "Datos del anuncio"),
    "field": ("Field", "Dato"), "value": ("Value", "Valor"), "source": ("Source", "Fuente"),
    "price": ("Price", "Precio"), "beds": ("Bedrooms", "Habitaciones"), "baths": ("Bathrooms", "Baños"),
    "sqft": ("Square feet", "Pies cuadrados"), "hoa_monthly": ("HOA / maintenance (monthly)", "HOA / mantenimiento (mensual)"),
    "taxes_annual": ("Property taxes (annual)", "Impuestos (anual)"), "ownership": ("Ownership type", "Tipo de propiedad"),
    "hoa_includes": ("Maintenance includes", "El mantenimiento incluye"), "status": ("Status", "Estado"), "year_built": ("Year built", "Año de construcción"),
    "legality": ("Short-term rental (Airbnb) legality", "Legalidad de alquiler a corto plazo (Airbnb)"),
    "building_policy": ("Building rental / sublet policy", "Política de alquiler / subarriendo del edificio"),
    "ltr": ("Long-term rent estimate", "Estimado de renta a largo plazo"),
    "rooms": ("Room-rent comps (roommates)", "Comparables de renta por cuarto (compañeros)"),
    "str": ("Short-term rental comps (Inside Airbnb)", "Comparables de alquiler a corto plazo (Inside Airbnb)"),
    "scen": ("Monthly cash flow", "Flujo de caja mensual"),
    "assump": ("Key assumptions (edit assumptions.yaml)", "Supuestos clave (editar assumptions.yaml)"),
    "sources": ("Data sources used", "Fuentes de datos usadas"),
    "warnings": ("Warnings", "Advertencias"),
    "fha": ("FHA eligibility", "Elegibilidad FHA"),
    "benchmarks": ("Benchmarks", "Referencias"),
    "median": ("median", "mediana"), "range": ("range (25th-75th pct)", "rango (percentil 25-75)"),
    "net": ("NET per month", "NETO por mes"), "total_cost": ("Total monthly cost", "Costo mensual total"),
    "cash_to_close": ("Cash to close (est.)", "Efectivo para cerrar (est.)"),
    "not_legal": ("Not legal here — not computed", "No es legal aquí — no calculado"),
    "disclaimer": ("Educational estimate from free public data, not financial, legal or lending advice. Verify every number (listing agent, lender, co-op/condo board, town zoning office) before acting.",
                   "Estimado educativo con datos públicos gratuitos; no es asesoría financiera, legal ni hipotecaria. Verifique cada número (agente, prestamista, junta de co-op/condominio, oficina de zonificación) antes de actuar."),
    "ranked": ("Rentals ranked by estimated STR profit", "Alquileres ordenados por ganancia STR estimada"),
    "by_beds": ("Summary by bedrooms", "Resumen por habitaciones"),
    "caveats": ("Caveats", "Advertencias"),
    "manual": ("Manual / browser steps that improve this report", "Pasos manuales / con navegador que mejoran este reporte"),
}
COST = {
    "principal_interest": ("Principal & interest", "Capital e intereses"), "mortgage_insurance": ("Mortgage insurance (MIP/PMI)", "Seguro hipotecario (MIP/PMI)"),
    "hoa_or_maintenance": ("HOA / maintenance", "HOA / mantenimiento"), "property_tax": ("Property tax", "Impuesto predial"),
    "insurance": ("Insurance", "Seguro"), "utilities": ("Utilities", "Servicios"), "repairs_reserve": ("Repairs reserve", "Reserva de reparaciones"),
    "platform_fees": ("Platform fees", "Comisiones de plataforma"), "cleaning": ("Cleaning", "Limpieza"), "supplies": ("Supplies", "Suministros"),
    "str_insurance": ("STR insurance", "Seguro STR"), "furnishing_amortized": ("Furniture (amortized)", "Muebles (amortizados)"),
    "repairs": ("Repairs", "Reparaciones"), "software": ("Software", "Software"), "permits": ("Permits", "Permisos"),
}


def t(k, lang):
    v = T.get(k) or COST.get(k) or (k, k)
    return v[0] if lang == "en" else v[1]
