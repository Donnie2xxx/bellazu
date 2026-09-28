"""'My loan': the buyer's own financing, used for every monthly number in the app.

Defaults come from the buyer's pre-approval and the lender's confirmed terms (loan numbers only): FHA, 30-year fixed at 6.8%,
max price $300,000, 5% down ($15,000 at the max price), lender's qualifying figures: home insurance $1,200/yr and property taxes
$4,000/yr. FHA: 1.75% upfront MIP financed into the loan + 0.55%/yr annual MIP; 3.5% is the FHA minimum down (editable).
A conventional loan (with PMI) stays available as a toggle. All of it is editable in My settings and saved with the buyer's list.
"""
from .finance import pmt

DEFAULT = {"v": 2,                   # profiles saved before v2 (conventional + market rate) fall back to these defaults
           "kind": "fha", "down_pct": 0.05, "min_down": 15_000, "max_price": 300_000, "term": 30,
           "rate": 6.8, "rate_src": "lender",   # 'lender' = confirmed by the lender; 'you' = edited; None rate = market average (est.)
           "pmi_pct": 0.0065,        # only for the conventional toggle: PMI at 95% LTV, roughly 0.5-0.8%/yr of the loan by credit score; midpoint, est.
           "closing_pct": 0.035,     # NJ/NY buyer closing costs ~3-4% of the price, est.
           "ins_m": 100,             # lender's figure: $1,200/yr
           "tax_y": 4_000}           # lender's figure, used only when a listing's real tax bill is unknown
FHA = {"down_pct": 0.035, "ufmip": 0.0175, "mip": 0.0055}   # 3.5% = FHA minimum down; upfront MIP financed; annual MIP on the base loan


def prof(p=None):
    d = dict(DEFAULT)
    p = p or {}
    if (p.get("v") or 0) < DEFAULT["v"]:
        return d
    d.update({k: v for k, v in p.items() if k in DEFAULT and (v is not None or k == "rate")})
    return d


def rate_of(p, market):
    p = prof(p)
    return float(p["rate"]) if p.get("rate") else float(market or 7.0)


def down_of(price, p):
    p = prof(p)
    pct = max(p["down_pct"], FHA["down_pct"]) if p["kind"] == "fha" else p["down_pct"]
    return round(min(price, max(price * pct, p["min_down"])))


def loan_costs(price, p, market_rate, min_down_pct=None):
    """Same keys as finance.loan_costs, from My loan. min_down_pct: a floor the home itself needs (e.g. a co-op board's 10-20%)."""
    p = prof(p)
    r = rate_of(p, market_rate)
    dn = down_of(price, p)
    kind = p["kind"]
    if min_down_pct and dn < price * min_down_pct:
        dn, kind = round(price * min_down_pct), "conv"
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
    """The monthly payment the lender qualified: at the max price with the approved loan (FHA, the profile's down payment and rate),
    the lender's $4,000/yr taxes and $1,200/yr insurance, no HOA."""
    p = prof(p)
    q = dict(p, kind=DEFAULT["kind"])
    return monthly(p["max_price"], q, market_rate, taxes_annual=p["tax_y"], hoa=0)


def tag(price, total, p, appr_total):
    """'ok' (price <= max and monthly <= approved), 'monthly' (price ok, monthly higher), 'over' (price above the approval)."""
    p = prof(p)
    if not price:
        return None
    if price > p["max_price"]:
        return "over"
    return "ok" if total <= appr_total + 0.5 else "monthly"
