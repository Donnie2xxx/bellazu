"""Forgiving town names for the town scan: case, spacing, ', NJ' / 'New Jersey', ZIP codes, common short forms
('Ft Lee', 'W New York', 'WNY', 'fortlee') and small typos (fuzzy match against the list below)."""
import difflib, json, pathlib, re

_RULES = pathlib.Path(__file__).resolve().parent.parent / "data" / "str_rules.json"
# North Jersey towns the town scan can search (Rent.com / Craigslist pages by town name). Towns with curated
# short-term-rental rules come from data/str_rules.json and are always included.
EXTRA_NJ = ["Belleville", "Bergenfield", "Bloomfield", "Cliffside Park", "Clifton", "East Orange", "East Rutherford", "Elizabeth",
            "Englewood Cliffs", "Fairview", "Garfield", "Hackensack", "Harrison", "Hasbrouck Heights", "Irvington", "Leonia",
            "Little Ferry", "Lodi", "Lyndhurst", "Montclair", "Newark", "North Arlington", "Nutley", "Palisades Park", "Passaic",
            "Paterson", "Ridgefield", "Ridgefield Park", "Rutherford", "Teaneck", "West Orange"]
NYC = "New York City"
ALIASES = {"wny": "west new york", "w ny": "west new york", "jc": "jersey city", "jersey cty": "jersey city", "nb": "north bergen",
           "nyc": NYC.lower(), "manhattan": NYC.lower(), "new york": NYC.lower(), "ny ny": NYC.lower(), "brooklyn": NYC.lower(),
           "queens": NYC.lower(), "bronx": NYC.lower(), "hoboken city": "hoboken", "union cty": "union city"}
ABBR = [(r"\bft\.?\s*", "fort "), (r"\bw\.?\s+", "west "), (r"\bn\.?\s+", "north "), (r"\be\.?\s+", "east "), (r"\bs\.?\s+", "south "),
        (r"\bmt\.?\s+", "mount "), (r"\bpk\b", "park"), (r"\bhts\.?\b", "heights"), (r"\btwp\.?\b", ""), (r"\btownship\b", ""),
        (r"\bborough of\b", ""), (r"\bcity of\b", ""), (r"\btown of\b", "")]


_SUP = {}


def supported():
    """[(display name, state)] sorted, NJ towns first, then New York City."""
    k = _RULES.stat().st_mtime_ns
    if k in _SUP:
        return list(_SUP[k])
    d = json.loads(_RULES.read_text())
    nj = {k.title() for k in d if not k.startswith("_") and k != "new york"} | set(EXTRA_NJ)
    out = [(t, "nj") for t in sorted(nj)] + [(NYC, "ny")]
    _SUP.clear()
    _SUP[k] = out
    return list(out)


def names():
    return [t for t, _ in supported()]


def _clean(s):
    s = (s or "").replace("\u00a0", " ").strip().lower()
    s = re.sub(r"\b\d{5}(-\d{4})?\b", " ", s)                                   # ZIP codes
    s = re.sub(r"[,;/]+", " ", s)
    s = re.sub(r"\b(new jersey|n\.?\s?j\.?|usa|us|united states)\b\.?", " ", s)   # state words
    s = re.sub(r"\s+", " ", s).strip()
    for a, b in ABBR:
        s = re.sub(a, b, s + " ").strip()
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize(text):
    """{'name', 'state', 'match': exact|alias|fuzzy|none, 'suggestions': [names], 'typed'}."""
    typed = (text or "").strip()
    sup = supported()
    by = {t.lower(): (t, s) for t, s in sup}
    nospace = {t.lower().replace(" ", ""): (t, s) for t, s in sup}
    c = _clean(typed)
    ny_hint = bool(re.search(r"\b(ny|new york)\b", typed.lower())) and "west new york" not in typed.lower()
    if not c:
        return {"name": "", "state": "nj", "match": "none", "suggestions": [], "typed": typed}
    if c in by:
        return {"name": by[c][0], "state": by[c][1], "match": "exact", "suggestions": [], "typed": typed}
    if ny_hint:
        c = re.sub(r"\s*\bny$", "", c).strip() or "new york"
        if c in by:
            return {"name": by[c][0], "state": by[c][1], "match": "exact", "suggestions": [], "typed": typed}
    if c in ALIASES:
        t, s = by[ALIASES[c]]
        return {"name": t, "state": s, "match": "alias", "suggestions": [], "typed": typed}
    ns = c.replace(" ", "")
    if ns in nospace:
        t, s = nospace[ns]
        return {"name": t, "state": s, "match": "alias", "suggestions": [], "typed": typed}
    close = difflib.get_close_matches(ns, list(nospace), n=4, cutoff=0.6)
    sugg = [nospace[x][0] for x in close]
    if close and difflib.SequenceMatcher(None, ns, close[0]).ratio() >= 0.82:
        t, s = nospace[close[0]]
        return {"name": t, "state": s, "match": "fuzzy", "suggestions": sugg[1:], "typed": typed}
    if not sugg:   # try word-level: any supported town sharing a word
        words = set(c.split())
        sugg = [t for t, _ in sup if words & set(t.lower().split()) - {"city", "park", "west", "north", "east"}][:4]
    return {"name": typed.title() if typed.islower() else typed, "state": "ny" if ny_hint else "nj", "match": "none",
            "suggestions": sugg, "typed": typed}
