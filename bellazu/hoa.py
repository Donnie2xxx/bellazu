"""Monthly HOA / condo fee / co-op maintenance for a listing.

Where it comes from (checked on real Realty-in-US payloads, Sep 2026):
  * the search list (/properties/v3/list) never carries it (0 of 1,724 NJ listings had hoa);
  * the detail call (/properties/v3/detail) has it in up to four places, best first:
      home.hoa.fee                                        (monthly, when the MLS feed maps it)
      home.details[category="Homeowners Association"]     "Calculated Total Monthly Association Fees: 883",
                                                           "Association Fee: 365" + "Association Fee Frequency: Monthly",
                                                           "Maintenance Expense: 775" (co-ops), "Association: No"
      home.mortgage.estimate.monthly_payment_details      type hoa_fees (same number as hoa.fee, 0 when unknown)
      home.description.text                               "Low HOA fees of $255/month", "The monthly maintenance is $1,555"
  * what the fee covers: "Association Amenities: Taxes, Heat, Water" / "Maintenance Description: Common Area,Taxes".
When none of these has a number: houses and multi-family -> "No HOA (typical for houses)"; condos, co-ops and townhomes ->
an estimate from the median of real fees we have seen for the same kind of home in the same ZIP / town / area, labeled est.
"""
import json, pathlib, re, statistics, threading, time

HOA_KINDS = {"condo", "coop", "townhome"}
KIND_OF = {"condos": "condo", "condo": "condo", "condo_townhome": "condo", "condo_townhome_rowhome_coop": "condo", "apartment": "condo",
           "coop": "coop", "co-op": "coop", "cooperative": "coop", "townhomes": "townhome", "townhouse": "townhome", "townhome": "townhome",
           "single_family": "house", "single-family": "house", "house": "house", "multi_family": "multi", "multi-family": "multi",
           "duplex_triplex": "multi", "2fam": "multi", "2-family": "multi", "3-4-family": "multi"}
LO, HI = 25, 6000          # a monthly fee outside this is a parsing mistake (or a yearly number)
_FREQ = [(r"semi[- ]?annual|semiannual|twice a year|half[- ]year", 1 / 6), (r"quarter|qtr", 1 / 3),
         (r"annual|yearly|year|yr|annum", 1 / 12), (r"month|mo\b|mthly|monthly", 1.0)]
_INC = [("taxes", r"tax"), ("heat/hot water", r"heat|hot water|gas"), ("utilities", r"electric|all utilities"), ("water", r"water|sewer"),
        ("parking", r"parking|garage"), ("internet", r"internet|cable")]


def kind_of(t):
    return KIND_OF.get(str(t or "").strip().lower(), "other")


def _num(s):
    m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", str(s or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _freq(s, default=1.0):
    s = str(s or "").lower()
    for pat, k in _FREQ:
        if re.search(pat, s):
            return k
    return default


def _ok(v):
    return v is not None and LO <= v <= HI


def _includes(txts):
    t = " ".join(txts).lower()
    return [k for k, pat in _INC if re.search(pat, t)]


_TXT = re.compile(r"(?P<pre>monthly|quarterly|annual|yearly)?\s*(?P<k>h\.?o\.?a\.?(?:\s+(?:fees?|dues))?|association\s+(?:fees?|dues)|common\s+charges?|"
                  r"condo\s+fees?|maintenance(?:\s+fees?)?|monthly\s+fees?|monthly\s+charges?)"
                  r"(?P<gap>[^$.\d\n]{0,28})\$\s?(?P<v>[\d,]{2,7}(?:\.\d{1,2})?)\s*(?P<f>(?:/|per|a|each|every)\s*(?:mo(?:nth)?|month|quarter|qtr|year|yr|annum)|"
                  r"monthly|quarterly|annually|yearly|a\s+month)?", re.I)


def from_text(text):
    """(monthly fee, label, phrase) from listing text, or (None, None, None)."""
    for m in _TXT.finditer(text or ""):
        v = _num(m.group("v"))
        if v is None or re.search(r"parking|garage|storage|pet|transfer|capital|assessment|move|application|initiation|one[- ]time|special", m.group("gap"), re.I):
            continue
        f = _freq((m.group("f") or "") + " " + (m.group("pre") or ""), 1.0)
        mv = v * f
        if _ok(mv):
            k = m.group("k").lower()
            return round(mv), ("maintenance" if "maint" in k else "hoa"), m.group(0).strip()[:80]
    return None, None, None


def parse_detail(home, list_type=None):
    """Everything we can learn about the monthly fee from one /properties/v3/detail 'home' object (no API call).
    -> {"fee", "src", "label" ('hoa'|'maintenance'), "inc", "none", "kind"}; fee is monthly USD or None."""
    h = home or {}
    de = h.get("description") or {}
    kind = kind_of(list_type) if kind_of(list_type) != "other" else kind_of(de.get("type"))
    txt = de.get("text") or ""
    if kind == "condo" and re.search(r"\bco-?op\b|cooperative", txt, re.I) and not re.search(r"\bcondo", txt, re.I):
        kind = "coop"
    sec = {}
    for d in h.get("details") or []:
        if str(d.get("category") or "").lower().startswith("homeowners association"):
            for line in d.get("text") or []:
                k, _, v = str(line).partition(":")
                sec[k.strip().lower()] = v.strip()
    out = {"fee": None, "src": None, "label": "maintenance" if kind == "coop" else "hoa", "inc": [], "none": False, "kind": kind}
    out["inc"] = _includes([sec.get("association amenities", ""), sec.get("maintenance description", ""), sec.get("association fee includes", "")])
    if kind == "condo" and "taxes" in out["inc"]:      # NJ condo owners pay their own tax bill; a fee that covers taxes is co-op maintenance
        out["kind"] = kind = "coop"
        out["label"] = "maintenance"
    hf = (h.get("hoa") or {}).get("fee") if isinstance(h.get("hoa"), dict) else None
    tot = _num(sec.get("calculated total monthly association fees"))
    af = _num(sec.get("association fee"))
    mx = next((_num(v) for k, v in sec.items() if re.search(r"maintenance (expense|fee)|common charge|condo fee|co-?op (fee|maintenance)", k) and _num(v)), None)
    mort = next((x.get("amount") for x in (((h.get("mortgage") or {}).get("estimate") or {}).get("monthly_payment_details") or [])
                 if x.get("type") == "hoa_fees"), None)
    cands = [(hf, "listing: HOA fee field"), (tot, "listing: HOA section (monthly total)"),
             (af * _freq(sec.get("association fee frequency"), 1.0) if af else None, "listing: HOA section"),
             (mx * _freq(sec.get("maintenance frequency") or sec.get("maintenance expense frequency"), 1.0) if mx else None, "listing: maintenance"),
             (mort, "listing: realtor.com payment estimate")]
    for v, s in cands:
        if _ok(v):
            out["fee"], out["src"] = round(float(v)), s
            if s == "listing: maintenance":
                out["label"] = "maintenance"
            break
    if out["fee"] is None:
        v, lab, phrase = from_text(txt)
        if v:
            out["fee"], out["src"] = v, f"listing description (“{phrase}”)"
            if lab == "maintenance" and kind == "coop":
                out["label"] = "maintenance"
    if out["fee"] is None and sec.get("association", "").lower() in ("no", "n", "none"):
        out["none"] = True
    if not out["inc"] and txt:
        m = re.search(r"(?:maintenance|hoa|association fees?|common charges?)\s+(?:fee\s+)?(?:includes?|incl\.?|covers)\s*:?\s*([^.]{0,160})", txt, re.I)
        if m:
            out["inc"] = _includes([m.group(1)])
    return out


# ------------------------------------------------------------------ what we have seen: real fees by kind / town / ZIP
_LOCK = threading.Lock()


def _obs_path(dir_):
    return pathlib.Path(dir_) / "hoa_obs.json"


def load_obs(dir_, seed=None):
    obs = {}
    if seed and pathlib.Path(seed).exists():
        try:
            obs.update(json.loads(pathlib.Path(seed).read_text()))
        except Exception:
            pass
    try:
        obs.update(json.loads(_obs_path(dir_).read_text()))
    except Exception:
        pass
    return obs


def add_obs(dir_, pid, town, zip_, kind, fee, sqft=None, beds=None):
    if not (pid and fee and kind in HOA_KINDS):
        return
    with _LOCK:
        p = _obs_path(dir_)
        try:
            d = json.loads(p.read_text())
        except Exception:
            d = {}
        d[str(pid)] = {"town": town, "zip": str(zip_ or ""), "kind": kind, "fee": round(float(fee)), "sqft": sqft, "beds": beds, "t": int(time.time())}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d))


def estimate(obs, town, zip_, kind, sqft=None):
    """Median real fee for the same kind of home (co-ops apart from condos/townhomes), nearest group with enough homes:
    same ZIP (3+), same town (3+), else the whole area (4+). Scaled a little by size when both sizes are known.
    -> {"fee", "n", "where"} or None. Never an exact-looking number: rounded to $25 and always shown as est."""
    grp = "coop" if kind == "coop" else "condo"
    rows = [o for o in obs.values() if ("coop" if o.get("kind") == "coop" else "condo") == grp and o.get("fee")]
    for where, sel, need in ((str(zip_ or ""), [o for o in rows if zip_ and o.get("zip") == str(zip_)], 3),
                             (town, [o for o in rows if town and str(o.get("town") or "").lower() == str(town).lower()], 3),
                             ("area", rows, 4)):
        if len(sel) >= need:
            med = statistics.median(o["fee"] for o in sel)
            ps = [o["fee"] / o["sqft"] for o in sel if o.get("sqft") and 250 <= float(o["sqft"]) <= 5000]
            if sqft and 250 <= float(sqft) <= 5000 and len(ps) >= 3:
                med = min(max(statistics.median(ps) * float(sqft), med * 0.6), med * 1.6)
            return {"fee": int(round(med / 25) * 25), "n": len(sel), "where": where, "kind": grp}
    return None
