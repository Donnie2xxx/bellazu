"""Free listing photos for NJ Bright MLS homes: the public listing page on newjerseyrealestatenetwork.com (a Sierra Interactive IDX site),
looked up by the MLS number RentCast gives. No API key and no quota. Only the photo URLs (their CDN) are kept, cached on disk:
14 days when found, 3 days when not found. Never raises."""
import json, os, pathlib, re, subprocess, time
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
OK_TTL, MISS_TTL = 14 * 86400, 3 * 86400
MAX_PHOTOS = 12


def _dir():
    d = pathlib.Path(os.environ.get("BELLAZU_CACHE") or pathlib.Path(__file__).resolve().parents[2] / "cache") / "photos_nj"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(addr):
    return re.sub(r"[^a-z0-9]+", "-", str(addr or "").lower()).strip("-")


def cached(mls):
    p = _dir() / f"{re.sub(r'[^A-Za-z0-9]', '', mls)}.json"
    try:
        d = json.loads(p.read_text())
        if time.time() - d["t"] < (OK_TTL if d.get("photos") else MISS_TTL):
            return d
    except Exception:
        pass
    return None


def fetch(mls, addr):
    """{'photos': [...], 'url': listing page or None}. Free; one page download unless cached."""
    if not mls or not str(mls).upper().startswith("NJ"):
        return {"photos": [], "url": None}
    c = cached(mls)
    if c:
        return c
    url = f"https://www.newjerseyrealestatenetwork.com/property-search/detail/337/{mls}/{_slug(addr)}/"
    photos, ok_url = [], None
    try:
        h = subprocess.run(["curl", "-sL", "-m", "20", "-A", UA, url], capture_output=True, timeout=25).stdout.decode("utf8", "ignore")
        num = str(addr or "").split()[0] if addr else ""
        t = re.search(r"<title>([^<]*)", h)
        if t and mls in t.group(1) and num in t.group(1):
            seen = {}
            for u, n in re.findall(r"(https://cdn\.listingphotos\.sierrastatic\.com/large/[^\"' )]+/337_" + re.escape(mls) + r"_(\d+)\.jpg)", h):
                seen.setdefault(int(n), u)
            photos = [seen[n] for n in sorted(seen)][:MAX_PHOTOS]
            ok_url = url if photos else None
    except Exception:
        return {"photos": [], "url": None}          # network trouble: not cached, try again next time
    d = {"photos": photos, "url": ok_url, "t": time.time()}
    try:
        (_dir() / f"{re.sub(r'[^A-Za-z0-9]', '', mls)}.json").write_text(json.dumps(d))
    except Exception:
        pass
    return d


def fetch_many(pairs, workers=6):
    """pairs: [(mls, addr)] -> {mls: result}. Parallel, free."""
    pairs = [(m, a) for m, a in pairs if m]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return dict(zip([m for m, _ in pairs], ex.map(lambda p: fetch(*p), pairs)))
