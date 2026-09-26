"""Saved homes ("favorites"): merge logic, sync codes, backup files and an optional encrypted online copy.

Layers
  A. The browser (localStorage, written by a tiny component in app.py) keeps the list on the phone.
  B. Backup file: an HTML page that is readable on its own AND restorable (the list is embedded as JSON).
  C. Online copy (always on): ONE encrypted file (saves/bella.json) in a PRIVATE GitHub repo, written over SSH with
     a deploy key that can only touch that one repo. The content is encrypted with the app passcode (bellazu/keylock.py),
     so it survives app restarts, redeploys, cleared browsers and new phones: any device that enters the passcode sees it.
Everything here is plain Python (no Streamlit)."""
import base64, hashlib, html as H, io, json, os, re, secrets, tempfile, threading, time

from . import keylock

VERSION = 1
FILE_TAG = "bellazu-saves"
REMOTE_REPO = os.environ.get("BELLAZU_SAVES_REPO", "Donnie2xxx/bellazu-saves")
_ALPHA = "abcdefghjkmnpqrstuvwxyz23456789"          # no 0/o, 1/l/i
GITHUB_HOST_KEY = "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"   # gh api meta (ssh_keys, ed25519)
TOMBSTONE_DAYS = 365


def now_ms():
    return int(time.time() * 1000)


# ------------------------------------------------------------------ list model
def empty():
    return {"v": VERSION, "sync": None, "items": {}, "removed": {}}


def new_code():
    raw = "".join(secrets.choice(_ALPHA) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def clean_code(s):
    s = re.sub(r"[^a-z0-9]", "", (s or "").lower())
    if len(s) != 16 or any(c not in _ALPHA for c in s):
        return None
    return "-".join(s[i:i + 4] for i in range(0, 16, 4))


def normalize(d):
    """Accept anything list-shaped; return a clean list dict."""
    out = empty()
    if not isinstance(d, dict):
        return out
    out["sync"] = clean_code(d.get("sync")) if d.get("sync") else None
    items = d.get("items") or {}
    if isinstance(items, list):
        items = {str(x.get("id")): x for x in items if isinstance(x, dict) and x.get("id")}
    for k, v in items.items():
        if isinstance(v, dict) and v.get("id") == k:
            v.setdefault("updated", now_ms())
            out["items"][k] = v
    for k, t in (d.get("removed") or {}).items():
        try:
            out["removed"][str(k)] = int(t)
        except Exception:
            pass
    pr = d.get("prefs")
    if isinstance(pr, dict) and pr.get("lang") in ("EN", "ES"):
        try:
            out["prefs"] = {"lang": pr["lang"], "t": int(pr.get("t", 0))}
        except Exception:
            pass
    return out


def merge(a, b):
    """Union of two lists. Per home the newest edit wins; a removal wins over anything older than it."""
    a, b = normalize(a), normalize(b)
    out = empty()
    out["sync"] = a["sync"] or b["sync"]
    cut = now_ms() - TOMBSTONE_DAYS * 86400_000
    rem = {}
    for k in set(a["removed"]) | set(b["removed"]):
        t = max(a["removed"].get(k, 0), b["removed"].get(k, 0))
        if t >= cut:
            rem[k] = t
    for k in set(a["items"]) | set(b["items"]):
        x, y = a["items"].get(k), b["items"].get(k)
        best = x if (y is None or (x is not None and int(x.get("updated", 0)) >= int(y.get("updated", 0)))) else y
        if rem.get(k, -1) >= int(best.get("updated", 0)):
            continue
        out["items"][k] = best
    out["removed"] = {k: t for k, t in rem.items() if k not in out["items"]}
    pa, pb = a.get("prefs"), b.get("prefs")          # settings (language): the newest choice wins
    if pa or pb:
        out["prefs"] = pa if (pb is None or (pa is not None and pa["t"] >= pb["t"])) else pb
    return out


def same(a, b):
    return json.dumps(normalize(a), sort_keys=True) == json.dumps(normalize(b), sort_keys=True)


def item_id(kind, key):
    k = re.sub(r"[^a-z0-9|]+", "-", str(key).lower()).strip("-")[:90]
    return f"{kind[0]}:{k}"


# ------------------------------------------------------------------ backup file (layer B)
def _money(v):
    try:
        return f"${round(float(v)):,}"
    except Exception:
        return ""


def export_html(lst, lang="en"):
    """A self-contained page in ONE language (the one picked in the app) + the data for 'Restore from file'."""
    lst = normalize(lst)
    items = sorted(lst["items"].values(), key=lambda x: -int(x.get("saved_ms", 0)))
    es = lang == "es"
    st_lbl = {"interested": ("Interested", "Me interesa"), "toured": ("Toured", "La visité"), "offer": ("Offer", "Oferta"), "no": ("Not for me", "No es para mí")}
    rows = []
    for x in items:
        pic = x.get("photo") if str(x.get("photo", "")).startswith("https://") else ""
        facts = " · ".join(b for b in [x.get("facts_line_es" if es else "facts_line_en") or ""] if b)
        nums = "".join(f"<li>{H.escape((c.get('title') or ['', ''])[1 if es else 0])}: <b>{H.escape(str(c.get('pay') or '—'))}</b></li>" for c in (x.get("cols") or []))
        link = f"<a href='{H.escape(x['url'])}'>{'Ver anuncio' if es else 'See listing'} ↗</a>" if str(x.get("url", "")).startswith("http") else ""
        s = st_lbl.get(x.get("status") or "interested", st_lbl["interested"])
        rows.append(f"<div class='c'>{f'<img src={chr(39)}{H.escape(pic)}{chr(39)} alt={chr(39)}{chr(39)}>' if pic else ''}<div><h3>{H.escape(x.get('title') or '')}</h3>"
                    f"<p class='p'>{H.escape(_money(x.get('price')) + ((('/mes' if es else '/mo')) if x.get('rent') else ''))} {H.escape(facts)}</p>"
                    f"<p>{'Guardada' if es else 'Saved'} {H.escape(x.get('saved') or '')} · {H.escape(s[1] if es else s[0])}</p>"
                    + (f"<ul>{nums}</ul>" if nums else "") + (f"<p class='n'>📝 {H.escape(x.get('note') or '')}</p>" if x.get("note") else "") + f"<p>{link}</p></div></div>")
    data = json.dumps({"tag": FILE_TAG, **lst}, ensure_ascii=True).replace("</", "<\\/")
    title = "Mis casas guardadas · BellaZu" if es else "My saved homes · BellaZu"
    return f"""<!doctype html><html lang="{'es' if es else 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>body{{font-family:system-ui,sans-serif;background:#141414;color:#fff;margin:0;padding:16px;max-width:640px}}
h1{{font-weight:600}} .c{{display:flex;gap:12px;border:1px solid #333;border-radius:16px;padding:12px;margin:10px 0}} .c img{{width:96px;height:72px;object-fit:cover;border-radius:10px}}
h3{{margin:0 0 4px;font-size:1rem}} p,li{{margin:2px 0;font-size:.9rem;color:#ddd}} .p{{color:#fff;font-weight:600}} .n{{color:#F4A7BB}} a{{color:#F4A7BB}} .k{{font-size:.8rem;color:#aaa}}</style></head><body>
<h1>{title}</h1><p class="k">{'Para recuperar su lista: en BellaZu abra ♥ Mis casas guardadas → Recuperar desde archivo y elija este archivo.' if es else 'To get your list back: in BellaZu open ♥ My saved homes → Restore from file and pick this file.'}</p>
{''.join(rows) or '<p>—</p>'}
<script type="application/json" id="bellazu-saves">{data}</script></body></html>"""


def parse_import(raw):
    """Read a backup (our HTML or JSON). Returns a list dict or None."""
    try:
        txt = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    except Exception:
        return None
    m = re.search(r'<script type="application/json" id="bellazu-saves">(.*?)</script>', txt, re.S)
    body = m.group(1).replace("<\\/", "</") if m else txt
    try:
        d = json.loads(body)
    except Exception:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("items"), (dict, list)):
        return None
    return normalize(d)


# ------------------------------------------------------------------ encryption for the online copy
LIST_PATH = os.environ.get("BELLAZU_SAVES_PATH", "saves/bella.json")     # ONE list for the app (everyone who knows the passcode)


def seal(lst, secret):
    return json.dumps(keylock.lock(json.dumps(normalize(lst), separators=(",", ":")), secret)).encode()


def unseal(raw, secret):
    try:
        pt = keylock.unlock(raw.decode(), secret)
        return normalize(json.loads(pt)) if pt else None
    except Exception:
        return None


# ------------------------------------------------------------------ online copy (layer C): private GitHub repo over SSH, deploy key
_KEY = {"pem": None}
_LOCK = threading.Lock()
STATE = {"status": None, "merged": None, "pending": None, "worker": None}


def set_key(pem):
    _KEY["pem"] = pem or None


def cloud_available():
    if not _KEY["pem"]:
        return False
    try:
        import dulwich, paramiko  # noqa: F401
        return True
    except Exception:
        return False


def _vendor():
    import logging
    import paramiko
    from dulwich.client import SSHVendor
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)

    class _Wrap:
        def __init__(self, client, chan):
            self.client, self.chan = client, chan
            self.stderr = io.BytesIO()

        def read(self, n=None):
            if n is None:
                out = b""
                while True:
                    d = self.chan.recv(65536)
                    if not d:
                        return out
                    out += d
            data = self.chan.recv(n)
            while len(data) < n:
                more = self.chan.recv(n - len(data))
                if not more:
                    break
                data += more
            return data

        def write(self, data):
            self.chan.sendall(data)
            return len(data)

        def can_read(self):
            return self.chan.recv_ready()

        def close(self, timeout=None):
            try:
                self.chan.close()
            finally:
                self.client.close()

    class Vendor(SSHVendor):
        def run_command(self, host, command, username=None, port=None, password=None, key_filename=None, ssh_command=None, protocol_version=None):
            pk = paramiko.Ed25519Key.from_private_key(io.StringIO(_KEY["pem"]))
            cl = paramiko.SSHClient()
            hk = paramiko.Ed25519Key(data=base64.b64decode(GITHUB_HOST_KEY))
            for h in ("github.com", "[ssh.github.com]:443", "ssh.github.com"):
                cl.get_host_keys().add(h, "ssh-ed25519", hk)
            cl.set_missing_host_key_policy(paramiko.RejectPolicy())      # only GitHub's published host key is accepted
            cl.connect(host, port=port or 22, username=username or "git", pkey=pk, look_for_keys=False, allow_agent=False, timeout=12,
                       banner_timeout=12, auth_timeout=12)
            ch = cl.get_transport().open_session(timeout=12)
            ch.settimeout(25)
            ch.exec_command(command if isinstance(command, str) else command.decode())
            return _Wrap(cl, ch)
    return Vendor()


LAST_ROUTE = {"v": None}


def _clients():
    from dulwich.client import SSHGitClient
    routes = [("github.com", 22), ("ssh.github.com", 443)]
    if LAST_ROUTE["v"] in routes:                      # try what worked last time first
        routes.remove(LAST_ROUTE["v"]); routes.insert(0, LAST_ROUTE["v"])
    for host, port in routes:
        yield (host, port), SSHGitClient(host, port=port, username="git", vendor=_vendor()), f"/{REMOTE_REPO}.git"


def _repo():
    """Local cache: a bare clone in /tmp (rebuilt from GitHub after a restart)."""
    from dulwich.repo import Repo
    d = os.environ.get("BELLAZU_SAVES_DIR") or os.path.join(tempfile.gettempdir(), "bz_saves.git")   # server: a folder that survives restarts
    return Repo(d) if os.path.isdir(d) else Repo.init_bare(d, mkdir=True)


def _fetch(repo):
    last = None
    for route, cl, path in _clients():
        try:
            res = cl.fetch(path, repo)
            LAST_ROUTE["v"] = route
            return cl, path, res.refs.get(b"refs/heads/main")
        except Exception as e:     # try the next route
            last = e
    raise last or RuntimeError("no route")


def _read(repo, head):
    from dulwich.object_store import tree_lookup_path
    if not head:
        return None
    try:
        _, sha = tree_lookup_path(repo.__getitem__, repo[head].tree, LIST_PATH.encode())
        return repo[sha].data
    except KeyError:
        return None


def _put_path(repo, root_old, parts, blob_id):
    """New tree = old tree with parts[...] set to blob_id (creates folders as needed)."""
    from dulwich.objects import Tree
    t = Tree()
    for e in (root_old.items() if root_old is not None else []):
        t.add(e.path, e.mode, e.sha)
    name = parts[0].encode()
    if len(parts) == 1:
        t.add(name, 0o100644, blob_id)
    else:
        sub_old = repo[root_old[name][1]] if (root_old is not None and name in root_old) else None
        sub = _put_path(repo, sub_old, parts[1:], blob_id)
        t.add(name, 0o040000, sub.id)
    repo.object_store.add_object(t)
    return t


def _write(secret, lst):
    """fetch -> merge with what is online -> commit -> push; retry on a race. Returns the merged list (never drops a home)."""
    from dulwich.objects import Blob, Commit
    last = None
    for attempt in range(4):
        repo = _repo()
        cl, path, head = _fetch(repo)
        raw = _read(repo, head)
        remote = unseal(raw, secret) if raw else None
        if raw and remote is None:
            raise RuntimeError("online copy can't be opened with this passcode")      # never overwrite what we can't read
        merged = merge(lst, remote) if remote else normalize(lst)
        if remote is not None and same(merged, remote):
            return merged
        if not merged["items"] and not merged["removed"] and not merged.get("prefs") and remote is None:
            return merged                                                    # nothing to store yet
        blob = Blob.from_string(seal(merged, secret))
        repo.object_store.add_object(blob)
        root = _put_path(repo, repo[repo[head].tree] if head else None, LIST_PATH.split("/"), blob.id)
        c = Commit()
        c.tree, c.parents = root.id, ([head] if head else [])
        c.author = c.committer = b"BellaZu app <app@bellazu.invalid>"
        c.author_time = c.commit_time = int(time.time())
        c.author_timezone = c.commit_timezone = 0
        c.encoding = b"UTF-8"
        c.message = f"saved homes: {len(merged['items'])}".encode()
        repo.object_store.add_object(c)
        try:
            r = cl.send_pack(path, lambda refs: {b"refs/heads/main": c.id}, generate_pack_data=repo.generate_pack_data)
            err = (getattr(r, "ref_status", None) or {}).get(b"refs/heads/main")
            if err:
                raise RuntimeError(str(err))
            return merged
        except Exception as e:     # someone pushed first (or a network blip): fetch, merge again, retry
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise last


def cloud_get(secret):
    """Read the online list. Returns (list|None, error|None). Blocking, ~1-3 s."""
    if not cloud_available() or not secret:
        return None, "off"
    with _LOCK:
        try:
            repo = _repo()
            _, _, head = _fetch(repo)
            raw = _read(repo, head)
            if not raw:
                return empty(), None
            got = unseal(raw, secret)
            return (got, None) if got is not None else (None, "locked")
        except Exception as e:
            return None, e.__class__.__name__


def cloud_put(secret, lst):
    """Background sync: merge this list with the online copy and push if anything changed. The latest call wins the queue;
    the merged result lands in STATE['merged'] for every session to pick up."""
    if not cloud_available() or not secret:
        return False
    STATE["pending"] = (secret, normalize(lst))
    w = STATE.get("worker")
    if w and w.is_alive():
        return True

    def run():
        while STATE.get("pending"):
            sec, l_ = STATE["pending"]
            STATE["pending"] = None
            with _LOCK:
                try:
                    m = _write(sec, l_)
                    STATE["merged"] = merge(STATE["merged"], m) if STATE.get("merged") else m
                    STATE["status"] = {"ok": True, "t": time.time()}
                except Exception as e:
                    STATE["status"] = {"ok": False, "t": time.time(), "err": e.__class__.__name__}
    t = threading.Thread(target=run, daemon=True, name="bz-saves-sync")
    STATE["worker"] = t
    t.start()
    return True


def cloud_busy():
    w = STATE.get("worker")
    return bool((w and w.is_alive()) or STATE.get("pending"))


def cloud_wait(seconds=8.0):
    end = time.time() + seconds
    while cloud_busy() and time.time() < end:
        time.sleep(0.1)
    return not cloud_busy()


def cloud_status():
    return STATE.get("status")


def cloud_merged():
    return STATE.get("merged")
