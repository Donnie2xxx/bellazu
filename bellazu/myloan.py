"""'My loan': the buyer's own financing, used for every monthly number in the app.

Defaults come from the buyer's pre-approval and the lender's quote (loan numbers only): conventional, 30-year fixed at 7.0%,
max price $300,000, 5% down (at least $15,000), PMI est. 0.55%/yr (about right for a ~730 score at 95% LTV), lender's qualifying
figures: home insurance $1,200/yr and property taxes $4,000/yr. FHA at the lender's 6.8% stays a one-tap toggle
(1.75% upfront MIP financed + 0.55%/yr; 3.5% is the FHA minimum down). All of it is editable in My settings and saved with the list.
"""
from .finance import pmt

DEFAULT = {"v": 3,                   # profiles saved before v3 fall back to these defaults
           "kind": "conv", "down_pct": 0.05, "min_down": 15_000, "max_price": 300_000, "term": 30,
           "rate": 7.0, "rate_src": "lender",           # conventional rate; 'lender' = quoted by the lender, 'you' = edited, None = market average (est.)
           "fha_rate": 6.8, "fha_rate_src": "lender",   # FHA rate, used when the FHA toggle is on
           "pmi_pct": 0.0055,        # conventional PMI at 95% LTV with a ~730 score: about 0.5-0.6%/yr of the loan, est.
           "closing_pct": 0.035,     # NJ/NY buyer closing costs ~3-4% of the price, est.
           "ins_m": 100,             # lender's figure: $1,200/yr
           "tax_y": 4_000}           # lender's figure, used only when a listing's real tax bill is unknown
FHA = {"down_pct": 0.035, "ufmip": 0.0175, "mip": 0.0055}   # 3.5% = FHA minimum down; upfront MIP financed; annual MIP on the base loan


def prof(p=None):
    d = dict(DEFAULT)
    p = p or {}
    if (p.get("v") or 0) < DEFAULT["v"]:
        return d
    d.update({k: v for k, v in p.items() if k in DEFAULT and (v is not None or k in ("rate", "fha_rate"))})
    return d


def rate_keys(kind):
    return ("fha_rate", "fha_rate_src") if kind == "fha" else ("rate", "rate_src")


def rate_of(p, market):
    """The rate for the profile's loan type (FHA and conventional each keep their own)."""
    p = prof(p)
    k = rate_keys(p["kind"])[0]
    return float(p[k]) if p.get(k) else float(market or 7.0)


def down_of(price, p):
    p = prof(p)
    pct = max(p["down_pct"], FHA["down_pct"]) if p["kind"] == "fha" else p["down_pct"]
    return round(min(price, max(price * pct, p["min_down"])))


def loan_costs(price, p, market_rate, min_down_pct=None):
    """Same keys as finance.loan_costs, from My loan. min_down_pct: a floor the home itself needs (e.g. a co-op board's 10-20%)."""
    p = prof(p)
    dn = down_of(price, p)
    kind = p["kind"]
    if min_down_pct and dn < price * min_down_pct:
        dn, kind = round(price * min_down_pct), "conv"
    r = rate_of(dict(p, kind=kind), market_rate)
    base = max(price - dn, 0)
    if kind == "fha":
        loan = base * (1 + FHA["ufmip"])
        mi = base * FHA["mip"] / 12
    else:
        loan = base
        mi = loan * p["pmi_pct"] / 12 if price and dn / price < 0.20 else 0
    cc = price * p["closing_pct"]
    return {"down_payment": round(dn), "down_pct": dn / price if price else 0, "loan_amount": round(loan), "rate_pct": round(r, 3), "term": p["term"],
            "principal_interest": round(pmt(loan, r, p["term"])), "mortgage_insurance": round(mi), "closing_costs_est": round(cc),
            "cash_to_close_est": round(dn + cc), "kind": kind}


def monthly(price, p, market_rate, taxes_annual=None, hoa=0, taxes_in_hoa=False, min_down_pct=None):
    """The real monthly cost of one home with My loan: P&I + PMI/MIP + tax + insurance + HOA/maintenance."""
    p = prof(p)
    lc = loan_costs(price, p, market_rate, min_down_pct)
    if taxes_in_hoa:
        tax, tsrc = 0, "in"
    elif taxes_annual:
        tax, tsrc = float(taxes_annual) / 12, "listing"
    else:
        tax, tsrc = p["tax_y"] / 12, "lender"
    parts = {"pi": lc["principal_interest"], "mi": lc["mortgage_insurance"], "tax": round(tax), "ins": round(p["ins_m"]), "hoa": round(float(hoa or 0))}
    return {**parts, "total": sum(parts.values()), "tax_src": tsrc, "loan": lc}


def approved(p, market_rate):
    """The benchmark monthly payment: at the lender's max price with the active loan type (its down payment, rate and PMI/MIP),
    the lender's $4,000/yr taxes and $1,200/yr insurance, no HOA."""
    p = prof(p)
    return monthly(p["max_price"], p, market_rate, taxes_annual=p["tax_y"], hoa=0)


def tag(price, total, p, appr_total):
    """'ok' (price <= max and monthly <= approved), 'monthly' (price ok, monthly higher), 'over' (price above the approval)."""
    p = prof(p)
    if not price:
        return None
    if price > p["max_price"]:
        return "over"
    return "ok" if total <= appr_total + 0.5 else "monthly"
