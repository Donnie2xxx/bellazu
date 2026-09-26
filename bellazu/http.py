"""Polite HTTP GET/POST with on-disk cache + per-source status log."""
import hashlib, json, os, time, pathlib, threading
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = pathlib.Path(os.environ.get("BELLAZU_CACHE", ROOT / "cache"))
CACHE.mkdir(parents=True, exist_ok=True)
UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")
UA_BOT = "BellaZu/0.1 (personal real-estate research; low volume)"
_last = {}
_lock = threading.Lock()
STATUS = []   # list of dicts: source, url, ok, http, note  (reset per run by core)


def _throttle(host, min_interval):
    with _lock:
        t = _last.get(host, 0)
        wait = min_interval - (time.time() - t)
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.time()


def record(source, url, ok, http=None, note=""):
    STATUS.append({"source": source, "url": url, "ok": bool(ok), "http": http, "note": note})


def fetch(url, source, ttl_hours=24, method="GET", data=None, headers=None, binary=False,
          ua="browser", min_interval=2.0, timeout=40, validate=None, session=None, retries=1):
    """Return (content or None). Cached by url+data. validate(content)->bool marks blocks."""
    key = hashlib.sha1((method + url + json.dumps(data, sort_keys=True)).encode()).hexdigest()
    sub = CACHE / "http"
    sub.mkdir(exist_ok=True)
    path = sub / key
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl_hours * 3600:
        c = path.read_bytes()
        record(source, url, True, "cache", "served from cache")
        return c if binary else c.decode("utf-8", "replace")
    host = url.split("/")[2]
    _throttle(host, min_interval)
    h = {"User-Agent": UA_BROWSER if ua == "browser" else UA_BOT,
         "Accept-Language": "en-US,en;q=0.9",
         "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"}
    if headers:
        h.update(headers)
    s = session or requests
    r = None
    for attempt in range(retries + 1):
        try:
            r = s.request(method, url, data=data, headers=h, timeout=timeout, allow_redirects=True)
            if r.status_code not in (403, 429, 202, 500, 502, 503) or attempt == retries:
                break
        except Exception as e:  # network error
            if attempt == retries:
                record(source, url, False, None, f"network error: {e.__class__.__name__}")
                return None
        time.sleep(8)   # one polite retry for transient rate-limits

    body = r.content
    ok = r.status_code == 200 and (len(body) > 500 or validate is not None)
    txt = None if binary else body.decode("utf-8", "replace")
    if ok and validate is not None:
        ok = bool(validate(body if binary else txt))
    if not ok:
        note = "blocked/challenge" if r.status_code in (202, 403, 429) or (r.status_code == 200) else "error"
        record(source, url, False, r.status_code, note)
        return None
    path.write_bytes(body)
    record(source, url, True, r.status_code, "")
    return body if binary else txt


def cache_file(name):
    p = CACHE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
