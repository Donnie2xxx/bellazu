import json, pathlib
P = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "str_rules.json"


_MEM = {}


def _rules():
    k = P.stat().st_mtime_ns
    if k not in _MEM:                  # parse once per process (per file version)
        _MEM.clear()
        _MEM[k] = json.loads(P.read_text())
    return _MEM[k]


def rules_for(town):
    import copy
    d = _rules()
    t = (town or "").lower().replace("township", "").replace("town of", "").replace("city of", "").strip()
    alias = {"new york city": "new york", "manhattan": "new york", "brooklyn": "new york", "queens": "new york", "bronx": "new york"}
    t = alias.get(t, t)
    r = copy.deepcopy(d.get(t))
    if not r:
        return {"status": "unknown", "tenant_str": "unknown", "owner_str": "unknown",
                "summary_en": f"No curated STR rule for '{town}'. Check the municipal code (ecode360.com search) and call the zoning office.",
                "summary_es": f"No hay regla de STR registrada para '{town}'. Revise el código municipal (ecode360.com) y llame a la oficina de zonificación.",
                "sources": ["https://ecode360.com/"], "source_type": "none", "last_verified": None}
    r = dict(r)
    r["last_verified"] = d["_meta"]["last_verified"]
    r["str_legal_for_owner"] = r.get("owner_str") not in (False, None) and not str(r.get("owner_str")).startswith("unknown")
    r["str_legal_for_tenant"] = r.get("tenant_str") not in (False, None) and not str(r.get("tenant_str")).startswith("unknown")
    return r
