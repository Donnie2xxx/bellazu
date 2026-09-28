"""Pure functions: mortgage math + scenario cash flows. All monthly USD."""
from .config import by_beds


def pmt(principal, annual_rate_pct, years):
    r = annual_rate_pct / 100 / 12
    n = years * 12
    return principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)


def loan_costs(price, down_pct, rate_pct, years, fha=False, A=None):
    f = A["financing"]
    base = price * (1 - down_pct)
    loan = base * (1 + f["fha_upfront_mip_pct"]) if fha else base
    pi = pmt(loan, rate_pct, years)
    mi = base * f["fha_annual_mip_pct"] / 12 if fha else (base * f["pmi_annual_pct_if_lt20"] / 12 if down_pct < 0.20 else 0)
    return {"down_payment": round(price * down_pct), "loan_amount": round(loan), "rate_pct": round(rate_pct, 3),
            "principal_interest": round(pi), "mortgage_insurance": round(mi),
            "closing_costs_est": round(price * f["closing_cost_pct"]),
            "cash_to_close_est": round(price * down_pct + price * f["closing_cost_pct"])}


def carrying_costs(facts, A, occupied_by="owner"):
    """Monthly non-mortgage costs of owning the unit."""
    oc = A["ownership_costs"]
    price = float(facts.get("price") or 0)
    inc = [x.lower() for x in (facts.get("hoa_includes") or [])]
    hoa = float(facts.get("hoa_monthly") or 0)
    notes = []
    if "taxes" in inc:
        tax = 0.0
        notes.append("Property taxes are included in the maintenance fee (co-op).")
    elif facts.get("taxes_annual"):
        tax = float(facts["taxes_annual"]) / 12
    elif oc.get("property_tax_fallback_annual"):      # My loan: the lender's qualifying tax figure when the real bill is unknown
        tax = float(oc["property_tax_fallback_annual"]) / 12
        notes.append(f"TAXES UNKNOWN: using the lender's ${oc['property_tax_fallback_annual']:,.0f}/yr — replace with the real tax bill.")
    else:
        tax = price * oc["property_tax_rate_fallback"] / 12
        notes.append(f"TAXES UNKNOWN: using fallback {oc['property_tax_rate_fallback']:.1%} of price — replace with the real tax bill.")
    ins = oc["ho6_insurance_monthly"] if occupied_by == "owner" else oc["landlord_policy_monthly"]
    util = 0 if "utilities" in inc else by_beds(oc["utilities_owner_monthly_by_beds"], facts.get("beds"))
    reserve = price * oc["maintenance_reserve_pct_of_price"] / 12
    return {"hoa_or_maintenance": round(hoa), "property_tax": round(tax), "insurance": round(ins),
            "utilities": round(util), "repairs_reserve": round(reserve)}, notes


def str_operating(annual_revenue, booked_nights, beds, A, utilities_included=False):
    s = A["str"]
    turns = booked_nights / max(s["avg_stay_nights"], 1)
    m = {
        "platform_fees": annual_revenue * s["platform_fee_pct"] / 12,
        "cleaning": turns * by_beds(s["cleaning_cost_per_turn_by_beds"], beds) / 12,
        "supplies": booked_nights * s["supplies_per_booked_night"] / 12,
        "utilities": 0 if utilities_included else by_beds(s["utilities_monthly_by_beds"], beds),
        "str_insurance": s["insurance_monthly"],
        "furnishing_amortized": by_beds(s["furnishing_cost_by_beds"], beds) / s["furnishing_amortization_months"],
        "repairs": annual_revenue * s["repairs_pct_of_revenue"] / 12,
        "software": s["software_monthly"],
        "permits": s["permit_fees_annual"] / 12,
    }
    return {k: round(v) for k, v in m.items()}


def mtr_operating(monthly_rate, beds, A):
    t = A["mtr"]
    s = A["str"]
    gross = monthly_rate * t["occupancy"]
    m = {"platform_fees": gross * t["platform_fee_pct"],
         "cleaning": t["turnovers_per_year"] * by_beds(s["cleaning_cost_per_turn_by_beds"], beds) / 12,
         "utilities": by_beds(t["utilities_monthly_by_beds"], beds),
         "insurance": t["insurance_monthly"],
         "furnishing_amortized": by_beds(s["furnishing_cost_by_beds"], beds) / s["furnishing_amortization_months"]}
    return round(gross), {k: round(v) for k, v in m.items()}
