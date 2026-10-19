"""After-repair value (ARV) from comparable homes, for the 'If I fix it up' section of a listing.

Comps are RECENT SALES (Realty in US sold list, last 12 months, one cached call per town) when there are enough, else the ACTIVE
listings we already have saved (asking prices, labeled as such). Same building comps are picked by street number + street name.
Nearby = same kind of home, similar beds/baths/size, within 0.5 mi (widening to 1 and 2 mi, then the town, when there are too few).
The 'nicer / fixed-up' units are the top quarter of the comps by price per sq ft. ARV = this unit's sq ft x that price per sq ft.
It is a rough estimate: it leaves out rehab cost, HOA, closing, holding and selling costs.

Same-building units are only compared when they are about the same size as this unit (`size_match`):
  exact   = the same listed sq ft;
  similar = within ±10% of this unit's sq ft or ±100 sq ft, whichever is larger (e.g. 900 ft² -> 800-1,000; 1,500 ft² -> 1,350-1,650).
Only those (the "matched" set, exact first, then same bedroom count, then closest size) feed the stats and lead the list. Units of a
different size, or with no size listed, go to a separate "other sizes" group that is never used in the estimate. When this unit has no
size listed, units with the same bedroom count are the matched set instead (basis "beds", labeled as such in the app).
"""
import datetime as dt
import math
import re

from . import hoa as _hoa
from .sources import fha as _fha

APT = {"condo", "coop"}
SELL_COST = 0.06
RADII = (0.5, 1.0, 2.0)
SIZE_PCT, SIZE_ABS = 0.10, 100     # "similar size" = within ±10% or ±100 sq ft, whichever is larger
MIN_N = 4                       # comps with a usable price per sq ft (or price) needed for an estimate
CUES = [("reno", r"renovat|remodel|gut(ted)?\b|rehab(bed)?\b|newly (updated|done)", ("renovated", "renovado")),
        ("updated", r"\bupdated\b|\bmodern(ized)?\b|\bupgraded\b", ("updated", "actualizado")),
        ("kitchen", r"new kitchen|kitchen (was )?(renovat|remodel|updated)|(granite|quartz|stainless)", ("new kitchen", "cocina nueva")),
        ("bath", r"new bath|bath(room)? (was )?(renovat|remodel|updated)", ("new bath", "baño nuevo")),
        ("floors", r"new floor|refinished (hardwood )?floor|brand new floor", ("new floors", "pisos nuevos")),
        ("turnkey", r"turn[- ]?key|move[- ]in ready|mint condition", ("move-in ready", "listo para mudarse")),
        ("work", r"needs? (some |major |a lot of )?(work|tlc|rehab|renovation|updating)|handyman|fixer|as[- ]is|investor special|contractor special",
         ("needs work", "necesita arreglos"))]


def cue_keys(text):
    t = str(text or "").lower()
    return [k for k, rx, _ in CUES if re.search(rx, t)]


def cue_labels(keys, es=False):
    m = {k: lbl for k, _, lbl in CUES}
    return [m[k][1 if es else 0] for k in keys if k in m]


def miles(a, b, c, d):
    try:
        la1, lo1, la2, lo2 = map(math.radians, (float(a), float(b), float(c), float(d)))
    except Exception:
        return None
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def klass(t):
    k = _hoa.kind_of(t)
    return "apt" if k in APT else k


def street_key(addr):
    n, s = _fha.norm_street(addr)
    return (n, s) if n and s else None


def _q(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def _age_days(d):
    try:
        return (dt.date.today() - dt.date.fromisoformat(str(d)[:10])).days
    except Exception:
        return None


def _ppsf(c):
    return c["price"] / c["sqft"] if c.get("price") and c.get("sqft") and c["sqft"] >= 250 else None


def _similar(s, c):
    """Same class of home, beds within 1, baths within 1, size within -40%/+60% when both are known."""
    if klass(c.get("type")) != s["klass"]:
        return False
    if s.get("beds") is not None and c.get("beds") is not None and abs(int(c["beds"]) - int(s["beds"])) > 1:
        return False
    if s.get("baths") and c.get("baths") and abs(float(c["baths"]) - float(s["baths"])) > 1:
        return False
    if s.get("sqft") and c.get("sqft") and not (0.6 * s["sqft"] <= c["sqft"] <= 1.6 * s["sqft"]):
        return False
    return True


def size_match(s_sqft, c_sqft):
    """'exact' (same listed sq ft), 'similar' (within ±10% or ±100 sq ft, whichever is larger), 'other', or 'unknown' (a size is missing)."""
    try:
        a, b = float(s_sqft or 0), float(c_sqft or 0)
    except (TypeError, ValueError):
        return "unknown"
    if a <= 0 or b <= 0:
        return "unknown"
    if round(a) == round(b):
        return "exact"
    return "similar" if abs(b - a) <= max(SIZE_PCT * a, SIZE_ABS) else "other"


def split_building(bld, s):
    """Same-building units -> (matched, other, basis). basis 'sqft' (exact/similar size) or 'beds' (this unit has no size: same bedroom count).
    Each unit gets c['_size'] ('exact' | 'similar' | 'beds' | 'other' | 'unknown') and c['_size_diff'] (sq ft difference or None)."""
    sq = s.get("sqft")
    basis = "sqft" if sq else "beds"
    matched, other = [], []
    for c in bld:
        if basis == "sqft":
            m = size_match(sq, c.get("sqft"))
            c["_size"], c["_size_diff"] = m, (round(float(c["sqft"]) - float(sq)) if m in ("exact", "similar", "other") else None)
            (matched if m in ("exact", "similar") else other).append(c)
        else:
            same = s.get("beds") is not None and c.get("beds") is not None and int(c["beds"]) == int(s["beds"])
            c["_size"], c["_size_diff"] = ("beds" if same else "other" if c.get("beds") is not None else "unknown"), None
            (matched if same else other).append(c)
    sb = s.get("beds")

    def rank(c):
        tier = 0 if c["_size"] == "exact" else 1
        beds_off = 0 if (sb is not None and c.get("beds") is not None and int(c["beds"]) == int(sb)) else 1
        return (tier, beds_off, abs(c["_size_diff"] or 0), -(c.get("_ppsf") or 0))
    matched.sort(key=rank)
    other.sort(key=lambda c: (c["_size"] == "unknown", abs(c.get("_size_diff") or 0)))
    return matched, other, basis


def _trim(vals):
    """Drop price-per-sq-ft values that are obvious data mistakes (under half or over twice the median)."""
    if len(vals) < 4:
        return vals
    m = _q(vals, .5)
    return [v for v in vals if .5 * m <= v <= 2 * m]


def far_pricier(c, s, use_ppsf):
    """A comp far above this home's own price level (a luxury tower, new build) says little about a fixed-up unit of this kind."""
    if use_ppsf and s.get("price") and s.get("sqft"):
        return bool(c.get("_ppsf") and c["_ppsf"] > 2.0 * s["price"] / s["sqft"])
    return bool(s.get("price") and c.get("price") and c["price"] > 1.8 * s["price"])


def stats(comps, sqft, use_ppsf):
    """Top-quartile stats -> {"n", "top_n", "p75", "med_top", "p90", "low", "mid", "high", "unit"} or None when there are too few comps."""
    vals = _trim([_ppsf(c) for c in comps if _ppsf(c)]) if use_ppsf else [c["price"] for c in comps if c.get("price")]
    if len(vals) < MIN_N:
        return None
    p75 = _q(vals, .75)
    top = [v for v in vals if v >= p75 - 1e-9]
    med_top = _q(top, .5)
    k = sqft if use_ppsf else 1
    return {"n": len(vals), "top_n": len(top), "median": _q(vals, .5), "p75": p75, "med_top": med_top, "top_max": max(top),
            "low": round(p75 * k), "mid": round(med_top * k), "high": round(max(top) * k), "unit": "sqft" if use_ppsf else "price"}


def subject_of(addr, price, beds, baths, sqft, typ, town, lat, lon, pid=None):
    return {"address": addr, "price": price, "beds": beds, "baths": baths, "sqft": sqft, "type": typ, "klass": klass(typ), "town": town,
            "lat": lat, "lon": lon, "id": str(pid or "")}


def _prep(rows, s, sold, cues_of=None):
    out, me = [], (s.get("address") or "").strip().lower()
    for r in rows:
        if not r.get("price") or (r.get("address") or "").strip().lower() == me or (s.get("id") and str(r.get("id")) == s["id"]):
            continue
        if sold:
            a = _age_days(r.get("sold_date"))
            if a is None or a > 365:
                continue
            if r["price"] < 20000:
                continue
        c = dict(r, _sold=sold, _mi=miles(s.get("lat"), s.get("lon"), r.get("lat"), r.get("lon")) if s.get("lat") and r.get("lat") else None)
        c["_key"] = street_key(r.get("address"))
        c["_ppsf"] = _ppsf(c)
        c["_cues"] = cue_keys(cues_of(r) if cues_of else None)
        out.append(c)
    return out


def _pick(pool, s):
    """(same_building comps, nearby comps, radius label) from one prepared pool."""
    sk = street_key(s.get("address"))
    bld = [c for c in pool if sk and c["_key"] == sk and c.get("town") == s.get("town") and klass(c.get("type")) in (s["klass"], "apt")] if s["klass"] == "apt" else []
    bkeys = {id(c) for c in bld}
    sim = [c for c in pool if _similar(s, c) and id(c) not in bkeys]
    near, rad = [], None
    if s.get("lat"):
        for r in RADII:
            near = [c for c in sim if c["_mi"] is not None and c["_mi"] <= r]
            rad = r
            if len([c for c in near if c["_ppsf"]]) >= 6 or (not s.get("sqft") and len(near) >= 6):
                break
    if len(near) < MIN_N:
        near = [c for c in sim if c.get("town") == s.get("town")]
        rad = "town"
    return bld, near, rad


def _key_rank(c, use_ppsf):
    return (c["_ppsf"] or 0) if use_ppsf else (c["price"] or 0)


def analyze(s, sold_rows, active_rows, cues_of=None):
    """s from subject_of(). Returns a dict for the UI: basis 'sold' | 'ask' | None, stats, comps and the ARV range."""
    use_ppsf = bool(s.get("sqft") and s["sqft"] >= 250)
    res = {"subject": s, "use_ppsf": use_ppsf, "sold": None, "ask": None}
    for name, rows, sold in (("sold", sold_rows, True), ("ask", active_rows, False)):
        if not rows:
            continue
        pool = _prep(rows, s, sold, cues_of)
        bld, near, rad = _pick(pool, s)
        far = [c for c in bld + near if far_pricier(c, s, use_ppsf)]
        fid = {id(c) for c in far}
        bld, near = [c for c in bld if id(c) not in fid], [c for c in near if id(c) not in fid]
        bld, bld_other, bbasis = split_building(bld, s)      # only same-size units count; other sizes are shown apart, never in the stats
        st = stats(bld + near if use_ppsf else near, s.get("sqft"), use_ppsf)
        bp = [c["_ppsf"] for c in bld if c.get("_ppsf")]
        bstat = {"n": len(bld), "median_price": _q([c["price"] for c in bld], .5) if bld else None,
                 "median_ppsf": _q(bp, .5) if bp else None, "n_ppsf": len(bp)}
        ds = sorted(c["sold_date"] for c in pool if c.get("sold_date")) if sold else []
        res[name] = {"bld": bld, "bld_other": bld_other, "bld_basis": bbasis, "bld_stats": bstat, "near": sorted(near, key=lambda c: -_key_rank(c, use_ppsf)),
                     "radius": rad, "stats": st, "n_all": len(pool), "far": len(far), "since": ds[0] if ds else None}
    res["basis"] = "sold" if (res["sold"] or {}).get("stats") else "ask" if (res["ask"] or {}).get("stats") else None
    if res["basis"]:
        st = res[res["basis"]]["stats"]
        p = s.get("price") or 0
        res.update(low=st["low"], mid=st["mid"], high=st["high"], spread=(st["mid"] - p) if p else None,
                   spread_lo=(st["low"] - p) if p else None, spread_hi=(st["high"] - p) if p else None)
    return res


def profit(arv, price, rehab, sell_cost=SELL_COST):
    """Rough profit: sale price less selling costs, less what you pay and the rehab. Nothing else (no closing, holding, HOA, taxes)."""
    return round(arv * (1 - sell_cost) - (price or 0) - (rehab or 0))
