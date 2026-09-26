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
class _ThreadList:
    """A list per thread, so towns looked up side by side (in parallel threads) keep their own source log."""
    def __init__(self):
        self._l = threading.local()

    def _get(self):
        if not hasattr(self._l, "v"):
            self._l.v = []
        return self._l.v

    def append(self, x):
        self._get().append(x)

    def extend(self, xs):
        self._get().extend(xs)

    def clear(self):
        self._get().clear()

    def __iter__(self):
        return iter(list(self._get()))

    def __len__(self):
        return len(self._get())

    def __getitem__(self, i):
        return self._get()[i]


STATUS = _ThreadList()   # list of dicts: source, url, ok, http, note  (reset per run by core)
# Failed lookups are remembered for a while in this process so a blocked or down site doesn't make every page wait again
# (throttle + a retry with an 8 s pause each time). Same result as before (no data from that site), just without the wait.
FAIL_URL_S = 30 * 60        # this exact URL failed: skip it for 30 min
FAIL_HOST_S = 15 * 60       # the site blocked us (403/429/202) or didn't answer: skip the whole site for 15 min
_fail_url, _fail_host = {}, {}


def _throttle(host, min_interval):
    """Same spacing per site as before, but the wait happens outside the lock: a pause for one site
    no longer holds up lookups to other sites running in parallel threads."""
    with _lock:
        now = time.time()
        slot = max(now, _last.get(host, 0) + min_interval)
        _last[host] = slot
    if slot > now:
        time.sleep(slot - now)


def record(source, url, ok, http=None, note="", ms=None):
    STATUS.append({"source": source, "url": url, "ok": bool(ok), "http": http, "note": note, **({"ms": ms} if ms is not None else {})})


def fetch(url, source, ttl_hours=24, method="GET", data=None, headers=None, binary=False,
          ua="browser", min_interval=2.0, timeout=40, validate=None, session=None, retries=1):
    """Return (content or None). Cached by url+data. validate(content)->bool marks blocks."""
    t0 = time.time()
    key = hashlib.sha1((method + url + json.dumps(data, sort_keys=True)).encode()).hexdigest()
    sub = CACHE / "http"
    sub.mkdir(exist_ok=True)
    path = sub / key
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl_hours * 3600:
        c = path.read_bytes()
        record(source, url, True, "cache", "served from cache")
        return c if binary else c.decode("utf-8", "replace")
    host = url.split("/")[2]
    now = time.time()
    fu, fh = _fail_url.get(key), _fail_host.get(host)
    if (fu and fu[0] > now) or (fh and fh[0] > now):
        f = fu if (fu and fu[0] > now) else fh
        record(source, url, False, f[1], "failed a few minutes ago; not retried yet", ms=0)
        return None
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
                record(source, url, False, None, f"network error: {e.__class__.__name__}", ms=round((time.time() - t0) * 1000))
                _fail_host[host] = (time.time() + FAIL_HOST_S, None)
                return None
        time.sleep(8)   # one polite retry for transient rate-limits

    body = r.content
    ok = r.status_code == 200 and (len(body) > 500 or validate is not None)
    txt = None if binary else body.decode("utf-8", "replace")
    if ok and validate is not None:
        ok = bool(validate(body if binary else txt))
    if not ok:
        note = "blocked/challenge" if r.status_code in (202, 403, 429) or (r.status_code == 200) else "error"
        record(source, url, False, r.status_code, note, ms=round((time.time() - t0) * 1000))
        _fail_url[key] = (time.time() + FAIL_URL_S, r.status_code)
        if r.status_code in (202, 403, 429):
            _fail_host[host] = (time.time() + FAIL_HOST_S, r.status_code)
        return None
    path.write_bytes(body)
    record(source, url, True, r.status_code, "", ms=round((time.time() - t0) * 1000))
    return body if binary else txt


def cache_file(name):
    p = CACHE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
