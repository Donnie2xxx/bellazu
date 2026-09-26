from ..http import fetch


def mortgage30():
    txt = fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US", "fred:MORTGAGE30US", ttl_hours=24, ua="bot")
    if not txt:
        return None
    rows = [l.split(",") for l in txt.strip().splitlines()[1:] if "," in l]
    rows = [(d, v) for d, v in rows if v not in (".", "")]
    d, v = rows[-1]
    return {"rate_pct": float(v), "date": d, "source": "Freddie Mac PMMS via FRED (MORTGAGE30US)"}
