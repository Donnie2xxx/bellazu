"""30-year mortgage rate (Freddie Mac PMMS weekly average).
FRED often times out from cloud hosts, so try it briefly, then Freddie Mac's own PMMS history CSV (same series)."""
import time

from ..http import fetch

_FRED_DOWN = [0.0]   # FRED times out from Streamlit Cloud (12 s each time); after one miss skip it for 24 h in this process
_MEMO = {}          # the answer, kept 6 h in this process (every town check asks for it)


def _fred():
    if time.time() < _FRED_DOWN[0]:
        return None
    txt = fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US", "fred:MORTGAGE30US", ttl_hours=24, ua="bot",
                timeout=6, retries=0)
    if not txt:
        _FRED_DOWN[0] = time.time() + 24 * 3600
        return None
    rows = [l.split(",") for l in txt.strip().splitlines()[1:] if "," in l]
    rows = [(d, v) for d, v in rows if v not in (".", "")]
    if not rows:
        return None
    d, v = rows[-1]
    return {"rate_pct": float(v), "date": d, "source": "Freddie Mac PMMS via FRED (MORTGAGE30US)"}


def _pmms():
    txt = fetch("https://www.freddiemac.com/pmms/docs/PMMS_history.csv", "freddiemac:PMMS", ttl_hours=24, timeout=20, retries=0,
                validate=lambda t: t.lstrip().lower().startswith("date,pmms30"))
    if not txt:
        return None
    rows = []
    for line in txt.strip().splitlines()[1:]:
        p = line.split(",")
        if len(p) > 1 and p[1].strip() not in ("", "."):
            try:
                m, dd, y = (int(x) for x in p[0].strip().split("/"))
                rows.append((f"{y:04d}-{m:02d}-{dd:02d}", float(p[1])))
            except ValueError:
                continue
    if not rows:
        return None
    d, v = max(rows)
    return {"rate_pct": v, "date": d, "source": "Freddie Mac PMMS (freddiemac.com)"}


def mortgage30():
    m = _MEMO.get("r")
    if m and time.time() - m[0] < 6 * 3600:
        return dict(m[1])
    r = _fred() or _pmms()
    if r:
        _MEMO["r"] = (time.time(), dict(r))
    return r
