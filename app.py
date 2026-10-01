"""BellaZu web app (Streamlit). Simple phone-first UI, English/Spanish, passcode-gated.
Run locally:  APP_PASSCODE=... streamlit run app.py   (or put the values in .streamlit/secrets.toml)
Secrets (st.secrets first, then environment variables):
  APP_PASSCODE (required), RENTCAST_API_KEY (optional), RENTCAST_MONTHLY_CAP / RENTCAST_USED_OFFSET (optional).
RentCast key: data/rc.lock holds the key encrypted with the passcode (bellazu/keylock.py); it is tried first and
RENTCAST_API_KEY is the fallback (also used if RentCast refuses the locked key). The key is never shown.
Nothing personal lives in this file: every number is typed by the user and kept only in the browser session."""
import hmac, html as H, json, os, pathlib, re, sys, tempfile, time
_BZ_T0 = time.perf_counter()
import contextlib
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def secret(name, default=""):
    """st.secrets first (Streamlit Community Cloud), then os.environ."""
    v = None
    try:
        v = st.secrets.get(name)
    except Exception:          # no secrets.toml -> fine, fall back to the environment
        v = None
    if v in (None, ""):
        v = os.environ.get(name, default)
    return str(v).strip() if v is not None else default


for _k in ("RENTCAST_API_KEY", "RENTCAST_MONTHLY_CAP", "RENTCAST_USED_OFFSET"):   # the engine reads these from os.environ
    _v = secret(_k)
    if _v and not os.environ.get(_k):
        os.environ[_k] = _v


def _moved_to():
    """The app now lives on its own always-on server. Only the old Streamlit Community Cloud copy (it runs from /mount/src and
    the server sets BELLAZU_SERVER=1) shows a "BellaZu moved" page, once data/moved.json names the new address with
    "live": true. With "live": false it shows only for ?moved_preview=1 (to test the redirect on Streamlit Cloud)."""
    if os.environ.get("BELLAZU_SERVER") == "1" or not str(ROOT).startswith("/mount/"):
        return ""
    try:
        m = json.loads((ROOT / "data" / "moved.json").read_text())
    except Exception:
        return ""
    if not m.get("live") and str(st.query_params.get("moved_preview") or "") != "1":   # not switched on yet: preview only
        return ""
    return str(m.get("url") or "").strip()


MOVED_JS = """
export default function(component) {
  const { data, parentElement } = component;
  const d = data || {};
  if (parentElement.__bzm) return;
  parentElement.__bzm = 1;
  // one language, same rules as the app: ?lang= wins, then the language saved on this phone, then a Spanish phone
  let lang = "";
  const pick = (q) => { try { const v = new URLSearchParams(q).get("lang"); return v ? v.toLowerCase().slice(0, 2) : ""; } catch (e) { return ""; } };
  lang = pick(window.location.search);
  if (!lang) { try { lang = pick(window.top.location.search); } catch (e) {} }
  if (lang !== "en" && lang !== "es") {
    lang = "";
    try { const raw = window.localStorage.getItem("bellazu_saves_v1"); const p = raw ? (JSON.parse(raw).prefs || {}) : {};
          if (p.lang === "ES" || p.lang === "EN") lang = p.lang.toLowerCase(); } catch (e) {}
  }
  if (!lang) lang = String(navigator.language || "").toLowerCase().startsWith("es") ? "es" : "en";
  const T = lang === "es" ? d.es : d.en;
  let qs = window.location.search;                       // keep the rest of the link (e.g. ?towns=secaucus,kearny)
  try { if (window.top.location.search) qs = window.top.location.search; } catch (e) {}
  const P = new URLSearchParams(qs); P.delete("moved_preview"); P.set("lang", lang);
  const url = d.url.split("?")[0] + "?" + P.toString();
  const root = document.createElement("div");
  root.className = "mv";
  root.innerHTML = '<div class="w">BellaZu</div><div class="h">' + T.h + '</div><p>' + T.p + '</p>' +
    '<a class="b" target="_blank" rel="noopener" href="' + url.replace(/"/g, "") + '">' + T.b + '</a><p class="s">' + T.s + '</p>';
  parentElement.appendChild(root);
  // Automatic jump where the page may navigate the whole tab (e.g. opened directly). On Streamlit Cloud the app runs in a
  // sandboxed frame without top navigation, so this is refused there and the button (opens a new tab) does the job.
  setTimeout(() => { try { window.top.location.href = url; } catch (e) {} }, 900);
}
"""
MOVED_CSS = """
.mv {text-align:center; padding:48px 12px; color:#fff; font-family:Inter, system-ui, sans-serif}
.mv .w {font-family:'Instrument Serif', Georgia, serif; font-size:30px; margin-bottom:28px}
.mv .h {font-family:'League Gothic', Impact, sans-serif; font-size:46px; text-transform:uppercase; line-height:1.05; margin-bottom:14px}
.mv p {color:#ddd; font-size:17px; line-height:1.5; margin:0 0 26px}
.mv .b {display:block; background:#F4A7BB; color:#141414 !important; text-decoration:none; font-weight:700; font-size:20px;
        padding:20px 18px; border-radius:999px; letter-spacing:.04em; text-transform:uppercase}
.mv .s {color:#A9A9A9; font-size:14px; margin-top:18px}
"""


def moved_page(url):
    """Old address: a one-language "BellaZu moved" note, a big button, and an automatic jump to the new address.
    Nothing else runs here (no passcode, no lookups, no API calls)."""
    st.set_page_config(page_title="BellaZu", page_icon="🏡", layout="centered", initial_sidebar_state="collapsed")
    st.markdown("<style>#MainMenu, footer, header[data-testid='stHeader'], [data-testid='stToolbar'], [data-testid='stDecoration'],"
                "[data-testid='stStatusWidget'] {display:none !important} .stApp {background:#141414}</style>", unsafe_allow_html=True)
    comp = st.components.v2.component("bz_moved", css=MOVED_CSS, js=MOVED_JS)
    comp(key="bz_moved", data={
        "url": url,
        "en": {"h": "BellaZu moved 💕", "p": "BellaZu has a new home. It is faster and never falls asleep. Your saved homes come along: same passcode.",
               "b": "Open the new BellaZu", "s": "Tap the button. Tip: save the new page to your home screen."},
        "es": {"h": "BellaZu se mudó 💕", "p": "BellaZu tiene una nueva casa. Es más rápida y nunca se duerme. Sus casas guardadas vienen también: el mismo código.",
               "b": "Abrir la nueva BellaZu", "s": "Toque el botón. Consejo: guarde la nueva página en su pantalla de inicio."}})
    st.stop()


if _moved_to():
    moved_page(_moved_to())


def _fresh_engine():
    """Streamlit Cloud pulls new commits into a running process, which re-runs app.py but keeps the old bellazu
    modules in memory. Reload them when their files change (or on the first run after such a pull)."""
    import sys, importlib, pathlib as _pl
    root = _pl.Path(__file__).parent / "bellazu"
    stamp = tuple(sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob("*.py")))
    old = getattr(sys, "_bz_stamp", None)
    stale = (old is None and "bellazu" in sys.modules) or (old is not None and old != stamp)
    if stale:           # drop every bellazu module so the imports below load all of them fresh (a reload in place can leave
        for name in [m for m in list(sys.modules) if m == "bellazu" or m.startswith("bellazu.")]:   # one module holding another's old functions)
            sys.modules.pop(name, None)
        importlib.invalidate_caches()
    sys._bz_stamp = stamp


_fresh_engine()
from bellazu import analyze_property, scan_arbitrage          # noqa: E402
from bellazu.render import property_html, arb_html, write_property, write_arbitrage  # noqa: E402
from bellazu.sources import rentcast                          # noqa: E402
from bellazu import simple as S                               # noqa: E402
from bellazu import towns                                     # noqa: E402
from bellazu.simple import money                              # noqa: E402
from bellazu import keylock                                   # noqa: E402
from bellazu import listings                                  # noqa: E402
from bellazu import saves                                     # noqa: E402
from bellazu import myloan as ML                              # noqa: E402
from bellazu import arv as ARV                                # noqa: E402
import datetime as dt                                         # noqa: E402
from bellazu import hoa as HOA                                # noqa: E402

st.set_page_config(page_title="BellaZu", page_icon="🏡", layout="centered", initial_sidebar_state="collapsed")


# ------------------------------------------------------------------ optional timing (?debug_timing=1): per-section ms of each run, shown at the bottom
def _tm_start():
    ss = st.session_state
    if "debug_timing" not in ss:
        ss.debug_timing = str(st.query_params.get("debug_timing") or "") == "1"
    cur = ss.get("_tm_cur")
    if cur is not None:
        cb = []
        while cur and cur[-1][0].startswith("cb:"):          # callbacks ran just before this run: they belong to it
            cb.insert(0, cur.pop())
        if cur:
            ss.setdefault("_tm_hist", []).append({"secs": cur, "total": ss.get("_tm_last", 0), "at": ss.get("_tm_at")})
            ss._tm_hist = ss._tm_hist[-8:]
        cur = cb
    ss._tm_cur = list(cur or [])
    ss._tm_at = time.strftime("%H:%M:%S")
    ss._tm_last = 0


from streamlit.runtime.scriptrunner import get_script_run_ctx as _src_ctx   # noqa: E402


@contextlib.contextmanager
def tm(name):
    t = time.perf_counter()
    try:
        yield
    finally:
        try:
            if _src_ctx(suppress_warning=True) is None:      # a plain side thread (e.g. the engine's parallel web lookups): nothing to record into
                raise LookupError
            ss = st.session_state
            ss.setdefault("_tm_cur", []).append((name, round((time.perf_counter() - t) * 1000)))
            if not name.startswith("cb:"):
                ss._tm_last = round((time.perf_counter() - _BZ_T0) * 1000)
        except Exception:
            pass


def _tm_show():
    ss = st.session_state
    if not ss.get("debug_timing"):
        return
    def fmt(r):
        return " · ".join(f"{n} {ms}" for n, ms in r["secs"] if ms >= 5 or n in ("css", "total")) or "-"
    runs = (ss.get("_tm_hist") or [])[-4:] + [{"secs": ss.get("_tm_cur") or [], "total": round((time.perf_counter() - _BZ_T0) * 1000), "at": ss.get("_tm_at")}]
    st.code("\n".join(f"{'this run' if i == len(runs) - 1 else 'earlier'} {r.get('at') or ''}: total {r['total']} ms | {fmt(r)}" for i, r in enumerate(runs)), language=None)


_tm_start()
st.session_state["_full"] = False          # set by a tap inside a fragment that needs the whole page redrawn (see feed_block)


def timed(name):
    import functools

    def deco(f):
        @functools.wraps(f)
        def w(*a, **k):
            with tm(name):
                return f(*a, **k)
        return w
    return deco


@st.cache_resource(show_spinner=False)
def _locked_rc_key(pc_hash, _pc):
    """Decrypt data/rc.lock once per process (slow KDF). Cached by a hash of the passcode, never shown."""
    return keylock.unlock(ROOT / "data" / "rc.lock", _pc) if (ROOT / "data" / "rc.lock").exists() else None


def _setup_rentcast():
    pc = secret("APP_PASSCODE") or st.session_state.get("_gate_pc", "")
    k = None
    if pc:
        import hashlib
        k = _locked_rc_key(hashlib.sha256(pc.strip().lower().encode()).hexdigest(), pc)
    rentcast.set_keys(k)            # RENTCAST_API_KEY (st.secrets -> environment) stays the fallback


_setup_rentcast()


@st.cache_resource(show_spinner=False)
def _locked_rapid_key(pc_hash, _pc):
    """Decrypt data/rapid.lock (RapidAPI key for the listings feed) once per process. Never shown."""
    return keylock.unlock(ROOT / "data" / "rapid.lock", _pc) if (ROOT / "data" / "rapid.lock").exists() else None


def _setup_listings():
    pc = secret("APP_PASSCODE") or st.session_state.get("_gate_pc", "")
    if pc:
        import hashlib
        listings.set_key(_locked_rapid_key(hashlib.sha256(pc.strip().lower().encode()).hexdigest(), pc) or secret("RAPIDAPI_KEY"))
    elif secret("RAPIDAPI_KEY"):
        listings.set_key(secret("RAPIDAPI_KEY"))


_setup_listings()


@st.cache_resource(show_spinner=False)
def _locked_saves_key(pc_hash, _pc):
    """Decrypt data/saves.lock (deploy key that can only write the private saved-homes backup repo). Never shown."""
    return keylock.unlock(ROOT / "data" / "saves.lock", _pc) if (ROOT / "data" / "saves.lock").exists() else None


def _setup_saves():
    pc = secret("APP_PASSCODE") or st.session_state.get("_gate_pc", "")
    if os.environ.get("BZ_NO_CLOUD"):          # local tests: keep saved homes in the browser only (never touch the real online copy)
        return
    k = None
    if pc:
        import hashlib
        k = _locked_saves_key(hashlib.sha256(pc.strip().lower().encode()).hexdigest(), pc)
    k = k or secret("BELLAZU_SAVES_DEPLOY_KEY")      # server: the key sits in its secrets file (the passcode lock stays the first choice)
    if k:
        saves.set_key(k)


_setup_saves()
if "rc_budget" not in st.session_state:     # optional test aid: ?rc_budget=N caps live RentCast lookups in this session (only lowers use)
    try:
        _b = st.query_params.get("rc_budget")
        st.session_state.rc_budget = max(int(_b), 0) if _b not in (None, "") else None
    except Exception:
        st.session_state.rc_budget = None

_t_css = time.perf_counter()
st.markdown("""<style>
/* Design language: dark editorial landing page. Near-black canvas, white type, hairline dividers, tall condensed uppercase
   display type (League Gothic), neo-grotesk body (Inter), serif wordmark (Instrument Serif), outlined + solid pill buttons,
   one soft rose accent. */
@import url('https://fonts.googleapis.com/css2?family=League+Gothic&family=Inter:wght@300;400;500;600;700&family=Instrument+Serif&display=swap');
:root {--ink:#141414; --ink2:#1B1B1B; --line:#2E2E2E; --line2:#3A3A3A; --paper:#FFFFFF; --mute:#A9A9A9; --rose:#F4A7BB; --rose2:#FFD3DE;
       --good:#8FE3B5; --maybe:#FFCF7A; --skip:#FF9DB5; --disp:'League Gothic', 'Oswald', Impact, sans-serif; --body:'Inter', system-ui, sans-serif}
html, body, .stApp, .stMarkdown, button, input, textarea, select, p, li, label {font-family:var(--body)}
[data-testid="stIconMaterial"], .material-symbols-rounded {font-family:'Material Symbols Rounded' !important}
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] {display:none !important}
.stApp {background:var(--ink); color:var(--paper)}
.block-container {padding-top:.4rem; padding-bottom:4rem; max-width:640px}
input {font-size:16px !important}
h1, h2, h3, h4, [data-testid="stHeading"] {font-family:var(--disp) !important; text-transform:uppercase; font-weight:400 !important; letter-spacing:.01em; line-height:.95 !important}
[data-testid="stMarkdownContainer"] h4 {font-size:2rem; margin:1.6rem 0 .5rem; padding-top:1rem; border-top:1px solid var(--line)}
[data-testid="stMarkdownContainer"] a {color:var(--rose)}
[data-testid="stCaptionContainer"], .stCaption {color:var(--mute) !important}
hr {border-color:var(--line) !important}
/* buttons: outlined pill (secondary), solid white pill (primary), uppercase micro-type */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-testid="stPopoverButton"] {
  min-height:3.3rem; border-radius:100px; border:1px solid var(--paper); background:transparent; color:var(--paper);
  text-transform:uppercase; letter-spacing:.06em; font-weight:500; font-size:.92rem; transition:color .35s cubic-bezier(.39,.575,.565,1), background-color .3s}
.stButton button:hover, .stDownloadButton button:hover, [data-testid="stPopoverButton"]:hover {background:var(--paper); color:var(--ink); border-color:var(--paper)}
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {
  background:var(--paper); color:var(--ink); border:1px solid var(--paper); font-weight:700; min-height:3.6rem}
.stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover {background:var(--rose); border-color:var(--rose); color:var(--ink)}
.stButton button[kind="tertiary"] {border:none; min-height:2.2rem; color:var(--rose); text-decoration:underline; text-underline-offset:4px; background:transparent}
.stButton button p, .stDownloadButton button p, .stFormSubmitButton button p, [data-testid="stPopoverButton"] p {font-weight:inherit}
/* inputs: outlined pills, centered uppercase placeholder like a newsletter field */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {background:transparent !important; border-radius:100px !important; border:1px solid var(--line2) !important}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {border-color:var(--paper) !important}
[data-baseweb="input"] input, [data-baseweb="select"] input {color:var(--paper) !important; padding-left:1.1rem !important}
[data-baseweb="input"] input::placeholder {color:#8C8C8C !important; text-transform:uppercase; letter-spacing:.05em; font-size:.85rem !important}
[data-testid="stTextInput"] label p, [data-testid="stSelectbox"] label p, [data-testid="stNumberInput"] label p, [data-testid="stWidgetLabel"] p {
  text-transform:uppercase; letter-spacing:.08em; font-size:.74rem !important; color:var(--mute); font-weight:500}
[data-testid="stNumberInput"] button {background:transparent; color:var(--paper); border:none}
/* pills + segmented controls */
[data-testid="stButtonGroup"] button {border-radius:100px !important; min-height:2.7rem; padding:0 1.05rem; border:1px solid var(--line2) !important; background:transparent !important;
  color:var(--paper) !important; text-transform:uppercase; letter-spacing:.05em; font-size:.8rem; font-weight:500}
[data-testid="stButtonGroup"] button[kind$="Active"], [data-testid="stButtonGroup"] button[data-selected="true"], [data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stButtonGroup"] button[aria-pressed="true"] {background:var(--paper) !important; color:var(--ink) !important; border-color:var(--paper) !important}
[data-testid="stButtonGroup"] button[kind$="Active"] *, [data-testid="stButtonGroup"] button[data-selected="true"] *, [data-testid="stButtonGroup"] button[aria-checked="true"] *,
[data-testid="stButtonGroup"] button[aria-pressed="true"] * {color:var(--ink) !important}
.st-key-mode [data-testid="stButtonGroup"] button {min-height:3.3rem; font-size:.86rem}
.st-key-lang [data-testid="stButtonGroup"] button {min-height:2.9rem !important; padding:0 1rem; font-size:.8rem; letter-spacing:.03em; text-transform:none}
/* expanders + popovers */
[data-testid="stExpander"] details {border:none; border-top:1px solid var(--line); border-bottom:1px solid var(--line); border-radius:0; background:transparent}
[data-testid="stExpander"] summary {padding-left:0}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary:hover, [data-testid="stExpander"] details[open] > summary {background:transparent !important; color:var(--paper) !important}
[data-testid="stExpander"] summary p {text-transform:uppercase; letter-spacing:.08em; font-size:.82rem; font-weight:500}
[data-testid="stPopoverBody"] {background:var(--ink2) !important; border:1px solid var(--line2) !important; border-radius:24px !important}
[data-testid="stAlert"] {background:var(--ink2); border:1px solid var(--line2); border-radius:20px; color:var(--paper)}
[data-testid="stDataFrame"] {border:1px solid var(--line); border-radius:12px}
/* top bar + hero */
.bz-top {display:flex; align-items:center; justify-content:space-between; padding:.2rem 0 .7rem; border-bottom:1px solid var(--line); margin-bottom:1.2rem}
.bz-word {font-family:'Instrument Serif', Georgia, serif; font-size:2rem; line-height:1; color:var(--paper)}
.bz-word i {color:var(--rose); font-style:normal}
.bz-eyebrow {text-transform:uppercase; letter-spacing:.1em; font-size:.74rem; color:var(--paper); display:flex; align-items:center; gap:.6rem; margin:.2rem 0 .8rem}
.bz-eyebrow:before {content:""; width:.55rem; height:.55rem; border-radius:50%; background:var(--rose); display:inline-block}
.bz-h1 {font-family:var(--disp); text-transform:uppercase; font-size:4.3rem; line-height:.9; letter-spacing:.01em; color:var(--paper); margin:0 0 .9rem}
.bz-h1 em {font-style:normal; color:var(--rose)}
.bz-lede {text-transform:uppercase; letter-spacing:.05em; font-size:.84rem; line-height:1.6; color:#D8D8D8; font-weight:300; margin:0 0 1.2rem; max-width:30rem}
.bz-marquee {overflow:hidden; border-top:1px solid var(--line); border-bottom:1px solid var(--line); margin:1.6rem 0 1.4rem; padding:.55rem 0; white-space:nowrap}
.bz-marquee .track {display:inline-block; animation:bzscroll 26s linear infinite; font-family:var(--disp); text-transform:uppercase; font-size:2.3rem; line-height:1}
.bz-marquee .o {color:transparent; -webkit-text-stroke:1px var(--paper)} .bz-marquee .f {color:var(--paper)} .bz-marquee .st {color:var(--rose); font-size:1.4rem; margin:0 .9rem; vertical-align:middle}
@keyframes bzscroll {from {transform:translateX(0)} to {transform:translateX(-50%)}}
@media (prefers-reduced-motion: reduce) {.bz-marquee .track {animation:none}}
.bz-steps {display:grid; grid-template-columns:1fr 1fr 1fr; border-top:1px solid var(--line); border-bottom:1px solid var(--line); margin:1.4rem 0 1rem}
.bz-steps .s {padding:.9rem .6rem .9rem 0; font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; color:#D8D8D8; line-height:1.35}
.bz-steps .s + .s {border-left:1px solid var(--line); padding-left:.7rem}
.bz-steps .n {display:block; font-family:var(--disp); font-size:2rem; color:var(--rose); line-height:1; margin-bottom:.25rem}
.bz-hello {font-family:var(--disp); text-transform:uppercase; font-size:2.6rem; line-height:.95; color:var(--paper); margin:.4rem 0 .5rem}
.bz-sub {text-transform:uppercase; letter-spacing:.05em; font-size:.8rem; line-height:1.6; color:#CFCFCF; font-weight:300; margin:.1rem 0 1.1rem}
.bz-addr {text-transform:uppercase; letter-spacing:.07em; font-size:.76rem; color:var(--mute); margin:.2rem 0 .6rem}
.bz-price {font-family:var(--body); font-weight:800; font-size:32px; line-height:1.1; letter-spacing:-.02em; color:var(--rose); margin:-.2rem 0 .15rem}
.bz-price .f {display:block; font-size:.95rem; font-weight:500; letter-spacing:0; color:#DADADA; margin-top:.2rem}
.bz-fh {font-family:var(--disp); text-transform:uppercase; font-size:1.75rem; line-height:1; color:var(--paper); margin:.55rem 0 .45rem}
.bz-tsum {border:1px solid var(--line2); border-radius:18px; background:var(--ink2); padding:.55rem .85rem; margin:.45rem 0 .2rem; font-size:.9rem; line-height:1.45}
.bz-tsum div + div {margin-top:.15rem}
/* result: verdict, tiles grid, airbnb line, cards */
.bz-verdict {border:1px solid var(--line2); border-radius:28px; padding:1.3rem 1.3rem 1.2rem; margin:.3rem 0 1rem; background:var(--ink2)}
.bz-verdict .big {font-family:var(--disp); text-transform:uppercase; font-size:3.4rem; line-height:.9; letter-spacing:.01em}
.bz-verdict .head {font-size:1.08rem; font-weight:600; margin-top:.6rem; line-height:1.4; color:var(--paper)}
.bz-verdict .why {font-size:1rem; margin-top:.3rem; line-height:1.5; color:#DADADA}
.bz-verdict .next {font-size:.95rem; margin-top:.9rem; padding-top:.8rem; border-top:1px solid var(--line2); line-height:1.5; color:#DADADA}
.bz-good .big {color:var(--good)} .bz-maybe .big {color:var(--maybe)} .bz-skip .big {color:var(--skip)}
.bz-good {box-shadow:inset 0 3px 0 var(--good)} .bz-maybe {box-shadow:inset 0 3px 0 var(--maybe)} .bz-skip {box-shadow:inset 0 3px 0 var(--skip)}
.bz-tiles {display:grid; grid-template-columns:1fr 1fr; border-top:1px solid var(--line); border-left:1px solid var(--line); margin:.4rem 0 1.1rem}
.bz-tile {border-right:1px solid var(--line); border-bottom:1px solid var(--line); padding:1rem .9rem .9rem}
.bz-tile .lbl {text-transform:uppercase; letter-spacing:.08em; font-size:.68rem; color:var(--mute)}
.bz-tile .num {font-family:var(--disp); font-size:2.6rem; line-height:1; color:var(--paper); margin:.35rem 0 .2rem; letter-spacing:.01em}
.bz-tile .sub {font-size:.78rem; color:#BDBDBD; line-height:1.35}
.bz-tile details {margin-top:.45rem; font-size:.78rem; color:#BDBDBD}
.bz-tile summary {color:var(--rose); cursor:pointer; list-style:none; text-transform:uppercase; letter-spacing:.06em; font-size:.66rem}
.bz-tile summary::-webkit-details-marker {display:none}
.bz-tile details p {margin:.3rem 0 0; line-height:1.4}
.bz-line {display:flex; gap:.7rem; align-items:flex-start; font-size:.95rem; padding:1rem 1.1rem; border-radius:100px; border:1px solid var(--rose); color:var(--paper); margin:.2rem 0 1.1rem; line-height:1.45}
.bz-ask {border:1px dashed var(--rose); border-radius:22px; padding:.85rem 1.1rem; margin:.2rem 0 .7rem; color:var(--paper); font-size:.95rem}
.bz-card {border:1px solid var(--line2); border-radius:24px; padding:1rem 1.1rem; margin:.65rem 0; background:var(--ink2)}
.bz-card .t {font-weight:600; color:var(--paper); line-height:1.35}
.bz-card .m {margin:.3rem 0; font-size:.98rem; color:#DADADA}
.bz-card .m b {color:var(--paper)}
.bz-card a {color:var(--rose); text-transform:uppercase; letter-spacing:.07em; font-size:.76rem; text-decoration:none; border-bottom:1px solid var(--rose)}
.bz-small {font-size:.85rem; color:var(--mute)}
.bz-small a {color:var(--rose)}
.bz-lbl {text-transform:uppercase; letter-spacing:.08em; font-size:.74rem; color:var(--mute); font-weight:500; margin:.6rem 0 .35rem}
html, body, .stApp, [data-testid="stMain"] {overflow-x:hidden !important; max-width:100vw}
[data-testid="stButtonGroup"] button {min-height:3rem !important}
.stButton button {min-height:3rem}
iframe[title*="searchbox"] {min-height:58px}
.bz-cmp {display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:6px; margin:.3rem 0 .7rem}
.bz-col {border:1px solid var(--line2); border-radius:18px; padding:.7rem .5rem .6rem; background:var(--ink2); min-width:0; overflow-wrap:anywhere}
.bz-col.star {border-color:var(--rose); box-shadow:inset 0 3px 0 var(--rose)}
.bz-col .tag {font-size:.58rem; color:var(--rose); text-transform:uppercase; letter-spacing:.05em; margin-bottom:.15rem}
.bz-col .h {text-transform:uppercase; letter-spacing:.04em; font-size:.68rem; color:var(--paper); font-weight:600; line-height:1.25; min-height:2.1em}
.bz-col .l {font-size:.6rem; text-transform:uppercase; letter-spacing:.06em; color:var(--mute); margin-top:.3rem}
.bz-col .n {font-family:var(--disp); font-size:2.05rem; line-height:1; margin:.15rem 0 .15rem; color:var(--paper)}
.bz-col .n.earn {color:var(--good)}
.bz-col .s {font-size:.7rem; color:#BDBDBD; line-height:1.3}
.bz-col .b {font-size:.66rem; margin-top:.45rem; padding-top:.4rem; border-top:1px solid var(--line2); line-height:1.3; color:#DADADA}
.bz-drive {display:flex; flex-direction:column; gap:.2rem; font-size:.92rem; border:1px solid var(--line2); border-radius:18px; padding:.65rem .95rem; margin:.1rem 0 .7rem; color:var(--paper)}
.bz-drive .x {font-size:.72rem; color:var(--mute)} .bz-drive a {color:var(--rose)}
.bz-bars {display:grid; grid-template-columns:repeat(12,1fr); gap:3px; align-items:end; height:90px; margin:.5rem 0 .2rem}
.bz-bars div {background:var(--rose); border-radius:4px 4px 0 0; min-height:4px} .bz-bars div.lo {background:#5A5A5A}
.bz-mon {display:grid; grid-template-columns:repeat(12,1fr); gap:3px; font-size:.62rem; color:var(--mute); text-align:center; margin-bottom:.4rem}
.bz-place {display:flex; gap:.75rem; align-items:flex-start; border-bottom:1px solid var(--line); padding:.65rem 0}
.bz-place img {width:68px; height:68px; object-fit:cover; border-radius:12px; flex:none; background:#222}
.bz-place .t {font-size:.92rem; color:var(--paper); line-height:1.3} .bz-place .m {font-size:.8rem; color:#BDBDBD; margin:.15rem 0}
.bz-place a {color:var(--rose); font-size:.72rem; text-transform:uppercase; letter-spacing:.06em}
.bz-warn.hi {border-width:2px; background:rgba(255,90,90,.08)}
.bz-warn {border:1px solid var(--skip); border-radius:18px; padding:.6rem .9rem; font-size:.88rem; margin:.3rem 0 .6rem; color:var(--paper)}
.bz-kv {display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.4rem 0; border-bottom:1px solid var(--line); font-size:.92rem; color:var(--paper)}
.bz-kv b {font-family:var(--disp); font-size:1.5rem; font-weight:400; white-space:nowrap}
.st-key-hmode [data-testid="stButtonGroup"] button {min-height:3.4rem; font-size:.74rem; white-space:normal; line-height:1.2}
[data-testid="stTabs"] button {min-height:3rem} [data-testid="stTabs"] button p {font-size:.85rem; text-transform:uppercase; letter-spacing:.05em}
[data-testid="stNumberInput"] input {font-size:16px !important}
.bz-home {border:1px solid var(--line2); border-radius:22px; overflow:hidden; margin:.8rem 0 .35rem; background:var(--ink2)}
.bz-home .ph {position:relative; aspect-ratio:3/2; background:#1c1c1c}
.bz-home .ph img {width:100%; height:100%; object-fit:cover; display:block}
.bz-home .ph .noimg {display:flex; align-items:center; justify-content:center; height:100%; font-size:2rem}
.bz-home .ph .pc {position:absolute; right:10px; bottom:10px; background:rgba(0,0,0,.65); color:#fff; font-size:.72rem; padding:.2rem .5rem; border-radius:10px}
.bz-home .bd {padding:.65rem .9rem .8rem}
.bz-home .p {font-family:var(--body); font-weight:800; font-size:30px; line-height:1.1; letter-spacing:-.02em; color:var(--rose)}
.bz-home .p .mo {font-size:.55em; font-weight:700; color:var(--rose2); margin-left:.1rem}
.bz-home .cut, .bz-home .new {font-family:var(--body, inherit); font-size:.7rem; vertical-align:middle; border-radius:10px; padding:.15rem .45rem; margin-left:.3rem; letter-spacing:.05em}
.bz-home .cut {background:var(--good); color:#111} .bz-home .new {background:var(--rose); color:#111}
.bz-home .m {font-size:.86rem; color:#DADADA; margin-top:.15rem} .bz-home .a {font-size:.8rem; color:var(--mute); margin-top:.3rem}
.bz-home .br {font-size:.66rem; color:var(--mute); margin-top:.2rem}
[data-testid="stLayoutWrapper"]:has(> .st-key-townbar) {position:sticky; top:0; z-index:90}   /* the wrapper is the element that can stick */
.st-key-townbar {background:var(--ink); padding:.45rem 0 .5rem; border-bottom:1px solid var(--line2)}
.st-key-townbar button {min-height:2.6rem}
.st-key-back_saved {flex:1 1 100%}
.st-key-back_saved button {min-height:2.6rem; border-color:var(--rose) !important; color:var(--rose) !important; background:var(--ink2) !important; font-weight:700; justify-content:flex-start}
[class*="st-key-tbx_"] button {border-radius:100px !important; background:var(--ink2) !important; border:1px solid var(--rose) !important; color:var(--paper) !important; text-transform:none !important; letter-spacing:0 !important}
.st-key-tb_change {flex:1 1 9rem}
.st-key-tpicker {background:var(--ink2)}
.bz-home .fha {font-size:.76rem; margin-top:.3rem; line-height:1.3} .bz-home .fha.ok {color:#9FE0B0} .bz-home .fha.no {color:#FFB38A} .bz-home .fha.q {color:#FFE08A}
.bz-fha {border:1px solid var(--line2); border-left:4px solid #9FE0B0; border-radius:16px; background:var(--ink2); padding:.6rem .8rem; margin:.5rem 0 .3rem; font-size:.9rem}
.bz-fha.no {border-left-color:#FFB38A} .bz-fha.q {border-left-color:#FFE08A}
.bz-fha .n {font-size:.8rem; margin-top:.3rem; color:#FFE08A} .bz-fha .s {font-size:.78rem; color:#CFCFCF; margin-top:.3rem}
.bz-rc {border:1px solid var(--rose); border-radius:20px; background:var(--ink2); padding:.75rem .85rem .6rem; margin:.7rem 0 .4rem}
.bz-rc .h {font-family:var(--disp); font-size:1.35rem; color:var(--paper); line-height:1.1}
.bz-rc .sub {font-size:.8rem; color:var(--mute); margin-top:.2rem}
.bz-rc .st {display:grid; grid-template-columns:1fr 1.4fr .8fr; gap:6px; margin:.5rem 0 .3rem}
.bz-rc .st div {background:var(--ink); border-radius:12px; padding:.35rem .45rem; min-width:0} .bz-rc .st span {display:block; font-size:.66rem; color:var(--mute); text-transform:uppercase; letter-spacing:.05em}
.bz-rc .st b {font-size:.92rem; color:var(--paper); white-space:nowrap}
.bz-rc .cmp {font-size:.86rem; color:var(--rose2); margin:.35rem 0 .45rem}
.bz-rc a {text-decoration:none !important; color:inherit !important}
.bz-rc.plain {border:0; background:transparent; padding:0; margin:0}
[class*="st-key-arvbox_"] {border:1px solid var(--rose); border-radius:20px; background:var(--ink2); padding:.75rem .85rem .6rem; margin:.7rem 0 .4rem; gap:0}
[class*="st-key-arvbox_"] [data-testid="stElementContainer"] {margin:0}
.bz-rc .row {display:grid; grid-template-columns:64px 1fr; gap:.6rem; align-items:center; padding:.35rem 0; border-top:1px solid var(--line)}
.bz-rc .row img, .bz-rc .row .ni {width:64px; height:48px; object-fit:cover; border-radius:10px; background:#222; display:flex; align-items:center; justify-content:center}
.bz-rc .row b {font-size:.92rem; color:var(--paper)} .bz-rc .row .f {font-size:.76rem; color:#CFCFCF} .bz-rc .row .f.a {color:var(--mute); overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.bz-rc .row > div {min-width:0}
.bz-rc .ex {font-size:.78rem; color:#DADADA; margin-top:.45rem; border-top:1px solid var(--line); padding-top:.4rem}
.bz-rc .src {font-size:.66rem; color:var(--mute); margin-top:.35rem}
.bz-rc .g {font-size:.72rem; color:var(--rose2); text-transform:uppercase; letter-spacing:.05em; margin:.65rem 0 .1rem}
.bz-rc .cue {font-size:.72rem; color:#9FE0B0} .bz-rc .cue.w {color:#FFB38A}
.bz-rc .pill {display:inline-block; border-radius:100px; padding:.15rem .6rem; font-size:.72rem; font-weight:600; margin-top:.35rem}
.bz-rc .pill.s {background:rgba(159,224,176,.14); color:#9FE0B0} .bz-rc .pill.a {background:rgba(245,211,122,.14); color:#F5D37A}
.bz-rc .big {display:grid; grid-template-columns:1fr 1fr; gap:6px; margin:.5rem 0 .3rem}
.bz-rc .big div {background:var(--ink); border-radius:12px; padding:.4rem .55rem; min-width:0} .bz-rc .big span {display:block; font-size:.66rem; color:var(--mute); text-transform:uppercase; letter-spacing:.05em}
.bz-rc .big b {font-size:1.05rem; color:var(--paper)} .bz-rc .big .sm {font-size:.72rem; color:#CFCFCF}
.bz-rc .cav {font-size:.76rem; color:#FFE08A; margin-top:.5rem; line-height:1.35}
.bz-home.nb {margin:0 0 .35rem; border-top:0; border-radius:0 0 22px 22px}
[class*="st-key-hcard_"] {margin-top:.8rem; gap:0 !important}
[class*="st-key-hcard_"] > div {width:100%}
.bz-tsel {display:flex; flex-wrap:wrap; align-items:center; gap:.35rem; font-size:.86rem; color:var(--paper); margin:.1rem 0}
.bz-tsel b {color:var(--rose)}
.bz-mt {display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:.4rem 0 .2rem}
.bz-mt .c {border:1px solid var(--line2); border-radius:18px; background:var(--ink2); padding:.6rem .65rem .55rem; min-width:0; overflow-wrap:anywhere}
.bz-mt .c.best {border-color:var(--rose)}
.bz-mt .t {font-family:var(--disp); font-size:1.25rem; line-height:1.1; color:var(--paper)}
.bz-mt .k {font-size:.7rem; color:var(--mute); margin-top:.35rem; text-transform:uppercase; letter-spacing:.05em}
.bz-mt .v {font-size:.84rem; color:#E6E6E6; margin-top:.1rem}
.bz-mt .r {display:flex; justify-content:space-between; gap:.3rem; font-size:.78rem; color:#DADADA; margin-top:.12rem}
.bz-mt .r b {color:var(--paper); white-space:nowrap} .bz-mt .r b.earn {color:var(--good)}
.bz-mt .s {font-size:.72rem; color:#CFCFCF; margin-top:.35rem; line-height:1.25}
.bz-gal {display:flex; overflow-x:auto; scroll-snap-type:x mandatory; gap:6px; border-radius:20px; margin:.3rem 0 .2rem; -webkit-overflow-scrolling:touch}
.bz-gal img {flex:0 0 100%; width:100%; aspect-ratio:3/2; object-fit:cover; scroll-snap-align:center; border-radius:20px}
/* saved homes */
.st-key-bz_store, [data-testid="stElementContainer"]:has(> .st-key-bz_store) {display:none !important}
.st-key-savedbtn button {min-height:2.7rem !important; padding:0 .85rem; font-size:.78rem; letter-spacing:.05em; border-color:var(--rose); color:var(--rose)}
.st-key-savedbtn button:hover {background:var(--rose); color:var(--ink)}
[class*="st-key-svon_"] button, [class*="st-key-svon_"] button:hover {background:var(--rose) !important; border-color:var(--rose) !important; color:var(--ink) !important; font-weight:700}
[class*="st-key-svoff_"] button {border-color:var(--rose); color:var(--rose)}
.bz-sv {display:flex; gap:.8rem; align-items:flex-start}
.bz-sv img, .bz-sv .noimg {width:104px; height:78px; object-fit:cover; border-radius:14px; flex:none; background:#222; display:flex; align-items:center; justify-content:center; font-size:1.6rem}
.bz-sv .t {font-weight:600; color:var(--paper); line-height:1.3; font-size:.95rem; overflow-wrap:anywhere}
.bz-sv .p {font-family:var(--body); font-weight:800; font-size:26px; line-height:1.1; letter-spacing:-.02em; color:var(--rose); margin-top:.2rem}
.bz-sv .m {font-size:.8rem; color:#CFCFCF; margin-top:.1rem; line-height:1.35} .bz-sv .d {font-size:.72rem; color:var(--mute); margin-top:.2rem}
.bz-sv-nums {margin:.55rem 0 .2rem} .bz-sv-nums .bz-col .n {font-size:1.6rem} .bz-sv-nums .bz-col .h {min-height:0}
.bz-sv-b {font-size:.8rem; color:#DADADA; margin:.15rem 0; line-height:1.35}
[data-baseweb="textarea"] {border-radius:18px !important; background:var(--ink) !important}
[data-baseweb="textarea"] textarea {background:var(--ink) !important; color:var(--paper) !important; font-size:16px !important}
[data-baseweb="textarea"] textarea::placeholder {color:#8C8C8C !important}
[data-testid="stFileUploaderDropzone"] {background:var(--ink2) !important; border:1px dashed var(--rose) !important; border-radius:22px !important; color:var(--paper) !important}
[data-testid="stFileUploaderDropzone"] button {background:transparent !important; color:var(--paper) !important; border:1px solid var(--paper) !important; border-radius:100px !important}
[data-testid="stFileUploaderDropzone"] button *, [data-testid="stFileUploaderDropzoneInstructions"] * {color:var(--paper) !important}
[data-testid="stFileUploaderDropzoneInstructions"] small {color:var(--mute) !important}
[data-testid="stFileUploaderDropzoneInstructions"] {display:none !important}
[data-testid="InputInstructions"] {display:none !important}   /* Streamlit's English "Press Enter to apply" hint */
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p {font-size:0 !important}
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {content:var(--bz-up); font-size:.85rem}
[data-testid="stFileUploaderFile"] * {color:var(--paper) !important}
.stLinkButton a {border-radius:100px !important; border:1px solid var(--paper) !important; background:transparent !important; color:var(--paper) !important; min-height:2.8rem;
  text-transform:uppercase; letter-spacing:.06em; font-size:.8rem !important; font-weight:500}
.stLinkButton a * {color:var(--paper) !important}
[class*="st-key-svcard_"] {border:1px solid var(--line2) !important; border-radius:22px !important; background:var(--ink2); padding:.9rem .9rem .5rem !important}
.bz-foot {text-transform:uppercase; letter-spacing:.08em; font-size:.66rem; color:#7D7D7D; text-align:center; margin-top:1.4rem}
/* ---- Calm pass (2026-09-26): sentence case, two type sizes for UI text (1rem / .85rem) and three weights (400/600/800),
   fewer outlined boxes (whitespace instead), muted grey only for secondary text. Brand pieces (wordmark, landing headline) keep their look. */
h1, h2, h3, h4, [data-testid="stHeading"] {font-family:var(--body) !important; text-transform:none; font-weight:800 !important; letter-spacing:-.015em; line-height:1.2 !important}
[data-testid="stMarkdownContainer"] h4 {font-size:1.25rem; margin:2rem 0 .6rem; padding-top:0; border-top:0}
.stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-testid="stPopoverButton"], .stLinkButton a {text-transform:none; letter-spacing:0; font-size:1rem !important; font-weight:600}
.stButton button[kind="tertiary"] {text-decoration:none; font-weight:600}
[data-baseweb="input"] input::placeholder {text-transform:none; letter-spacing:0; font-size:1rem !important}
[data-testid="stTextInput"] label p, [data-testid="stSelectbox"] label p, [data-testid="stNumberInput"] label p, [data-testid="stWidgetLabel"] p {text-transform:none; letter-spacing:0; font-size:.85rem !important; font-weight:600}
[data-testid="stButtonGroup"] button {text-transform:none; letter-spacing:0; font-size:.9rem; font-weight:600}
[data-testid="stExpander"] details {border-top:0; border-bottom:1px solid var(--line)}
[data-testid="stExpander"] summary p {text-transform:none; letter-spacing:0; font-size:1rem; font-weight:600}
[data-testid="stExpander"] summary svg {color:var(--mute)}
[data-testid="stTabs"] button p {text-transform:none; letter-spacing:0; font-size:.95rem; font-weight:600}
.bz-eyebrow, .bz-lede, .bz-steps .s, .bz-sub, .bz-tile .lbl, .bz-tile summary, .bz-card a, .bz-col .tag, .bz-col .h, .bz-col .l, .bz-place a,
.bz-rc .st span, .bz-mt .k, .bz-foot {text-transform:none !important; letter-spacing:0 !important}
.bz-lede, .bz-sub {font-size:1rem; font-weight:400}
.bz-hello {font-family:var(--body); text-transform:none; font-weight:800; font-size:2rem; letter-spacing:-.025em; line-height:1.15; margin:.6rem 0 .2rem}
.bz-fh {font-family:var(--body); text-transform:none; font-weight:800; font-size:1.25rem; letter-spacing:-.015em; margin:1.4rem 0 .5rem}
.bz-addr {text-transform:none; letter-spacing:0; font-size:1rem; color:var(--paper); margin:.5rem 0 .1rem}
.bz-lbl {text-transform:none; letter-spacing:0; font-size:.85rem; font-weight:600; color:var(--mute); margin:.9rem 0 .35rem}
.bz-verdict .big {font-family:var(--body); text-transform:none; font-size:1.9rem; font-weight:800; letter-spacing:-.02em; line-height:1.1}
.bz-rc .h {font-family:var(--body); font-weight:800; font-size:1.1rem}
.bz-card, .bz-drive, .bz-fha, .bz-rc, .bz-mt {border:0 !important; border-radius:20px}
.bz-fha {border-left:3px solid #9FE0B0 !important; border-radius:6px 16px 16px 6px}
.bz-rc {background:transparent; padding:.2rem 0 .4rem}
.bz-tl {font-size:1rem; color:var(--paper); margin:0 0 .6rem; line-height:1.5}
/* home cards: photo + one line, generous space between cards */
.bz-hl {display:flex; align-items:center; gap:.5rem; font-size:1rem; color:var(--paper); line-height:1.35; min-height:2.4rem}
.bz-hl .x {color:var(--mute)}
[class*="st-key-hcard_"] {margin-top:1.6rem}
[class*="st-key-hrow_"] {margin-top:.15rem; gap:.25rem !important}
[class*="st-key-hrow_"] .stButton button, [class*="st-key-svrow_"] .stButton button {min-height:2.4rem; border:0; padding:0 .6rem; font-weight:600}
[class*="st-key-hrow_"] .stButton button:hover {background:transparent; color:var(--rose)}
[class*="st-key-hrow_"] .stLinkButton a {border:0 !important; min-height:2.4rem; color:var(--rose) !important}
[class*="st-key-hrow_"] .stLinkButton a * {color:var(--rose) !important}
/* lighter For sale / For rent switch */
[class*="st-key-hst_"] [data-testid="stButtonGroup"] button {min-height:2.3rem; border:0 !important; border-radius:0 !important; background:transparent !important; color:var(--mute) !important; padding:0 .2rem; margin-right:1.1rem}
[class*="st-key-hst_"] [data-testid="stButtonGroup"] button * {color:var(--mute) !important}
[class*="st-key-hst_"] [data-testid="stButtonGroup"] button[kind$="Active"], [class*="st-key-hst_"] [data-testid="stButtonGroup"] button[aria-checked="true"],
[class*="st-key-hst_"] [data-testid="stButtonGroup"] button[data-selected="true"], [class*="st-key-hst_"] [data-testid="stButtonGroup"] button[aria-pressed="true"] {background:transparent !important; box-shadow:inset 0 -2px 0 var(--rose)}
[class*="st-key-hst_"] [data-testid="stButtonGroup"] button[kind$="Active"] *, [class*="st-key-hst_"] [data-testid="stButtonGroup"] button[aria-checked="true"] *,
[class*="st-key-hst_"] [data-testid="stButtonGroup"] button[data-selected="true"] *, [class*="st-key-hst_"] [data-testid="stButtonGroup"] button[aria-pressed="true"] * {color:var(--paper) !important}
/* lighter filters bar + "About this town" */
[class*="st-key-hflt_"] details, [class*="st-key-tinfo_"] details, .st-key-mt_sum details {border-bottom:0 !important}
[class*="st-key-hflt_"] summary p, [class*="st-key-tinfo_"] summary p, .st-key-mt_sum summary p {font-size:.9rem; font-weight:600; color:var(--mute)}
/* home detail: 3-number summary */
.bz-3 {display:grid; grid-template-columns:repeat(3, 1fr); gap:.5rem; margin:1rem 0 .4rem}
.bz-3 div {background:var(--ink2); border-radius:16px; padding:.7rem .6rem; min-width:0}
.bz-3 b {display:block; font-size:1.3rem; font-weight:800; letter-spacing:-.02em; color:var(--paper); white-space:nowrap}
.bz-3 span {display:block; font-size:.8rem; color:var(--mute); line-height:1.3; margin-top:.15rem}
.bz-3n {font-size:.85rem; color:var(--mute); margin:.2rem 0 1rem}
/* saved cards: photo on top, no outlined box */
[class*="st-key-svcard_"] {border:0 !important; background:transparent; padding:0 !important; margin-top:1.4rem}
.bz-svh {font-size:1rem; color:var(--paper); line-height:1.35; margin:.45rem 0 .1rem}
.bz-svh .x {color:var(--mute); font-size:.85rem}
[class*="st-key-svrow_"] {gap:.2rem !important; margin-top:.1rem}
[class*="st-key-svrow_"] .stLinkButton a {border:0 !important; min-height:2.4rem; color:var(--rose) !important; font-weight:600}
[class*="st-key-svrow_"] .stLinkButton a * {color:var(--rose) !important}
[class*="st-key-svdt_"] details, [class*="st-key-svnx_"] details {border-bottom:0 !important}
[class*="st-key-svcard_"] {gap:.35rem !important}
[class*="st-key-svdt_"] summary p, [class*="st-key-svnx_"] summary p {font-size:.95rem; font-weight:600; color:var(--mute)}
/* My loan: approval tag + monthly under each card, and the home's breakdown */
.bz-cm {font-size:.9rem; color:var(--paper); line-height:1.45; margin:-.2rem 0 .2rem}
.bz-cm .x {color:var(--mute); font-size:.85rem}
.bz-cm .ff {color:#FFB38A; font-size:.85rem; font-weight:600}
.bz-cm .cn {color:#FFE08A; font-size:.85rem}
.tg {font-weight:600} .tg.g {color:#9FE0B0} .tg.y {color:#F5D37A} .tg.r {color:#F28B8B}
.bz-tag {display:inline-block; border-radius:100px; padding:.3rem .8rem; font-weight:600; font-size:.9rem; margin:.1rem 0 .5rem}
.bz-tag.g {background:rgba(159,224,176,.14); color:#9FE0B0} .bz-tag.y {background:rgba(245,211,122,.14); color:#F5D37A} .bz-tag.r {background:rgba(242,139,139,.14); color:#F28B8B}
.bz-bd {width:100%; border-collapse:collapse; font-size:.92rem; margin:.2rem 0 .4rem}
.bz-bd td {padding:.28rem 0; vertical-align:top} .bz-bd td.n {text-align:right; white-space:nowrap; font-weight:600; padding-left:.6rem}
.bz-bd td .x {display:block; color:var(--mute); font-size:.8rem} .bz-bd tr.t td {border-top:1px solid var(--line2); font-weight:800; padding-top:.45rem}
</style>""", unsafe_allow_html=True)
st.session_state.setdefault("_tm_cur", []).append(("css", round((time.perf_counter() - _t_css) * 1000)))
st.session_state._tm_cur.insert(0, ("boot", round((_t_css - _BZ_T0) * 1000)))


# ------------------------------------------------------------------ language (one at a time) + helpers
if "sv_sid" not in st.session_state:
    st.session_state.sv_sid = os.urandom(6).hex()
    _ql = str(st.query_params.get("lang") or "").strip().lower()
    if _ql in ("es", "en"):
        st.session_state.lang = _ql.upper()
        st.session_state.lang_src = "url"
        st.session_state.lang_t = int(time.time() * 1000)
        st.session_state.setdefault("sv", {"v": 1, "sync": None, "items": {}, "removed": {}})["prefs"] = {"lang": _ql.upper(), "t": st.session_state.lang_t}
    _qt = str(st.query_params.get("towns") or "").strip()          # ?towns=secaucus,kearny opens those towns side by side
    if _qt:
        _ts = []
        for _x in _qt.split(",")[:12]:
            _tn = towns.normalize(_x.replace("-", " ").strip())
            if _tn.get("name") and _tn.get("match") in ("exact", "alias", "fuzzy") and _tn["name"] not in _ts and _tn["name"] != "New York City":
                _ts.append(_tn["name"])
        if _ts:
            st.session_state.tsel = _ts[:6]
            st.session_state.tsel_boot = True
    _qh = re.sub(r"\D", "", str(st.query_params.get("home") or ""))[:14]        # ?home=<listing id> opens that listing's detail page (after the passcode)
    if _qh:
        st.session_state.home_boot = _qh
    st.session_state.setdefault("lang", "EN")



def ES():
    return st.session_state.get("lang", "EN") == "ES"


def L(en, es):
    return es if ES() else en


def P(pair):
    return pair[1] if ES() else pair[0]


def html(s):
    st.markdown(s.replace("$", "&#36;"), unsafe_allow_html=True)


def md(s):
    st.markdown(s.replace("$", "\\$"))


def cap(s):
    """st.caption with dollar signs kept literal (two $ in one line would turn into math)."""
    st.caption(s.replace("$", "\\$"))


@timed('header')
def header(authed=False):
    top = st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute", key="topbar")
    top.markdown("<div class='bz-word'>Bella<i>Zu</i></div>", unsafe_allow_html=True)
    top.segmented_control(L("Language", "Idioma"), ["EN", "ES"], key="lang", required=True, label_visibility="collapsed",
                          format_func=lambda k: "English" if k == "EN" else "Español", on_change=_lang_changed)
    if authed:
        n = len(sv()["items"])
        st.button(f"♥ {L('My saved homes', 'Mis casas guardadas')} · {n}", key="savedbtn", on_click=_go_saved, width="stretch")
    html("<div style='border-bottom:1px solid #2E2E2E; margin:-.3rem 0 1.1rem'></div>")


def header_hero():
    html(f"<div class='bz-eyebrow'>{L('For first-time buyers in North Jersey', 'Para primeros compradores en el norte de NJ')}</div>"
         f"<div class='bz-h1'>{L('Your first home, <em>made simple.</em>', 'Su primera casa, <em>sin complicaciones.</em>')}</div>"
         f"<div class='bz-lede'>{L('Type an address or a town. See what you would pay each month living there alone, with a tenant, or with Airbnb or 30+ day guests.', 'Escriba una dirección o un pueblo. Vea lo que pagaría al mes viviendo allí sin nadie más, con un inquilino, o con huéspedes de Airbnb o de 30+ días.')}</div>")


def marquee():
    words = [L("Check a home", "Revise una casa"), L("Find rentals", "Busque alquileres"), L("Plain answers", "Respuestas claras"), L("Free to use", "Gratis")]
    seq = "".join(f"<span class='{'f' if i % 2 == 0 else 'o'}'>{H.escape(w)}</span><span class='st'>✺</span>" for i, w in enumerate(words))
    html(f"<div class='bz-marquee' aria-hidden='true'><div class='track'>{seq}{seq}</div></div>")


# ------------------------------------------------------------------ saved homes: state (the UI is further down)
def sv():
    return st.session_state.setdefault("sv", saves.empty())


def _go_saved():
    st.session_state.page = "saved"


def _sv_secret():
    return secret("APP_PASSCODE") or st.session_state.get("_gate_pc", "")


def _sv_touch(push=True):
    """The list changed: write it to this browser (next render) and to the online copy (background)."""
    ss = st.session_state
    ss._full = True                         # the header count and this browser's copy are drawn outside any fragment
    ss.sv_ver = int(ss.get("sv_ver", 0)) + 1
    if push and ss.get("sv_loaded"):
        saves.cloud_put(_sv_secret(), sv())


def _lang_from_prefs(d, force=False):
    """Apply a saved language choice (unless the URL chose one for this visit)."""
    ss = st.session_state
    pr = (d or {}).get("prefs") or {}
    if ss.get("lang_src") == "url" and not force:
        return
    if pr.get("lang") in ("EN", "ES") and int(pr.get("t", 0)) > int(ss.get("lang_t", 0)):
        ss.lang, ss.lang_t = pr["lang"], int(pr["t"])


@timed('cb:sv_loaded')
def _sv_on_loaded():
    """localStorage answered (first render of each session, even on the passcode screen)."""
    ss = st.session_state
    v = (ss.get("bz_store") or {}).get("loaded") or {}
    if v.get("sid") != ss.get("sv_sid") or ss.get("sv_raw") is not None:
        return
    ss.sv_raw = v.get("raw") or ""
    ss.sv_storage_ok = not v.get("err")
    try:
        stored = saves.normalize(json.loads(ss.sv_raw)) if ss.sv_raw else None
    except Exception:
        stored = None
    if stored and (stored.get("prefs") or {}).get("lang"):
        _lang_from_prefs(stored)
    elif not ss.get("lang_t") and ss.get("lang_src") != "url" and str(v.get("nav") or "").lower().startswith("es"):
        ss.lang = "ES"                                   # first visit on a Spanish phone
    ss.sv_lang_ready = True
    if ss.get("authed"):
        _sv_process()


@timed('sv_process')
def _sv_process():
    """Merge browser + online copy so neither ever drops a home (runs once per session, after the passcode)."""
    ss = st.session_state
    try:
        stored = saves.normalize(json.loads(ss.sv_raw)) if ss.get("sv_raw") else None
    except Exception:
        stored = None
    ss.sv = saves.merge(stored, sv()) if stored else saves.normalize(sv())
    ss.sv_loaded = True
    if saves.cloud_available():
        saves.cloud_put(_sv_secret(), ss.sv)      # fetch + merge + push only if something is new, in the background
        m = saves.cloud_merged()                  # whatever already came back; the rest arrives via _sv_poll (no waiting here)
        if m:
            ss.sv = saves.merge(ss.sv, m)
        ss.sv_polling = time.time()
    _lang_from_prefs(ss.sv)
    if not saves.same(ss.sv, stored or saves.empty()):
        ss.sv_ver = int(ss.get("sv_ver", 0)) + 1  # write the merged list back to this browser


PICKS_FILE = ROOT / "data" / "bella_picks.json"      # readable copy (source tree only)
PICKS_LOCK = ROOT / "data" / "bella_picks.lock"      # what ships: the same list, encrypted with the app passcode (keeps addresses out of the public repo)
_PICKS_MEMO = {}


def _picks_entries():
    """Saved-home entries for the shared picked list (data/bella_picks.json): built from saved listing snapshots, no API calls."""
    d = None
    try:
        if PICKS_FILE.exists():
            d = json.loads(PICKS_FILE.read_text())
        elif PICKS_LOCK.exists():
            pc = _sv_secret()
            if pc not in _PICKS_MEMO:
                t_ = keylock.unlock(PICKS_LOCK, pc)
                _PICKS_MEMO[pc] = json.loads(t_) if t_ else None
            d = _PICKS_MEMO[pc]
    except Exception:
        d = None
    if not d:
        return []
    out = []
    for h in d.get("homes") or []:
        try:
            if not h.get("id") or not h.get("address"):
                continue
            hm = home_money(h) or {}
            tl = list(FEED_TYPE_LBL.get(h.get("kind"), FEED_TYPE_LBL["other"]))
            if hm.get("coop"):
                tl = ["Co-op", "Co-op"]
            fl = _facts_line(h.get("beds"), h.get("baths"), h.get("sqft"), tl, hm.get("hoa") or h.get("hoa_monthly"))
            ms = int(d.get("saved_ms") or saves.now_ms())
            photos = [p_ for p_ in (h.get("photos") or []) if p_]
            e = {"id": saves.item_id("listing", h["id"]), "kind": "home", "title": h["address"], "saved": d.get("saved") or _today(), "saved_ms": ms,
                 "updated": ms, "status": "interested", "note": "", "pick": True}
            e.update(addr=h["address"], town=h.get("town"), price=h.get("price"), rent=False, beds=h.get("beds"), baths=h.get("baths"), sqft=h.get("sqft"),
                     hoa=h.get("hoa_monthly"), type_lbl=tl, facts_line_en=fl[0], facts_line_es=fl[1], photo=h.get("photo") or _thumb(photos[0] if photos else None),
                     photos=photos[:8], url=h.get("url"), listing_id=str(h["id"]), broker=h.get("broker"), facts_over=_listing_facts(h),
                     safety=_caution(h.get("town")))
            out.append(e)
        except Exception:
            continue
    return out


def _seed_picks():
    """Merge the shared picked homes into this session's list. A home that was removed (tombstone) or is already saved is not re-added."""
    ss = st.session_state
    try:
        have = {str(x.get("listing_id")) for x in sv()["items"].values() if x.get("listing_id")} | {_norm_addr(x.get("addr")) for x in sv()["items"].values()}
        seed = saves.empty()
        for e in _picks_entries():
            if e["listing_id"] in have or _norm_addr(e["addr"]) in have:
                continue
            seed["items"][e["id"]] = e
        if seed["items"]:
            ss.sv = saves.merge(ss.sv, seed)
    except Exception:
        pass


def _lang_changed():
    """The user flipped English / Español: remember it here and online (with a time so the newest choice wins)."""
    ss = st.session_state
    ss.lang_t = saves.now_ms()
    ss.lang_src = "user"
    sv()["prefs"] = {"lang": ss.get("lang", "EN"), "t": ss.lang_t}
    _sv_touch()


def _sv_pull_merged(apply_lang=True):
    """Pick up what a background sync brought back from the online copy (e.g. homes saved on another device)."""
    ss = st.session_state
    if not ss.get("sv_loaded"):
        return
    m = saves.cloud_merged()
    if m and not saves.same(saves.merge(sv(), m), sv()):
        ss.sv = saves.merge(sv(), m)
        if apply_lang:                      # only before the language toggle is drawn in this run
            _lang_from_prefs(ss.sv)
        _sv_touch(push=False)



STORE_JS = """
export default function ({ data, setStateValue }) {
  const w = window, K = "bellazu_saves_v1";
  const sid = (data && data.sid) || "";
  if (w.__bzSid !== sid) {
    w.__bzSid = sid; w.__bzVer = 0;
    let raw = null, err = null;
    try { raw = w.localStorage.getItem(K); } catch (e) { err = String(e); }
    setStateValue("loaded", { raw: raw, err: err, sid: sid, nav: (navigator.language || "") });
  }
  if (data && typeof data.write === "string" && data.ver > (w.__bzVer || 0)) {
    try { w.localStorage.setItem(K, data.write); w.__bzVer = data.ver; setStateValue("ack", data.ver); }
    catch (e) { setStateValue("ack", -data.ver); }
  }
}
"""
_STORE = st.components.v2.component("bz_store", js=STORE_JS)


def _sv_on_ack():
    ss = st.session_state
    a = (ss.get("bz_store") or {}).get("ack")
    if isinstance(a, (int, float)):
        if a > 0:
            ss.sv_ack = max(int(ss.get("sv_ack", 0)), int(a))
        else:
            ss.sv_storage_ok = False




@timed('store')
def storage_bridge(gate_page=False):
    """Browser storage (localStorage): read once per session, write whenever the list or the language changed. Hidden."""
    ss = st.session_state
    ver = int(ss.get("sv_ver", 0))
    data = {"sid": ss.sv_sid, "ver": ver}
    if ss.get("sv_loaded") and ver > int(ss.get("sv_ack", 0)):
        data["write"] = json.dumps(saves.normalize(sv()), separators=(",", ":"), ensure_ascii=False)
    if gate_page:
        _STORE(key="bz_store", data=data, default={"loaded": None, "ack": None}, on_loaded_change=_sv_on_loaded, on_ack_change=_sv_on_ack)
        return
    with store_slot:
        _STORE(key="bz_store", data=data, default={"loaded": None, "ack": None}, on_loaded_change=_sv_on_loaded, on_ack_change=_sv_on_ack)


# ------------------------------------------------------------------ passcode gate
@timed('gate')
def gate():
    header()
    st.markdown(f"<div class='bz-eyebrow'>{L('Private beta', 'Beta privada')}</div>"
                f"<div class='bz-h1'>{L('Welcome to <em>BellaZu</em>', 'Bienvenida a <em>BellaZu</em>')}</div>"
                f"<div class='bz-lede'>{L('Type your passcode to come in 💕', 'Escriba su código para entrar 💕')}</div>", unsafe_allow_html=True)
    storage_bridge(gate_page=True)
    pc = secret("APP_PASSCODE").lower()
    if not pc:
        st.error(L("This app is not set up yet (missing APP_PASSCODE).", "La app aún no está configurada (falta APP_PASSCODE)."))
        st.stop()
    n = st.session_state.get("fails", 0)
    if n >= 15:
        st.error(L("Too many tries. Reload the page later.", "Demasiados intentos. Recargue la página más tarde."))
        st.stop()
    with st.form("gate"):
        typed = st.text_input(L("Passcode", "Código"), type="password", key="gate_pc_in")
        ok = st.form_submit_button(L("Enter", "Entrar"), type="primary", width="stretch")
    if ok:
        if hmac.compare_digest(typed.strip().lower().encode(), pc.encode()):
            st.session_state.authed = True
            st.session_state.fails = 0
            st.session_state._gate_pc = typed.strip().lower()   # server-side only; unlocks data/rc.lock if secrets lack it
            st.rerun()
        else:
            st.session_state.fails = n + 1
            time.sleep(min(1 + n, 5))       # slow down guessing
            st.error(L("Hmm, that passcode didn't work. Try again 💕", "Ese código no funcionó. Intente otra vez 💕"))
    st.stop()


if not st.session_state.get("authed"):
    gate()

ss_ = st.session_state
if ss_.get("sv_raw") is not None and not ss_.get("sv_loaded"):
    _sv_process()
if not ss_.get("sv_prefetch") and saves.cloud_available():      # start reading the online copy while the page draws
    ss_.sv_prefetch = True
    saves.cloud_put(_sv_secret(), saves.empty())
_sv_pull_merged()
header(authed=True)
store_slot = st.container()     # the browser-storage bridge is drawn here at the very end of the run (after every change)


# ------------------------------------------------------------------ shared bits
@timed("rep:prop_xlsx")
def xlsx_bytes(r, kind):
    with tempfile.TemporaryDirectory() as d:
        files = write_property(r, d, st.session_state.get("prop_cv"), lang="es" if ES() else "en") if kind == "property" else write_arbitrage(r, d)
        return pathlib.Path(files["xlsx"]).read_bytes(), pathlib.Path(files["xlsx"]).name


def _xlsx_or_note(make):
    """Build an Excel file only when the download is tapped. If it fails, a one-sheet file says so (server log has the detail)."""
    try:
        return make()
    except Exception as e:
        import io, traceback
        traceback.print_exc()
        import pandas as pd
        b = io.BytesIO()
        pd.DataFrame({"BellaZu": [f"The Excel file couldn't be made this time ({e.__class__.__name__}). / No se pudo crear el archivo de Excel esta vez."]}).to_excel(b, index=False)
        return b.getvalue()


def _prop_xlsx(r, cv, lg):
    with tempfile.TemporaryDirectory() as d:
        return pathlib.Path(write_property(r, d, cv, lang=lg)["xlsx"]).read_bytes()


def _town_xlsx(a, cv, lg):
    with tempfile.TemporaryDirectory() as d:
        return pathlib.Path(write_town(a, cv, d, lang=lg)).read_bytes()


def _fslug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")[:60]


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:50]


def verdict_box(v):
    lvl = v["level"]
    if v.get("title_en"):      # town scan: the title is the rule itself
        big = v['title_es'] if ES() else v['title_en']
        head = ""
    else:
        big = {"good": L("Good deal", "Buen negocio"), "maybe": L("Maybe", "Tal vez"), "skip": L("Skip this one", "Mejor no")}[lvl]
        head = {"good": L("Great news, this one could work!", "¡Buenas noticias, esta podría funcionar!"),
                "maybe": L("This one could work, but let's check a few things first.", "Esta podría funcionar, pero revisemos algunas cosas primero."),
                "skip": L("This one's not a fit, and here's why:", "Esta no le conviene, y le explicamos por qué:")}[lvl]
    nxt = v.get("next_es" if ES() else "next_en")
    html(f"<div class='bz-verdict bz-{lvl}'><div class='big'>{H.escape(big)}</div>"
         + (f"<div class='head'>{H.escape(head)}</div>" if head else "")
         + f"<div class='why'>{H.escape(v['es'] if ES() else v['en'])}</div>"
         + (f"<div class='next'>👉 <b>{L('What to do next:', 'Qué hacer ahora:')}</b> {H.escape(nxt)}</div>" if nxt else "") + "</div>")


def tiles(items):
    cells = "".join(f"<div class='bz-tile'><div class='lbl'>{H.escape(a)}</div><div class='num'>{H.escape(b)}</div><div class='sub'>{H.escape(c)}</div>"
                    + (f"<details><summary>{L('What does this mean?', '¿Qué significa?')}</summary><p>{H.escape(t[3])}</p></details>" if len(t) > 3 else "")
                    + "</div>" for t in items for a, b, c in [t[:3]])
    html(f"<div class='bz-tiles'>{cells}</div>")


def rc_usage_line():
    u = rentcast.usage()
    if u.get("key_state") == "refused":
        return L("Price lookups are off right now (RentCast didn't accept the key), so free sources are used. Add the price when we ask; everything else still works.",
                 "Las búsquedas de precio están apagadas por ahora (RentCast no aceptó la clave); se usan fuentes gratuitas. Agregue el precio cuando se lo pidamos; todo lo demás funciona.")
    if not u["enabled"]:
        return L("RentCast is off, so only free sources are used.", "RentCast está apagado; solo se usan fuentes gratuitas.")
    s = L(f"RentCast lookups used this month: {u['used']} of {u['free_plan']} (this app's own count).",
          f"Consultas de RentCast usadas este mes: {u['used']} de {u['free_plan']} (conteo de esta app).")
    if u["used"] >= u["cap"]:
        s += " " + L("Monthly limit reached, so free sources are used until next month.", "Se alcanzó el límite mensual; se usan fuentes gratuitas hasta el próximo mes.")
    return s


def addr_from_link(url):
    """Best-effort address from a Zillow/Redfin/Realtor URL slug (the page itself may be blocked)."""
    m = re.search(r"zillow\.com/homedetails/([^/]+)/", url) or re.search(r"redfin\.com/[A-Z]{2}/[^/]+/([^/]+)/", url) \
        or re.search(r"realtor\.com/realestateandhomes-detail/([^/]+)", url)
    if not m:
        return ""
    s = m.group(1).replace("-", " ")
    s = re.sub(r"\b(APT|UNIT)\b", lambda x: x.group(1).title(), s)
    s = re.sub(r"_M\d+.*$", "", s)
    s = re.sub(r"\s([A-Z]{2})\s(\d{5})$", r", \1 \2", s)
    return s


# ------------------------------------------------------------------ Check a home: result
COST_LBL = {"principal_interest": ("Mortgage payment (loan + interest)", "Pago de la hipoteca (préstamo + interés)"),
            "hoa_or_maintenance": ("Building fee (HOA / maintenance)", "Cuota del edificio (HOA / mantenimiento)"),
            "property_tax": ("Property tax", "Impuesto a la propiedad"), "insurance": ("Home insurance", "Seguro de la vivienda"),
            "utilities": ("Utilities (power, gas, internet)", "Servicios (luz, gas, internet)"),
            "repairs_reserve": ("Savings for repairs", "Ahorro para reparaciones")}
TYPE_LBL = {"co-op": ("Co-op", "Co-op"), "condo": ("Condo", "Condo"), "single-family": ("House", "Casa"), "multi-family": ("2 to 4 family", "Multifamiliar"),
            "townhouse": ("Townhouse", "Townhouse")}
INC_LBL = {"taxes": ("taxes", "impuestos"), "utilities": ("utilities", "servicios"), "internet": ("internet", "internet"), "heat/hot water": ("heat and hot water", "calefacción y agua caliente"),
           "parking": ("parking", "estacionamiento")}


def profit_txt(v):
    if v is None:
        return "?"
    return L(f"about {money(v)}/mo profit", f"unos {money(v)}/mes de ganancia") if v >= 0 else L(f"about {money(-v)}/mo loss", f"unos {money(-v)}/mes de pérdida")


@timed('prop_details')
def property_details(r, f, sc, o, rent, rent_src, own):
    A = r.get("assumptions") or {}
    fi = A.get("financing", {})
    # --- the home
    st.markdown(f"#### {L('🏡 The home', '🏡 La casa')}")
    inc = [P(INC_LBL.get(x, (x, x))) for x in (f.get("hoa_includes") or [])]
    lines = [L(f"**Price: {money(f.get('price'))}**", f"**Precio: {money(f.get('price'))}**") if f.get("price") else L("Price: unknown", "Precio: no se sabe"),
             L("Bedrooms", "Habitaciones") + f": {f.get('beds') or '?'}" + (" · " + L("Bathrooms", "Baños") + f": {f.get('baths')}" if f.get("baths") else ""),
             L("Building fee", "Cuota del edificio") + f": {money(f.get('hoa_monthly')) + L('/mo', '/mes') if f.get('hoa_monthly') else L('unknown', 'no se sabe')}"
             + (L(f" (includes {', '.join(inc)})", f" (incluye {', '.join(inc)})") if inc else "")]
    if f.get("taxes_annual"):
        lines.append(L("Property taxes", "Impuestos") + f": {money(f.get('taxes_annual'))}" + L("/year", "/año"))
    srcs = sorted({("you" if v == "user input" else (v.split("/")[2] if str(v).startswith("http") else v)) for v in (r.get("fact_sources") or {}).values()} - {"parsed from listing description"})
    lines.append(L("Where these came from: ", "De dónde salen: ") + ", ".join(L("what you typed", "lo que usted escribió") if s == "you" else s for s in srcs))
    md("\n".join(f"- {x}" for x in lines))

    # --- monthly costs
    if o:
        st.markdown(f"#### {L('💵 Your monthly cost if you live there', '💵 Su costo mensual si vive allí')}")
        c = o["costs"]
        fha = not ("co-op" in own and (r.get("fha") or {}).get("eligible") is False)
        mi_lbl = L("FHA insurance fee (required with a small down payment)", "Seguro FHA (obligatorio con poco pago inicial)") if fha else \
            L("Mortgage insurance (down payment under 20%)", "Seguro hipotecario (pago inicial menor al 20%)")
        rows = []
        for k in ["principal_interest", "mortgage_insurance", "hoa_or_maintenance", "property_tax", "insurance", "utilities", "repairs_reserve"]:
            v = c.get(k) or 0
            if k == "property_tax" and not v and "taxes" in (f.get("hoa_includes") or []):
                rows.append(f"- {P(COST_LBL[k])}: {L('included in building fee', 'incluido en la cuota')}")
            elif k == "utilities" and not v and "utilities" in (f.get("hoa_includes") or []):
                rows.append(f"- {P(COST_LBL[k])}: {L('included in building fee', 'incluido en la cuota')}")
            elif v:
                rows.append(f"- {mi_lbl if k == 'mortgage_insurance' else P(COST_LBL[k])}: {money(v)}")
        rows.append(f"- **{L('Total', 'Total')}: {money(o['total_cost'])}{L('/mo', '/mes')}**")
        md("\n".join(rows))
        ln = o["loan"]
        md(L(f"Cash to close: {money(ln['cash_to_close_est'])} = {money(ln['down_payment'])} down payment + about {money(ln['closing_costs_est'])} in closing costs. "
             f"Loan {money(ln['loan_amount'])} at {ln['rate_pct']:.2f}% for {fi.get('term_years', 30)} years.",
             f"Dinero para cerrar: {money(ln['cash_to_close_est'])} = {money(ln['down_payment'])} de pago inicial + unos {money(ln['closing_costs_est'])} de gastos de cierre. "
             f"Préstamo de {money(ln['loan_amount'])} al {ln['rate_pct']:.2f}% por {fi.get('term_years', 30)} años."))
        d = o.get("front_end_dti")
        if d is not None:
            md(L(f"Housing would take {d:.0%} of the income you entered. Lenders usually want this under about 31% to 43%.",
                 f"La vivienda se llevaría el {d:.0%} del ingreso que puso. Los prestamistas suelen querer menos de 31% a 43%."))
        else:
            st.caption(L("Add your income in ⚙️ My settings to see if a lender would likely approve the payment.",
                         "Agregue su ingreso en ⚙️ Mis ajustes para ver si un prestamista aprobaría el pago."))

    # --- what the lender counts
    st.markdown(f"#### {L('🏦 What the lender counts', '🏦 Lo que cuenta el banco')}")
    lines = [L("Roommate rent: lenders don't count it when you apply (it still lowers what you pay each month).",
               "Renta de compañeros: los bancos no la cuentan al aplicar (aun así baja lo que paga cada mes)."),
             L("A 2-4 family you live in: 75% of the other unit's fair rent (the appraiser's number, or the lease if lower) can count as your income.",
               "Una casa de 2-4 familias donde usted vive: el 75% de la renta justa de la otra unidad (la del tasador, o la del contrato si es menor) puede contar como su ingreso."),
             L("3-4 family: the rents of all units, minus 25%, must cover the full monthly payment, and you need 3 months of payments saved after closing.",
               "3-4 familias: las rentas de todas las unidades, menos 25%, deben cubrir el pago mensual completo, y necesita 3 meses de pagos ahorrados después del cierre.")]
    md("\n".join(f"- {x}" for x in lines))
    st.caption(L("Source: HUD Handbook 4000.1, section II.A.4.c (rental income), as updated by Mortgagee Letter 2023-17: ",
                 "Fuente: Manual HUD 4000.1, sección II.A.4.c (ingreso por alquiler), actualizado por la Carta Hipotecaria 2023-17: ")
               + "[hud.gov](https://www.hud.gov/sites/dfiles/OCHCO/documents/2023-17hsgml.pdf). " + L("Ask your lender; rules change.", "Pregunte a su prestamista; las reglas cambian."))

    # --- loan type
    fh = r.get("fha") or {}
    st.markdown(f"#### {L('🔑 Your loan', '🔑 Su préstamo')}")
    if fh.get("eligible") is False:
        md(L(f"FHA loans (the low down payment kind) almost never work for co-ops. This assumes a regular co-op loan with {fi.get('owner_conv_down_pct', .1):.0%} down. The co-op board must also approve you.",
             f"Los préstamos FHA (los de poco pago inicial) casi nunca sirven para co-ops. Esto asume un préstamo normal de co-op con {fi.get('owner_conv_down_pct', .1):.0%} inicial. La junta de la co-op también tiene que dar su aprobación."))
    elif "condo" in own:
        found = L("is on", "está en") if fh.get("eligible") else L("was not found on", "no apareció en")
        md(L(f"This assumes an FHA loan with {fi.get('fha_down_pct', .035):.1%} down. For FHA, the building must be on HUD's approved condo list. This building {found} the list we checked.",
             f"Esto asume un préstamo FHA con {fi.get('fha_down_pct', .035):.1%} inicial. Para FHA, el edificio debe estar en la lista de condos aprobados por HUD. Este edificio {found} la lista que revisamos."))
    else:
        md(L(f"This assumes an FHA loan with {fi.get('fha_down_pct', .035):.1%} down (the usual first-time buyer loan).",
             f"Esto asume un préstamo FHA con {fi.get('fha_down_pct', .035):.1%} inicial (el préstamo usual para primeros compradores)."))

    # --- roommates
    if o and o.get("rooms_rented"):
        st.markdown(f"#### {L('👭 Roommates', '👭 Compañeros de cuarto')}")
        ro = r.get("rooms") or {}
        basis = L(f"typical room rent nearby, from {ro.get('n')} Craigslist posts", f"renta típica de un cuarto cerca, de {ro.get('n')} anuncios de Craigslist") if ro.get("ok") \
            else L("an estimate based on the rent for the whole home", "un estimado según la renta de toda la casa")
        md(L(f"Renting {o['rooms_rented']} room{'s' if o['rooms_rented'] != 1 else ''} at about {money(o['room_rent_each'])} each ({basis}) brings in {money(o['income']['roommate_rent'])}/mo, so your share is {money(o['own_net_housing_cost'])}/mo.",
             f"Alquilar {o['rooms_rented']} cuarto{'s' if o['rooms_rented'] != 1 else ''} a unos {money(o['room_rent_each'])} cada uno ({basis}) trae {money(o['income']['roommate_rent'])}/mes, así que su parte es {money(o['own_net_housing_cost'])}/mes."))
        st.caption(L("Co-op boards often limit roommates. Check the building rules first." if "co-op" in own else "Check that the building rules allow roommates.",
                     "Las juntas de co-op a menudo limitan compañeros. Revise las reglas primero." if "co-op" in own else "Confirme que las reglas del edificio permitan compañeros."))

    # --- building rules
    ic, bp = r.get("coop_income_check"), r.get("building_policy") or {}
    if ic or bp:
        st.markdown(f"#### {L('📋 Building rules', '📋 Reglas del edificio')}")
        if ic:
            md(L(f"The board wants your yearly income to be {ic['multiple']:g} times the housing cost: about {money(ic['required_income_maintenance_only'])} for the building fee alone, "
                 f"or {money(ic['required_income_with_mortgage'])} counting the mortgage too." + (f" You entered {money(ic['buyer_income'])}." if ic.get("buyer_income") else ""),
                 f"La junta quiere que su ingreso anual sea {ic['multiple']:g} veces el costo de vivienda: unos {money(ic['required_income_maintenance_only'])} solo por la cuota, "
                 f"o {money(ic['required_income_with_mortgage'])} contando la hipoteca." + (f" Usted puso {money(ic['buyer_income'])}." if ic.get("buyer_income") else "")))
        note = bp.get("es" if ES() else "en")
        if note and bp.get("source") != "user input":
            md(S.plain(note))

    # --- rent estimate
    rc = r.get("rent_compare") or {}
    st.markdown(f"#### {L('📊 Rent estimate', '📊 Estimado de renta')}")
    src_name = {"rentcast": "RentCast", "free": L("nearby listings", "anuncios cercanos"), "hud": L("HUD fair rent for this ZIP code", "renta justa de HUD para este código postal")}.get(rent_src, "?")
    md(L(f"We used **{money(rent)}/mo** ({src_name}).", f"Usamos **{money(rent)}/mes** ({src_name}).") if rent else L("No rent estimate found.", "No se encontró estimado de renta."))
    lines = []
    if rc.get("free_ok"):
        lines.append(L(f"Nearby listings (free sources): {money(rc['free_median'])}/mo, from {rc['free_n']} listings",
                       f"Anuncios cercanos (fuentes gratuitas): {money(rc['free_median'])}/mes, de {rc['free_n']} anuncios"))
    if rc.get("rentcast_ok"):
        rng = L(f", range {money(rc.get('rentcast_low'))} to {money(rc.get('rentcast_high'))}", f", rango {money(rc.get('rentcast_low'))} a {money(rc.get('rentcast_high'))}") if rc.get("rentcast_low") else ""
        lines.append(L(f"RentCast: {money(rc['rentcast_rent'])}/mo, from {rc['rentcast_n']} rentals{rng}", f"RentCast: {money(rc['rentcast_rent'])}/mes, de {rc['rentcast_n']} alquileres{rng}"))
    else:
        why = {"quota": L("monthly limit reached", "límite mensual alcanzado"), "not_found": L("no estimate for this address", "sin estimado para esta dirección"),
               "no_key": L("not set up", "no configurado"), None: L("not used", "no usado"),
               "error:401": L("price lookups are off right now", "búsquedas de precio apagadas por ahora"),
               "budget": L("lookup limit for this check reached", "límite de consultas para esta revisión alcanzado")}.get(rc.get("rentcast_status"), L("not available", "no disponible"))
        lines.append(f"RentCast: {why}")
    md("\n".join(f"- {x}" for x in lines))
    g = S.rent_gap_line(r)
    if g:
        st.caption("⚠️ " + P(g).replace("$", "\\$"))
    comps = [c for c in (r.get("ltr") or {}).get("comps", [])][:5]
    rcc = ((r.get("rentcast") or {}).get("avm_comps") or [])[:5]
    for title, rows in ((L("Nearby listings", "Anuncios cercanos"), comps), (L("RentCast examples", "Ejemplos de RentCast"), rcc)):
        if rows:
            items = []
            for c in rows:
                bd = f"{int(c['beds'])} {L('bd', 'hab')}" if c.get("beds") is not None else ""
                url = c.get("url") if str(c.get("url", "")).startswith("http") else None
                name = H.escape(S.listing_name(c))[:48]
                items.append(f"<li>{money(c.get('price'))} · {bd} · {S.miles(c.get('dist_km'))} · " + (f"<a href='{H.escape(url)}' target='_blank'>{name}</a>" if url else name) + "</li>")
            html(f"<div class='bz-small'><b>{title}</b><ul>{''.join(items)}</ul></div>")

    # --- other ways
    st.markdown(f"#### {L('✨ Other ways to use this home', '✨ Otras formas de usar esta casa')}")
    inv, mtr, strs = sc.get("investment_ltr"), sc.get("mtr"), sc.get("str")
    lines = []
    if inv:
        lines.append(L(f"Rent it all to one tenant (investment loan, {fi.get('investment_down_pct', .25):.0%} down, {money(inv['loan']['cash_to_close_est'])} to close): {profit_txt(inv['net_monthly'])}",
                       f"Alquilarla completa a un inquilino (préstamo de inversión, {fi.get('investment_down_pct', .25):.0%} inicial, {money(inv['loan']['cash_to_close_est'])} para cerrar): {profit_txt(inv['net_monthly'])}"))
    if mtr:
        m = A.get("mtr", {})
        lines.append(L(f"Rent it furnished for 30+ days at a time (same loan): {profit_txt(mtr['net_monthly'])}. We estimate {money(mtr['mtr_rate'])}/mo from nearby furnished monthly listings "
                       f"(at most {m.get('max_premium_over_ltr', 1.5):g} times normal rent), rented {m.get('occupancy', .8):.0%} of the time.",
                       f"Alquilarla amueblada por 30+ días (mismo préstamo): {profit_txt(mtr['net_monthly'])}. Calculamos {money(mtr['mtr_rate'])}/mes con anuncios amueblados mensuales cercanos "
                       f"(máximo {m.get('max_premium_over_ltr', 1.5):g} veces la renta normal), alquilada el {m.get('occupancy', .8):.0%} del tiempo."))
    if strs:
        lines.append(L("Airbnb (under 30 nights): not allowed here, so we didn't count it.", "Airbnb (menos de 30 noches): no se permite aquí, así que no lo contamos.") if not strs.get("legal")
                     else L(f"Short-term rental with the town's limits: {profit_txt(strs['net_monthly'])}", f"Alquiler corto con los límites del pueblo: {profit_txt(strs['net_monthly'])}"))
    if lines:
        md("\n".join(f"- {x}" for x in lines))
        if "co-op" in own:
            st.caption(L("Most co-ops don't allow buying to rent out. Check the house rules.", "La mayoría de las co-ops no permiten comprar para alquilar. Revise las reglas."))
    else:
        st.caption(L("Add the price to see these.", "Agregue el precio para ver esto."))

    # --- airbnb rules
    sr = r.get("str_rules") or {}
    st.markdown(f"#### {L('🏙️ Airbnb rules in this town', '🏙️ Reglas de Airbnb en este pueblo')}")
    md(S.plain(sr.get("summary_es" if ES() else "summary_en", "")))
    links = []
    for x in sr.get("sources", []):
        mm = re.search(r"https?://\S+", x)
        if mm:
            links.append(f"[{mm.group(0).split('/')[2]}]({mm.group(0).rstrip(')')})")
    if links or sr.get("last_verified"):
        st.caption(L("Source: ", "Fuente: ") + ", ".join(links) + (L(f" (checked {sr.get('last_verified')})", f" (revisado {sr.get('last_verified')})") if sr.get("last_verified") else ""))

    # --- things to check
    w = S.plain_warnings(r)
    if w:
        st.markdown(f"#### {L('🔍 Things to double-check', '🔍 Cosas para confirmar')}")
        md("\n".join(f"- {P(x)}" for x in w))

    glossary()

    # --- verdict rules + assumptions
    st.markdown(f"#### {L('🧮 How we got these numbers', '🧮 Cómo calculamos esto')}")
    rt = r.get("rates") or {}
    oc = A.get("ownership_costs", {})
    wk = re.search(r"week of (\d{4}-\d{2}-\d{2})", rt.get("source", ""))
    items = [L(f"Interest rate {rt.get('base', 0):.2f}%: the U.S. weekly average from Freddie Mac" + (f" (week of {wk.group(1)})" if wk else "") + f". Investment loans cost {fi.get('investment_rate_adjust', .75):.2f}% more.",
               f"Tasa de interés {rt.get('base', 0):.2f}%: el promedio semanal de EE.UU. de Freddie Mac" + (f" (semana del {wk.group(1)})" if wk else "") + f". Los préstamos de inversión cuestan {fi.get('investment_rate_adjust', .75):.2f}% más."),
             L(f"Down payment: {fi.get('fha_down_pct', .035):.1%} for FHA, {fi.get('owner_conv_down_pct', .1):.0%} for a co-op loan, {fi.get('investment_down_pct', .25):.0%} for an investment loan. Closing costs {fi.get('closing_cost_pct', .03):.0%} of the price.",
               f"Pago inicial: {fi.get('fha_down_pct', .035):.1%} con FHA, {fi.get('owner_conv_down_pct', .1):.0%} con préstamo de co-op, {fi.get('investment_down_pct', .25):.0%} con préstamo de inversión. Gastos de cierre {fi.get('closing_cost_pct', .03):.0%} del precio."),
             L(f"FHA insurance: {fi.get('fha_upfront_mip_pct', 0):.2%} added to the loan plus {fi.get('fha_annual_mip_pct', 0):.2%} a year. Home insurance {money(oc.get('ho6_insurance_monthly'))}/mo. Repairs savings {oc.get('maintenance_reserve_pct_of_price', 0):.1%} of the price a year.",
               f"Seguro FHA: {fi.get('fha_upfront_mip_pct', 0):.2%} sumado al préstamo más {fi.get('fha_annual_mip_pct', 0):.2%} al año. Seguro de vivienda {money(oc.get('ho6_insurance_monthly'))}/mes. Ahorro para reparaciones {oc.get('maintenance_reserve_pct_of_price', 0):.1%} del precio al año."),
             L("Verdict: Skip if the income you entered is below the board rule or housing would take over 45% of it, or if even with roommates it costs more than the home's rent. "
               "Good deal if living there costs no more than that rent. Otherwise Maybe.",
               "Veredicto: Mejor no si el ingreso que puso no alcanza la regla de la junta o la vivienda se lleva más del 45%, o si aun con compañeros cuesta más que la renta de la casa. "
               "Buen negocio si vivir allí cuesta lo mismo o menos que esa renta. Si no, Tal vez.")]
    md("\n".join(f"- {x}" for x in items))
    ok_src = sorted({_src_name(s["source"]) for s in r.get("sources_status", []) if s.get("ok")})
    bad_src = sorted({_src_name(s["source"]) for s in r.get("sources_status", []) if not s.get("ok")} - set(ok_src))
    st.caption(L("Data from: ", "Datos de: ") + ", ".join(ok_src) + ((L(". Could not reach: ", ". No se pudo consultar: ") + ", ".join(bad_src)) if bad_src else "") + ".")
    lg_, cv_ = ("es" if ES() else "en"), st.session_state.get("prop_cv")          # the file is made only when tapped
    xn = (f"BellaZu_Reporte_Casa_{_fslug(r['address'])}_{str(r.get('generated') or '')[:10]}.xlsx" if lg_ == "es"
          else f"BellaZu_Property_Report_{_fslug(r['address'])}_{str(r.get('generated') or '')[:10]}.xlsx")
    st.download_button(L("⬇️ Spreadsheet (Excel)", "⬇️ Hoja de cálculo (Excel)"), lambda r=r, cv_=cv_, lg_=lg_: _xlsx_or_note(lambda: _prop_xlsx(r, cv_, lg_)), xn,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dlx_prop", width="stretch", on_click="ignore")
    st.caption(L("Estimates from public data, not financial, legal or lending advice. Confirm with your lender, agent and the town.",
                 "Estimados con datos públicos; no es asesoría financiera, legal ni hipotecaria. Confirme con su prestamista, agente y el municipio."))


SRC_NAMES = {"census": ("U.S. Census", "Censo de EE.UU."), "fred": ("Freddie Mac rates", "tasas de Freddie Mac"), "geocode": ("map lookup", "búsqueda en el mapa"),
             "insideairbnb": ("Inside Airbnb", "Inside Airbnb"), "listing_page": ("listing page", "página del anuncio"), "hud": ("HUD", "HUD"),
             "craigslist": ("Craigslist", "Craigslist"), "rent.com": ("Rent.com", "Rent.com"), "realtor.com": ("realtor.com", "realtor.com"), "redfin": ("Redfin", "Redfin"), "rentcast": ("RentCast", "RentCast"),
             "zillow": ("Zillow", "Zillow"), "nominatim": ("map lookup", "búsqueda en el mapa")}


def _src_name(raw):
    k = re.split(r"[:\s/]", str(raw).strip().lower(), maxsplit=1)[0]
    return P(SRC_NAMES[k]) if k in SRC_NAMES else str(raw).split(":")[0]


GLOSSARY = [
    (("Down payment", "Pago inicial (enganche)"), ("The part of the price you pay yourself. The bank lends you the rest.", "La parte del precio que usted paga. El banco le presta el resto.")),
    (("HOA / building fee", "HOA / cuota del edificio"), ("A monthly fee for the building: cleaning, repairs, doorman, and sometimes taxes and utilities.", "Una cuota mensual del edificio: limpieza, arreglos, portero y a veces impuestos y servicios.")),
    (("Co-op", "Co-op (cooperativa)"), ("You buy shares in the building instead of the apartment itself. A board must approve you and often limits renting out.", "Usted compra acciones del edificio en vez del apartamento. Una junta debe aprobarle y a menudo limita alquilar.")),
    (("FHA loan", "Préstamo FHA"), ("A government-backed loan for first-time buyers. You can put down as little as 3.5%, plus a small insurance fee.", "Un préstamo respaldado por el gobierno para primeros compradores. Puede dar desde 3.5% inicial, más un pequeño seguro.")),
    (("Closing costs", "Gastos de cierre"), ("Fees you pay on closing day: lawyer, bank, title and inspection. Often 2% to 5% of the price.", "Cargos que paga el día del cierre: abogado, banco, título e inspección. Suelen ser 2% a 5% del precio.")),
    (("30+ day rental", "Alquiler de 30+ días"), ("Renting a furnished home for a month or more, like to traveling nurses. It's allowed in many towns that ban Airbnb.", "Alquilar una casa amueblada por un mes o más, por ejemplo a enfermeras viajeras. Se permite en muchos pueblos que prohíben Airbnb.")),
    (("Pre-qualify", "Precalificar"), ("A quick check with a lender that tells you how much you could borrow. It's free and doesn't commit you.", "Una revisión rápida con un prestamista que le dice cuánto le podrían prestar. Es gratis y no le compromete.")),
]


def glossary():
    st.markdown(f"#### {L('📖 Words to know', '📖 Palabras clave')}")
    md("\n".join(f"- **{P(w)}:** {P(d)}" for w, d in GLOSSARY))


@timed('how')
def how_it_works():
    steps = [L("Type an address", "Escriba una dirección"), L("We check the numbers", "Revisamos los números"),
             L("You get a plain answer", "Recibe una respuesta clara")]
    html("<div class='bz-steps'>" + "".join(f"<div class='s'><span class='n'>0{i}</span>{H.escape(t)}</div>" for i, t in enumerate(steps, 1)) + "</div>")


def example():
    """Optional example home from the BELLAZU_EXAMPLE secret (JSON with address + details, or a plain address). Never hard-coded."""
    raw = secret("BELLAZU_EXAMPLE")
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) and d.get("address") else None
    except ValueError:
        return {"address": raw}


# ------------------------------------------------------------------ taps instead of typing: choices
UI_TYPES = {"single-family": ("House", "Casa"), "2-family": ("2-family", "2 familias"), "3-4-family": ("3-4 family", "3-4 familias"),
            "condo": ("Condo", "Condo"), "co-op": ("Co-op", "Co-op"), "townhouse": ("Townhouse", "Townhouse")}
ENGINE_TYPE = {"2-family": "multi-family", "3-4-family": "multi-family"}
UI_INC = {"taxes": ("taxes", "impuestos"), "heat": ("heat", "calefacción"), "water": ("water", "agua"), "electric": ("electric", "luz"),
          "gas": ("gas", "gas"), "internet": ("internet", "internet"), "parking": ("parking", "estacionamiento")}
BEDS = [0, 1, 2, 3, 4]
BATHS = [1.0, 1.5, 2.0, 2.5, 3.0]
BOARD = ["none", 3.0, 4.0, "other"]
INCOME_PICKS = ["skip", 50_000, 75_000, 100_000, 125_000, 150_000]
DOWN_PICKS = ["usual", 5.0, 10.0, 20.0]


def beds_fmt(k):
    return L("Studio", "Estudio") if k == 0 else ("4+" if k == 4 else str(k))


def baths_fmt(k):
    return "3+" if k >= 3 else f"{k:g}"


def board_fmt(k):
    if k == "none":
        return L("None / not sure", "Ninguna / no sé")
    if k == "other":
        return L("Other", "Otra")
    return f"{float(k):g}:1"


def includes_engine(sel):
    """UI 'fee includes' pills -> the engine's list. The math counts utilities as included only when electric AND gas are."""
    sel = set(sel or [])
    out = [x for x in ("taxes", "internet", "parking") if x in sel]
    if {"electric", "gas"} <= sel:
        out.append("utilities")
    if sel & {"heat", "water"}:
        out.append("heat/hot water")
    return out


def includes_ui(eng):
    eng = [x.lower() for x in (eng or [])]
    out = [x for x in ("taxes", "internet", "parking") if x in eng]
    if "utilities" in eng:
        out += ["electric", "gas"]
    if "heat/hot water" in eng:
        out += ["heat", "water"]
    return out



# ------------------------------------------------------------------ My loan (the buyer's pre-approval) + HOA labels
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def market_rate():
    """Freddie Mac PMMS 30-year fixed average (via FRED), cached 6 h. {"rate_pct", "date", "source"}."""
    from bellazu.sources import fred as _fred
    try:
        r = _fred.mortgage30()
    except Exception:
        r = None
    return r or {"rate_pct": 7.0, "date": None, "source": "fallback 7.0% (rate source unreachable)"}


def loan_prof():
    return ML.prof(((sv().get("loan") or {}).get("p")))


def loan_rate():
    return ML.rate_of(loan_prof(), market_rate()["rate_pct"])


def rate_lbl():
    p = loan_prof()
    rk, sk = ML.rate_keys(p["kind"])
    if p.get(rk):
        if p.get(sk) == "lender":
            return L(f"{loan_rate():.2f}% from your lender", f"{loan_rate():.2f}% de su banco")
        return L(f"{loan_rate():.2f}% (your rate)", f"{loan_rate():.2f}% (su tasa)")
    return L(f"{loan_rate():.2f}% est. rate, confirm with lender", f"{loan_rate():.2f}% tasa est., confírmela con su banco")


def approved_monthly():
    return ML.approved(loan_prof(), market_rate()["rate_pct"])


def loan_kind_lbl(lc=None):
    p = loan_prof()
    lc = lc or {}
    k = lc.get("kind") or p["kind"]
    dp = lc.get("down_pct") if lc.get("down_pct") is not None else (max(p["down_pct"], ML.FHA["down_pct"]) if k == "fha" else p["down_pct"])
    return (L(f"FHA {dp * 100:.1f}% down", f"FHA {dp * 100:.1f}% inicial") if k == "fha" else
            L(f"conventional {dp * 100:.1f}% down", f"convencional {dp * 100:.1f}% inicial")) + f", {p['term']} {L('yr', 'años')}"


def hoa_txt(hi, short=False, es=None):
    """'HOA $365/mo', 'Maintenance $1,555/mo (may include taxes)', 'No HOA (typical for houses)', 'HOA est. ~$525/mo'."""
    if not hi:
        return ""
    es = ES() if es is None else es
    L = (lambda a_, b_: b_) if es else (lambda a_, b_: a_)          # noqa: N806 (this language, or the one asked for)
    st_, fee, mt = hi.get("state"), hi.get("fee"), hi.get("label") == "maintenance"
    tx = L(" (includes taxes)", " (incluye impuestos)") if "taxes" in (hi.get("inc") or []) else L(" (may include taxes)", " (puede incluir impuestos)")
    if st_ == "real":
        ex_ = "" if not hi.get("exact") else L(" · confirmed", " · confirmada")
        return (L(f"Maintenance {money(fee)}/mo", f"Mantenimiento {money(fee)}/mes") + ex_ + ("" if short else tx)) if mt else L(f"HOA {money(fee)}/mo", f"HOA {money(fee)}/mes") + ex_
    if st_ == "est":
        return (L(f"Maintenance est. ~{money(fee)}/mo", f"Mantenimiento est. ~{money(fee)}/mes") + ("" if short else tx)) if mt else \
            L(f"HOA est. ~{money(fee)}/mo", f"HOA est. ~{money(fee)}/mes")
    if st_ == "none":
        return L("No HOA (listing says none)", "Sin HOA (según el anuncio)") if hi.get("src") == "listing says no association" else \
            L("No HOA (typical for houses)", "Sin HOA (normal en casas)")
    return L("HOA unknown", "HOA desconocida")


def hoa_extra_note(hi):
    """Extra confirmed costs on a listing: a capital assessment inside the fee and a one-time move-in board charge (or '')."""
    hi = hi or {}
    bits_en, bits_es = [], []
    if hi.get("capital_assessment"):
        bits_en.append(f"the fee includes a {money2(hi['capital_assessment'])}/mo capital assessment (building project)")
        bits_es.append(f"la cuota incluye una asignación de capital de {money2(hi['capital_assessment'])}/mes (proyecto del edificio)")
    if hi.get("move_in_fee"):
        pl = "+" if hi.get("move_in_plus") else ""
        bits_en.append(f"plus a one-time board charge at move-in of {money(hi['move_in_fee'])}{pl} (not in the monthly)")
        bits_es.append(f"más un cargo único de la junta al mudarse de {money(hi['move_in_fee'])}{pl} (no está en el pago mensual)")
    if not bits_en:
        return ""
    return L("Confirmed by the agent: ", "Confirmado por el agente: ") + L("; ".join(bits_en) + ".", "; ".join(bits_es) + ".")


def money2(v):
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return ""


def hoa_src_txt(hi):
    s_ = (hi or {}).get("src") or ""
    if (hi or {}).get("state") == "est":
        w = hi.get("where")
        where = L("nearby towns", "pueblos cercanos") if w == "area" else w
        return L(f"estimate: median of {hi.get('n')} similar homes with a known fee ({where}); ask the agent for the real number",
                 f"estimado: mediana de {hi.get('n')} viviendas parecidas con cuota conocida ({where}); pida el número real al agente")
    if s_.startswith("listing description"):
        ph = re.sub(r"\s+", " ", re.sub(r"[()\[\]]", " ", s_[len("listing description"):])).strip().replace("“ ", "“").replace(" ”", "”")
        return L("from the listing description ", "de la descripción del anuncio ") + ph
    return {"listing: HOA fee field": L("from the listing (HOA fee)", "del anuncio (cuota HOA)"),
            "listing: HOA section (monthly total)": L("from the listing's HOA section", "de la sección HOA del anuncio"),
            "listing: HOA section": L("from the listing's HOA section", "de la sección HOA del anuncio"),
            "listing: maintenance": L("from the listing (maintenance)", "del anuncio (mantenimiento)"),
            "listing: realtor.com payment estimate": L("from realtor.com's payment estimate", "del estimado de pago de realtor.com"),
            "RentCast sale listing": L("from RentCast's copy of the listing", "de la copia del anuncio en RentCast"),
            "typical for houses": L("houses and 2-4 family homes usually have no HOA", "las casas y de 2 a 4 familias normalmente no tienen HOA"),
            "listing says no association": L("the listing says there is no association", "el anuncio dice que no hay asociación"),
            "confirmed by the listing agent (exact)": L("confirmed by the listing agent (exact)", "confirmada por el agente del anuncio (exacta)"),
            "user input": L("you entered it", "usted lo ingresó")}.get(s_, s_)


TAG_TXT = {"ok": (("✓ Within your approval", "✓ Dentro de su aprobación"), "g"),
           "monthly": (("⚠ Price OK, monthly above approval", "⚠ Precio OK, pago mensual sobre lo aprobado"), "y"),
           "over": (("✕ Over your {max} approval", "✕ Sobre su aprobación de {max}"), "r")}


def tag_txt(tg):
    if not tg:
        return "", ""
    (en, es), c = TAG_TXT[tg]
    mx = kmoney(loan_prof()["max_price"])
    return L(en, es).replace("{max}", mx), c


FHA_FLAG = {"condo": ("🚫 Not FHA-approved — loan may not work", "🚫 Sin aprobación FHA — el préstamo puede no funcionar"),
            "coop": ("🚫 Co-op: no FHA — needs a co-op loan, 10%+ down", "🚫 Co-op: sin FHA — necesita préstamo de co-op, 10%+ inicial"),
            "limit": ("🚫 Above the FHA limit — needs a normal loan", "🚫 Sobre el límite FHA — necesita préstamo normal")}


def FHA_LONG(ff):
    return {"condo": L("This building isn't on HUD's FHA-approved condo list (or its approval lapsed), so your FHA loan may not work here. Ask your lender about a "
                       "single-unit approval; otherwise you'd need a normal loan, often 10% down. The numbers above still use your FHA terms.",
                       "Este edificio no está en la lista de condos aprobados por FHA de HUD (o su aprobación venció), así que su préstamo FHA puede no funcionar aquí. "
                       "Pregunte a su banco por una aprobación de unidad individual; si no, necesitaría un préstamo normal, a menudo con 10% inicial. Los números de arriba usan sus términos FHA."),
            "coop": L("FHA doesn't lend on co-ops, so the numbers above use a co-op loan with 10% down (some boards ask 20% or more) and PMI (est.). The board also has to approve you.",
                      "FHA no presta para co-ops, así que los números de arriba usan un préstamo de co-op con 10% inicial (algunas juntas piden 20% o más) y PMI (est.). La junta también tiene que aprobarla."),
            "limit": L("The price is above the county FHA limit, so the numbers above use a normal loan.", "El precio está sobre el límite FHA del condado, así que los números usan un préstamo normal.")}.get(ff, "")


COOP_NOTE = ("ⓘ Co-op: needs a lender that does co-op loans · 10% down (est.)", "ⓘ Co-op: necesita un banco que haga préstamos de co-op · 10% inicial (est.)")
COOP_LONG = ("Co-op: priced with a co-op loan at 10% down (some boards ask 20% or more) and PMI (est.). Not every lender does co-op loans: ask yours. The board also has to approve you.",
             "Co-op: calculado con un préstamo de co-op con 10% inicial (algunas juntas piden 20% o más) y PMI (est.). No todos los bancos hacen préstamos de co-op: pregunte al suyo. La junta también tiene que aprobarla.")


def fha_flag(fa):
    """With an FHA loan in My loan: 'condo' (building not on HUD's approved list), 'coop', 'limit' or None."""
    if not fa or loan_prof()["kind"] != "fha":
        return None
    return {"condo_no": "condo", "condo_unknown": "condo", "coop": "coop", "over_limit": "limit"}.get(fa.get("code"))


def home_money(h):
    """HOA + real monthly cost with My loan + approval tag for one for-sale listing (no API call). Memoized per session."""
    ss = st.session_state
    p = loan_prof()
    key = json.dumps([str(h.get("id")), h.get("price"), p, market_rate()["rate_pct"]], sort_keys=True, default=str)
    memo = ss.setdefault("_hm", {})
    if key in memo:
        return memo[key]
    d = listings.detail_cached(str(h["id"])) if h.get("id") else None
    hi = listings.hoa_info(h, d)
    price = float(h.get("price") or 0)
    if not price:
        return None
    coop = hi.get("kind") == "coop"
    m = ML.monthly(price, p, market_rate()["rate_pct"], (d or {}).get("taxes_annual") if (d or {}).get("ok") else None, hi.get("fee") or 0,
                   taxes_in_hoa=coop and hi.get("state") in ("real", "est"), min_down_pct=0.10 if coop else None)
    ap = approved_monthly()["total"]
    try:
        ff = fha_flag(fha_for_row(dict(h, type="coop") if coop else h))
    except Exception:
        ff = None
    out = {"hoa": hi, "m": m, "tag": ML.tag(price, m["total"], p, ap), "approved": ap, "fha": ff, "coop": coop}
    if len(memo) > 3000:
        memo.clear()
    memo[key] = out
    return out


def _loan_save():
    """A My loan field changed: keep it with the saved list (this browser + the online copy), newest edit wins."""
    ss = st.session_state
    p = loan_prof()
    kind = ss.get("ml_kind") or p["kind"]
    rk, sk = ML.rate_keys(p["kind"])                 # the rate box edits the loan type that was showing
    r_new = float(ss["ml_rate"]) if ss.get("ml_rate") else None
    r_src = (p.get(sk) if r_new is not None and p.get(rk) and abs(r_new - float(p[rk])) < 1e-9 else ("you" if r_new is not None else None))
    newp = dict(p, v=ML.DEFAULT["v"], kind=kind, max_price=float(ss.get("ml_max") or p["max_price"]), down_pct=float(ss.get("ml_down") or p["down_pct"] * 100) / 100,
                min_down=float(ss.get("ml_min") if ss.get("ml_min") is not None else p["min_down"]),
                term=int(ss.get("ml_term") or p["term"]),
                pmi_pct=float(ss.get("ml_pmi") if ss.get("ml_pmi") is not None else p["pmi_pct"] * 100) / 100,
                closing_pct=float(ss.get("ml_close") if ss.get("ml_close") is not None else p["closing_pct"] * 100) / 100,
                ins_m=float(ss.get("ml_ins") if ss.get("ml_ins") is not None else p["ins_m"]),
                tax_y=float(ss.get("ml_tax") if ss.get("ml_tax") is not None else p["tax_y"]))
    if kind == p["kind"]:                             # switching FHA <-> conventional keeps each type's own rate
        newp[rk], newp[sk] = r_new, r_src
    sv()["loan"] = {"p": newp, "t": saves.now_ms()}
    ss.pop("_hm", None)
    _sv_touch()


def _loan_down():
    """Quick down payment: 5% as in the pre-approval (at least $15K), or the 3.5% FHA minimum."""
    ss = st.session_state
    q = ss.get("ml_dq")
    if q is None:
        return
    ss["ml_down"], ss["ml_min"] = (5.0, 15_000) if q == "letter" else (3.5, 0)
    _loan_save()


def _loan_reset():
    ss = st.session_state
    sv()["loan"] = {"p": dict(ML.DEFAULT), "t": saves.now_ms()}
    for k in ("ml_kind", "ml_max", "ml_down", "ml_min", "ml_rate", "ml_term", "ml_pmi", "ml_close", "ml_ins", "ml_tax", "ml_dq"):
        ss.pop(k, None)
    ss.pop("_hm", None)
    _sv_touch()


def loan_panel():
    """My loan, inside ⚙️ My settings. Values live in the saved list (sv['loan']); widgets are refilled from it on every draw."""
    ss = st.session_state
    p = loan_prof()
    mr = market_rate()
    vals = {"ml_kind": p["kind"], "ml_max": int(p["max_price"]), "ml_down": round(p["down_pct"] * 100, 2), "ml_min": int(p["min_down"]),
            "ml_rate": float(p[ML.rate_keys(p["kind"])[0]] or 0.0), "ml_term": int(p["term"]), "ml_pmi": round(p["pmi_pct"] * 100, 2),
            "ml_close": round(p["closing_pct"] * 100, 2), "ml_ins": int(p["ins_m"]), "ml_tax": int(p["tax_y"])}
    for k, v in vals.items():
        ss[k] = v
    st.markdown(f"**{L('My loan', 'Mi préstamo')}**")
    st.caption(L("From your pre-approval and your lender's quotes. Every monthly number in BellaZu uses it.",
                 "De su pre-aprobación y las cotizaciones de su banco. Todos los números mensuales de BellaZu lo usan."))
    _rt = {k: (float(p[ML.rate_keys(k)[0]]) if p.get(ML.rate_keys(k)[0]) else float(mr["rate_pct"])) for k in ("conv", "fha")}
    st.segmented_control(L("Loan type", "Tipo de préstamo"), ["conv", "fha"], key="ml_kind", required=True, on_change=_loan_save, width="stretch",
                         format_func=lambda k: (L("Conventional", "Convencional") if k == "conv" else "FHA") + f" {_rt[k]:.2f}%")
    st.number_input(L("Approved up to (price, $)", "Aprobada hasta (precio, $)"), 50_000, 3_000_000, step=5_000, key="ml_max", on_change=_loan_save)
    ss["ml_dq"] = "letter" if (abs(p["down_pct"] - 0.05) < 1e-9 and int(p["min_down"]) == 15_000) else ("fhamin" if (abs(p["down_pct"] - 0.035) < 1e-9 and not p["min_down"]) else None)
    st.segmented_control(L("Down payment", "Pago inicial"), ["letter", "fhamin"], key="ml_dq", on_change=_loan_down, width="stretch",
                         format_func=lambda k: L("5% (pre-approval)", "5% (pre-aprobación)") if k == "letter" else L("3.5% (FHA minimum)", "3.5% (mínimo FHA)"))
    c1, c2 = st.columns(2)
    with c1:
        st.number_input(L("Down payment (%)", "Pago inicial (%)"), 3.0, 50.0, step=0.5, key="ml_down", on_change=_loan_save,
                        help=L("FHA needs at least 3.5%.", "FHA necesita al menos 3.5%.") if p["kind"] == "fha" else None)
    with c2:
        st.number_input(L("At least ($)", "Al menos ($)"), 0, 500_000, step=1_000, key="ml_min", on_change=_loan_save)
    st.number_input(L("Interest rate (%)", "Tasa de interés (%)"), 0.0, 15.0, step=0.125, format="%.3f", key="ml_rate", on_change=_loan_save)
    _rk, _sk = ML.rate_keys(p["kind"])
    cap(L(("Your lender's rate. " if p.get(_rk) and p.get(_sk) == "lender" else "")
          + f"Set 0 to use the market average ({mr['rate_pct']:.2f}%, Freddie Mac 30-year fixed, week of {mr.get('date') or '—'}, an estimate).",
          ("La tasa de su banco. " if p.get(_rk) and p.get(_sk) == "lender" else "")
          + f"Ponga 0 para usar el promedio del mercado ({mr['rate_pct']:.2f}%, Freddie Mac a 30 años fijo, semana del {mr.get('date') or '—'}, un estimado)."))
    st.segmented_control(L("Term", "Plazo"), [30, 15], key="ml_term", required=True, on_change=_loan_save, format_func=lambda y: L(f"{y} years", f"{y} años"))
    c3, c4 = st.columns(2)
    with c3:
        st.number_input(L("PMI (%/yr, est.)", "PMI (%/año, est.)"), 0.0, 2.0, step=0.05, key="ml_pmi", on_change=_loan_save, disabled=p["kind"] == "fha")
    with c4:
        st.number_input(L("Closing costs (%, est.)", "Gastos de cierre (%, est.)"), 0.0, 8.0, step=0.25, key="ml_close", on_change=_loan_save)
    c5, c6 = st.columns(2)
    with c5:
        st.number_input(L("Insurance ($/mo)", "Seguro ($/mes)"), 0, 2_000, step=10, key="ml_ins", on_change=_loan_save)
    with c6:
        st.number_input(L("Taxes if unknown ($/yr)", "Impuestos si no se saben ($/año)"), 0, 50_000, step=100, key="ml_tax", on_change=_loan_save)
    ap = approved_monthly()
    fha_ = p["kind"] == "fha"
    ins_en = (f"with the 1.75% upfront MIP, {rate_lbl()}, {p['term']} years, 0.55%/yr MIP" if fha_ else
              f"{rate_lbl()}, {p['term']} years, PMI est. {p['pmi_pct'] * 100:.2f}%/yr")
    ins_es = (f"con el MIP inicial de 1.75%, {rate_lbl()}, {p['term']} años, MIP de 0.55%/año" if fha_ else
              f"{rate_lbl()}, {p['term']} años, PMI est. {p['pmi_pct'] * 100:.2f}%/año")
    cap(L(f"Approved monthly payment: {money(ap['total'])} ({'FHA' if fha_ else 'conventional'} at {kmoney(p['max_price'])}, {money(ap['loan']['down_payment'])} down, "
          f"loan {money(ap['loan']['loan_amount'])}{' ' if fha_ else ', '}{ins_en}, the lender's {money(p['tax_y'])}/yr taxes and {money(p['ins_m'] * 12)}/yr insurance, no HOA). "
          + ("FHA condos must be on HUD's approved list; co-ops can't use FHA." if fha_ else
             "Conventional: condos don't need HUD approval. Co-ops need a lender that does co-op loans (priced at 10% down)."),
          f"Pago mensual aprobado: {money(ap['total'])} ({'FHA' if fha_ else 'convencional'} a {kmoney(p['max_price'])}, {money(ap['loan']['down_payment'])} de inicial, "
          f"préstamo {money(ap['loan']['loan_amount'])}{' ' if fha_ else ', '}{ins_es}, los {money(p['tax_y'])}/año de impuestos y {money(p['ins_m'] * 12)}/año de seguro del banco, sin HOA). "
          + ("Los condos con FHA deben estar en la lista aprobada de HUD; los co-ops no pueden usar FHA." if fha_ else
             "Convencional: los condos no necesitan aprobación de HUD. Los co-ops necesitan un banco que haga préstamos de co-op (calculado con 10% inicial).")))
    st.button(L("Reset to my pre-approval", "Volver a mi pre-aprobación"), key="ml_reset", on_click=_loan_reset, type="tertiary")


# ------------------------------------------------------------------ My settings (remembered in the session)
SET_KEYS = ("set_income", "set_down", "set_rm", "set_rc", "inc_chip")


def settings_defaults():
    ss = st.session_state
    ss.setdefault("set_income", 0)
    ss.setdefault("set_down", "usual")
    ss.setdefault("set_rm", 1)
    ss.setdefault("set_rc", rentcast.available())
    for k in SET_KEYS:          # keep widget values alive even on pages where the popover isn't drawn
        if k in ss:
            ss[k] = ss[k]


_KEEP_SAVED = re.compile(r"^(sv_sort|sv_filt)$")
_KEEP_MAIN = re.compile(r"^(hmode|pk_mode|rank_price|mt_price|mt_size|tchips_.+|hst_.+|hpx_.+|happ_.+|hbd_.+|hkd_.+|hsort_.+|tp_.+|tpo_.+|ts_.+|ro_.+|ub_.+|un_.+|rm_.+|lv_.+|own_.+|cc_.+|g_.+|arv_rehab_.+|arv_sell_.+)$")


def _keep_ui():
    """Streamlit forgets a widget's value on any run that doesn't draw it. The Saved homes list (sort, filter) is kept always; what the user chose on the
    main page (mode, town picks, price/size, feed filters, rent-out choices) is kept while in in Saved homes or in a home opened from there,
    and for the one run after that, which draws those widgets again."""
    ss = st.session_state
    away = ss.get("page") == "saved" or bool(ss.get("sv_chain"))
    pats = [_KEEP_SAVED] + ([_KEEP_MAIN] if (away or ss.pop("_kept_main", False)) else [])
    if away:
        ss._kept_main = True
    for k in list(ss.keys()):
        if isinstance(k, str) and any(p.match(k) for p in pats):
            try:
                ss[k] = ss[k]
            except Exception:
                pass


def _inc_chip():
    v = st.session_state.get("inc_chip")
    if v is not None:
        st.session_state.set_income = 0 if v == "skip" else int(v)


@timed('settings')
def settings_popover():
    with st.popover(L("⚙️ My settings", "⚙️ Mis ajustes"), width="content"):
        st.markdown(f"**{L('Your yearly income (before taxes)', 'Su ingreso anual (antes de impuestos)')}**")
        st.caption(L("Only used to check lender and co-op board rules. Never saved.", "Solo se usa para revisar reglas del banco y de la junta. Nunca se guarda."))
        st.pills(L("Quick pick", "Elegir rápido"), INCOME_PICKS, key="inc_chip", on_change=_inc_chip, label_visibility="collapsed",
                 format_func=lambda k: L("Skip", "Omitir") if k == "skip" else f"${k // 1000:,}K")
        st.number_input(L("Exact amount ($)", "Cantidad exacta ($)"), min_value=0, max_value=5_000_000, step=5000, key="set_income")
        loan_panel()
        st.markdown(f"**{L('Roommates', 'Compañeros de cuarto')}**")
        st.pills(L("Roommates", "Compañeros"), [0, 1, 2], key="set_rm", required=True, label_visibility="collapsed",
                 format_func=lambda k: {0: L("None", "Ninguno"), 1: "1", 2: "2"}[k])
        st.caption(L("Never more than the spare bedrooms.", "Nunca más que los cuartos libres."))
        st.toggle(L("Use RentCast lookups (better numbers)", "Usar consultas de RentCast (mejores números)"), key="set_rc", disabled=not rentcast.available())
        st.caption(rc_usage_line())


# ------------------------------------------------------------------ Check a home: running
def facts_for(addr):
    return st.session_state.setdefault("facts_over", {}).setdefault(addr.strip().lower(), {})


def home_opts(addr):
    ss = st.session_state
    fo = facts_for(addr)
    ov = {"price": fo.get("price"), "hoa_monthly": fo.get("hoa"), "taxes_annual": fo.get("taxes"), "beds": fo.get("beds"), "baths": fo.get("baths"),
          "ownership": ENGINE_TYPE.get(fo.get("type"), fo.get("type")), "hoa_includes": includes_engine(fo.get("inc")) if fo.get("inc") is not None else None}
    b = fo.get("board")
    bp = {"en": "Board income rule entered by the user.", "es": "Regla de ingreso de la junta ingresada por el usuario.",
          "source": "user input", "income_multiple": float(b)} if isinstance(b, (int, float)) and b else None
    aov = {"roommate": {"rooms_rented_out": int(ss.get("set_rm", 1))}}
    fa = fha_for_addr(addr)
    lp = loan_prof()
    eff = dict(lp)
    if lp["kind"] == "fha" and fa and fa.get("code") in ("coop", "over_limit"):   # FHA can't be used at all: a normal loan with My loan's down payment
        eff["kind"] = "conv"                         # (a condo not on HUD's list keeps the FHA numbers, flagged 'Not FHA-approved')
    conv = eff["kind"] == "conv"
    aov["financing"] = {"closing_cost_pct": lp["closing_pct"], "term_years": lp["term"], "pmi_annual_pct_if_lt20": lp["pmi_pct"]}
    aov["ownership_costs"] = {"ho6_insurance_monthly": lp["ins_m"], "property_tax_fallback_annual": lp["tax_y"]}
    g = (ss.get("gallery") or {}).get(addr.strip().lower()) or {}
    return {"overrides": {k: v for k, v in ov.items() if v is not None}, "income_annual": int(ss.get("set_income") or 0) or None,
            "loan_type": "conv" if conv else None, "listing_text": g.get("text") or None,
            "units_total": 3 if fo.get("type") == "3-4-family" else 2,
            "building_policy": bp, "use_rentcast": bool(ss.get("set_rc")) and rentcast.available(), "assumption_overrides": aov,
            "my_loan": {"p": eff, "min_down_pct": fa["down"] if (fa and fa.get("code") == "coop") else None, "rate": market_rate()["rate_pct"]}}


@timed('run_home')
def run_home(addr, where):
    ss = st.session_state
    opts = home_opts(addr)
    key = json.dumps([addr.strip().lower(), opts], sort_keys=True, default=str)
    cache = ss.setdefault("prop_cache", {})
    if key in cache:
        r = cache[key]
    else:
        with where, st.spinner(L("Checking the numbers for you... about 20 to 60 seconds ✨", "Revisando los números por usted... unos 20 a 60 segundos ✨")):
            try:
                with rentcast.budget(ss.get("rc_budget")) as b:
                    r = prop_check(addr.strip(), opts, ss.get("rc_budget"))
                if b is not None:
                    ss.rc_budget = b[0]
            except Exception as e:  # never show a stack trace to the user
                r = {"ok": False, "error": f"{e.__class__.__name__}"}
        if r.get("ok"):
            cache[key] = r
            rec = ss.setdefault("recent", [])
            if addr.strip() in rec:
                rec.remove(addr.strip())
            rec.insert(0, addr.strip())
            del rec[5:]
    ss.prop, ss.prop_key = r, key


def _addr_changed():
    ss = st.session_state
    ss.addr_sugg = []
    q = (ss.get("addr") or "").strip()
    if len(q) < 8:
        return
    try:
        from bellazu.geo import suggest, UNIT_RE
        sug = suggest(q, 4)
    except Exception:
        return
    unit = " ".join(m.group(0).strip(" ,") for m in UNIT_RE.finditer(q))
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    out = []
    for s_ in sug:
        if unit:                      # keep the typed apartment number on the suggestion
            parts = s_.split(", ", 1)
            s_ = f"{parts[0]} {unit}" + (f", {parts[1]}" if len(parts) > 1 else "")
        if norm(s_) != norm(q) and s_ not in out:
            out.append(s_)
    ss.addr_sugg = out[:3]


def _pick(key):
    v = st.session_state.get(key)
    if v:
        st.session_state.addr = v
        st.session_state.addr_sugg = []
    st.session_state[key] = None


def use_example():
    ex = example() or {}
    ss = st.session_state
    ss.addr = ex.get("address", "")
    fo = facts_for(ss.addr)
    for k in ("price", "hoa", "taxes", "beds"):
        if ex.get(k) is not None:
            fo[k] = int(ex[k])
    if ex.get("type") in UI_TYPES or ex.get("type") == "multi-family":
        fo["type"] = {"multi-family": "2-family"}.get(ex["type"], ex["type"])
    if ex.get("includes"):
        fo["inc"] = includes_ui(ex["includes"])
    if ex.get("board_multiple"):
        fo["board"] = float(ex["board_multiple"])
    ss.auto_go = True


# ------------------------------------------------------------------ Check a home: fill a missing fact / fix facts
def _set_fact(addr, k, wkey):
    v = st.session_state.get(wkey)
    if v is not None:
        facts_for(addr)[k] = v


def missing_fact(r):
    f = r.get("facts") or {}
    own = (f.get("ownership") or "").lower()
    if not f.get("price"):
        return "price"
    if not own:
        return "type"
    if f.get("beds") in (None, ""):
        return "beds"
    if own in ("condo", "co-op", "townhouse") and (f.get("hoa_monthly") in (None, "") or
                                                   facts_for(st.session_state.get("prop_addr", r["address"])).get("hoa_src") == "est"):
        return "hoa"
    return None


def ask_missing(r):
    """ONE small friendly prompt for the most important fact we couldn't find."""
    addr = st.session_state.get("prop_addr", r["address"])
    k = missing_fact(r)
    if not k:
        return
    sid = safe_name(addr)[:30]
    msg = {"price": L("We couldn't find the price. Add it and we'll redo the math ✨", "No encontramos el precio. Agréguelo y volvemos a calcular ✨"),
           "type": L("What kind of home is it? Tap one 👇", "¿Qué tipo de vivienda es? Toque una 👇"),
           "beds": L("How many bedrooms? Tap one 👇", "¿Cuántas habitaciones? Toque una 👇"),
           "hoa": (L(f"The listing doesn't show the monthly fee, so we used an estimate (~{money(facts_for(addr).get('hoa'))}/mo, similar homes nearby). Add the real fee for a truer cost ✨",
                     f"El anuncio no muestra la cuota mensual; usamos un estimado (~{money(facts_for(addr).get('hoa'))}/mes, viviendas parecidas cerca). Agregue la cuota real para un costo más exacto ✨")
                   if facts_for(addr).get("hoa_src") == "est" else
                   L("We couldn't find the monthly building fee. Add it for a truer cost ✨", "No encontramos la cuota mensual del edificio. Agréguela para un costo más real ✨"))}[k]
    html(f"<div class='bz-ask'>🔎 {H.escape(msg)}</div>")
    if k == "type":
        st.pills(msg, list(UI_TYPES), key=f"ask_type_{sid}", format_func=lambda x: P(UI_TYPES[x]), label_visibility="collapsed",
                 on_change=_set_fact, args=(addr, "type", f"ask_type_{sid}"))
    elif k == "beds":
        st.pills(msg, BEDS, key=f"ask_beds_{sid}", format_func=beds_fmt, label_visibility="collapsed",
                 on_change=_set_fact, args=(addr, "beds", f"ask_beds_{sid}"))
    else:
        with st.form(f"ask_{k}_{sid}", border=False):
            c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
            if k == "price":
                v = c1.number_input(L("Price ($)", "Precio ($)"), min_value=0, max_value=20_000_000, step=5000, value=None, placeholder="250000")
            else:
                v = c1.number_input(L("Monthly fee ($)", "Cuota mensual ($)"), min_value=0, max_value=50_000, step=25, value=None, placeholder="600")
            ok = c2.form_submit_button(L("Update ✨", "Actualizar ✨"), type="primary", width="stretch")
        if ok and v is not None:
            facts_for(addr)["price" if k == "price" else "hoa"] = int(v)
            if k == "hoa":
                facts_for(addr).update(hoa_src="user", hoa_info=None)
            st.rerun()


def fix_facts(r):
    addr = st.session_state.get("prop_addr", r["address"])
    f = r.get("facts") or {}
    fo = facts_for(addr)
    sid = safe_name(addr)[:30]
    own = (f.get("ownership") or "").lower()
    cur_type = fo.get("type") or {"multi-family": "2-family"}.get(own, own if own in UI_TYPES else None)
    b = fo.get("board")
    with st.popover(L("✏️ Not right? Fix the home facts", "✏️ ¿Algo mal? Corregir datos de la casa"), width="stretch"):
        with st.form(f"fix_{sid}", border=False):
            price = st.number_input(L("Price ($)", "Precio ($)"), min_value=0, max_value=20_000_000, step=5000, value=int(f.get("price") or 0))
            typ = st.pills(L("Type of home", "Tipo de vivienda"), list(UI_TYPES), default=cur_type, format_func=lambda x: P(UI_TYPES[x]))
            beds = st.pills(L("Bedrooms", "Habitaciones"), BEDS, default=min(int(f["beds"]), 4) if f.get("beds") not in (None, "") else None, format_func=beds_fmt)
            bv = f.get("baths")
            baths = st.pills(L("Bathrooms", "Baños"), BATHS, default=min(round(float(bv) * 2) / 2, 3.0) if bv else None, format_func=baths_fmt)
            hoa = st.number_input(L("Monthly building fee / HOA ($, 0 if none)", "Cuota mensual del edificio / HOA ($, 0 si no hay)"), min_value=0, max_value=50_000, step=25,
                                  value=int(f.get("hoa_monthly") or 0))
            inc = st.pills(L("The fee includes", "La cuota incluye"), list(UI_INC), selection_mode="multi", default=fo.get("inc") if fo.get("inc") is not None else includes_ui(f.get("hoa_includes")),
                           format_func=lambda x: P(UI_INC[x]))
            taxes = st.number_input(L("Property taxes per year ($, 0 if unknown)", "Impuestos por año ($, 0 si no sabe)"), min_value=0, max_value=200_000, step=100,
                                    value=int(fo.get("taxes") or f.get("taxes_annual") or 0))
            board = st.pills(L("Co-op/condo board income rule", "Regla de ingreso de la junta"), BOARD, format_func=board_fmt,
                             default=(b if b in BOARD else ("other" if b else "none")))
            other = st.number_input(L("If other: income must be this many times the housing cost", "Si es otra: el ingreso debe ser estas veces el costo"),
                                    min_value=0.0, max_value=10.0, step=0.5, value=float(b) if isinstance(b, float) and b not in BOARD else 0.0)
            ok = st.form_submit_button(L("Redo the math ✨", "Volver a calcular ✨"), type="primary", width="stretch")
        if ok:
            if price:
                fo["price"] = int(price)
            if typ:
                fo["type"] = typ
            if beds is not None:
                fo["beds"] = int(beds)
            if baths is not None:
                fo["baths"] = float(baths)
            if hoa or f.get("hoa_monthly") or fo.get("hoa") is not None:
                if fo.get("hoa") != int(hoa) or fo.get("hoa_src") == "est":
                    fo.update(hoa_src="user", hoa_info=None)
                fo["hoa"] = int(hoa)
            fo["inc"] = list(inc or [])
            if taxes:
                fo["taxes"] = int(taxes)
            fo["board"] = (float(other) if board == "other" and other else (board if isinstance(board, float) else None))
            st.rerun()


def addr_search(term):
    """Live suggestions for the address box (Photon / OpenStreetMap, cached). The typed text is always the last option."""
    t = (term or "").strip()
    if len(t) < 5:
        return []
    try:
        from bellazu.geo import suggest
        sug = suggest(t, 5)
    except Exception:
        sug = []
    return [(f"📍 {s_}", s_) for s_ in sug] + [(L(f"✏️ Use exactly: {t}", f"✏️ Usar tal cual: {t}"), t)]


SB_STYLE = {"searchbox": {"control": {"minHeight": "54px", "borderRadius": "100px", "fontSize": "16px", "paddingLeft": "8px",
                                     "backgroundColor": "#141414", "borderColor": "#3A3A3A", "color": "#FFFFFF"},
                          "input": {"fontSize": "16px", "color": "#FFFFFF"}, "singleValue": {"color": "#FFFFFF", "fontSize": "16px"},
                          "placeholder": {"fontSize": "15px", "color": "#8C8C8C"},
                          "menuList": {"backgroundColor": "#1B1B1B", "maxHeight": "340px"},
                          "option": {"color": "#FFFFFF", "backgroundColor": "#1B1B1B", "highlightColor": "#F4A7BB", "padding": "14px 16px",
                                     "fontSize": "16px", "minHeight": "52px"}},
            "dropdown": {"rotate": True, "width": 26, "height": 26, "fill": "#A9A9A9"},
            "clear": {"width": 22, "height": 22, "icon": "cross", "clearable": "always", "stroke": "#A9A9A9"},
            "wrapper": {"backgroundColor": "transparent"}}


def _go_recent(x):
    st.session_state.go = ("addr", x)


def not_found(r):
    """Friendly, never a dead end: say what happened, offer tappable matches, and show which map services were tried."""
    typed = st.session_state.get("prop_addr", "")
    try:
        from bellazu.geo import suggest
        sug = [x for x in suggest(typed, 4) if x.lower() != typed.lower()]
    except Exception:
        sug = []
    st.info(L(f"Hmm, we couldn't place “{typed}” on the map 💕 " + ("Is it one of these?" if sug else "Check the street number and add the town, like '12 Main St, Fort Lee'."),
              f"Mmm, no pudimos ubicar “{typed}” en el mapa 💕 " + ("¿Es una de estas?" if sug else "Revise el número y agregue el pueblo, por ejemplo '12 Main St, Fort Lee'.")), icon="🌷")
    for i, x in enumerate(sug):
        st.button(f"📍 {x}", key=f"nf_{i}", on_click=_go_recent, args=(x,), width="stretch")
    tried = [s_ for s_ in r.get("sources_status") or [] if str(s_.get("source", "")).startswith("geocode")]
    if tried:
        nm = {"geocode:nominatim": "OpenStreetMap", "geocode:photon": "Photon", "geocode:census": "US Census"}
        seen = {}
        for s_ in tried:
            why = L("no match", "sin resultado") if s_.get("ok") or s_.get("http") == 200 else (f"busy ({s_.get('http')})" if s_.get("http") else L("no answer", "sin respuesta"))
            seen.setdefault(nm.get(s_["source"], s_["source"]), why)
        st.caption(L("Map services tried: ", "Servicios de mapa consultados: ") + ", ".join(f"{k} ({v})" for k, v in seen.items()))


# ------------------------------------------------------------------ ONE search + ONE compare view (home or town)
from bellazu import compare as C                                # noqa: E402
from bellazu import town_snapshot                               # noqa: E402
from bellazu.render import town_html, write_town                # noqa: E402
town_html, write_town = timed("rep:town_html")(town_html), timed("rep:town_xlsx")(write_town)
property_html = timed("rep:prop_html")(property_html)


def _net_timed(f, name):
    """Like timed(), and also lists each slow web fetch inside (source, HTTP status, ms) for ?debug_timing=1."""
    import functools

    @functools.wraps(f)
    def w(*a, **k):
        with tm(name):
            r = f(*a, **k)
        try:
            for x in (r or {}).get("sources_status") or []:
                if (x.get("ms") or 0) >= 150:
                    st.session_state.setdefault("_tm_cur", []).append((f"  net:{x.get('source')}:{x.get('http')}", x["ms"]))
        except Exception:
            pass
        return r
    return w


town_snapshot = _net_timed(town_snapshot, "town_snapshot")


class _NoCache(Exception):
    """Carries a result that must not be kept in the shared cache (a failed lookup)."""
    def __init__(self, r):
        super().__init__("not cached")
        self.r = r


@st.cache_data(ttl=6 * 3600, max_entries=150, show_spinner=False)
def _town_snap_shared(name):
    """Town snapshot shared by every visitor of this server for 6 hours (free public data, never RentCast). Failures aren't kept."""
    r = town_snapshot(name, {"use_rentcast": False})
    if not r.get("ok"):
        raise _NoCache(r)
    return r


def town_snap(name):
    try:
        return _town_snap_shared(name)
    except _NoCache as e:
        return e.r


@st.cache_data(ttl=6 * 3600, max_entries=300, show_spinner=False)
def _prop_shared(addr_key, opts_key, rc_live, _addr, _opts):
    """A home check shared for 6 hours by address + every option that changes the numbers (+ whether RentCast lookups were allowed)."""
    r = analyze_property(_addr, _opts)
    if not r.get("ok"):
        raise _NoCache(r)
    return r


def prop_check(addr, opts, rc_budget):
    rc_live = bool(opts.get("use_rentcast")) and (rc_budget is None or rc_budget > 0)
    try:
        return _prop_shared(addr.strip().lower(), json.dumps(opts, sort_keys=True, default=str), rc_live, addr, opts)
    except _NoCache as e:
        return e.r


from bellazu.sources import hud as _hud_m, insideairbnb as _iab_m, craigslist as _cl_m, rentcom as _rcom_m, redfin as _rf_m   # noqa: E402
if not getattr(_hud_m, "_bz_timed", False):          # finer ?debug_timing=1 detail inside the town/home lookups (module attributes, once per process)
    _hud_m._load = timed("  hud_load")(_hud_m._load)
    _iab_m.load = timed("  iab_load")(_iab_m.load)
    _cl_m.search = timed("  craigslist")(_cl_m.search)
    _rcom_m.search = timed("  rent.com")(_rcom_m.search)
    _rf_m.rentals = timed("  redfin")(_rf_m.rentals)
    C.town_rank = timed("  town_rank")(C.town_rank)
    _hud_m._bz_timed = True
analyze_property = _net_timed(analyze_property, "analyze_property")

MONTHS = [("J", "E"), ("F", "F"), ("M", "M"), ("A", "A"), ("M", "M"), ("J", "J"), ("J", "J"), ("A", "A"), ("S", "S"), ("O", "O"), ("N", "N"), ("D", "D")]


def kmoney(v):
    if v is None:
        return "?"
    v = float(v)
    if abs(v) >= 10000:
        k = v / 1000
        return f"${k:,.0f}K" if abs(k - round(k)) < 0.05 or abs(k) >= 100 else f"${k:.1f}K"
    return f"${round(v):,}"


def drive_line(d):
    """One plain line: '26 min to Midtown · NJ Transit train 11-14 min to Penn Station'."""
    if not d:
        return
    bits = [L(f"🚗 {d['min']} min to Midtown", f"🚗 {d['min']} min a Midtown")]
    tr = d.get("transit")
    if tr:
        bits.append("🚆 " + re.sub(r"\s(about|unos)\s", " ", tr[1] if ES() else tr[0]))
    html(f"<div class='bz-tl'>{H.escape(' · '.join(bits))}</div>")


def drive_badge(d):
    if not d:
        return
    txt = C.drive_text(d, ES())
    how = L("typical, not live", "típico, no en vivo") + (L(" · from this address", " · desde esta dirección") if d.get("source") == "route" else L(" · town average", " · promedio del pueblo"))
    tolls = f"<a href='{d['tolls'][0]}' target='_blank'>{L('tolls', 'peajes')}</a>" if d.get("tolls") else ""
    tr = d.get("transit")
    html(f"<div class='bz-drive'><span>{H.escape(txt)}</span><span class='x'>{how} · {L('Hudson crossings and Midtown have', 'Los cruces del Hudson y Midtown tienen')} {tolls}</span>"
         + (f"<span class='x'>🚆 {H.escape(tr[1] if ES() else tr[0])}</span>" if tr else "") + "</div>")


def skew_note(base, sel):
    if sel.get("rent_out") != "unit":
        return
    u = ((base.get("units") or {}).get(sel.get("unit_beds", 2)) or {}).get("ltr") or {}
    if u.get("skewed"):
        cap(L(f"Most rentals listed here are in new buildings (typical {money(u['high'])}/mo), well above HUD's fair rent ({money(u['low'])}). "
                     f"For an older 2-family unit we use {money(u['typ'])}/mo, halfway between HUD and the cheaper listings. Move the rent slider if you know better.",
                     f"La mayoría de los alquileres aquí son de edificios nuevos (típico {money(u['high'])}/mes), muy por encima de la renta justa de HUD ({money(u['low'])}). "
                     f"Para una unidad en una casa de 2 familias usamos {money(u['typ'])}/mes, entre HUD y los anuncios más baratos. Mueva la barra de renta si sabe más."))


@timed('strip')
def compare_strip(out, first, loan_lbl=None):
    cols = C.labels(out, first)
    cells = ""
    for c in cols:
        earn = c["pay_lbl"][0] == "You earn"
        cells += (f"<div class='bz-col{' star' if c['star'] else ''}'>" + (f"<div class='tag'>⭐ {L('City renters', 'Para la ciudad')}</div>" if c["star"] else "")
                  + f"<div class='h'>{H.escape(P(c['title']))}</div><div class='l'>{H.escape(P(c['pay_lbl']))}</div>"
                  f"<div class='n{' earn' if earn else ''}'>{H.escape(c['pay'])}</div><div class='s'>{H.escape(P(c['sub']))}</div>"
                  f"<div class='b'>{H.escape(P(c['badge']))}</div></div>")
    hd = L(f"What you pay each month, same loan: {loan_lbl}", f"Lo que paga al mes, mismo préstamo: {loan_lbl}") if loan_lbl else \
        L('What you pay each month, same FHA loan', 'Lo que paga al mes, mismo préstamo FHA')
    html(f"<div class='bz-lbl'>{H.escape(hd)}</div><div class='bz-cmp'>{cells}</div>")


@timed('sel')
def sel_for(sid, base):
    """Tap-only choices for the compare view. Returns the selection dict for compare()."""
    ss = st.session_state
    d = C.default_sel(base)
    multi = base["ptype"] == "multi-family"
    pt = "mf" if multi else "sf"          # the choice resets when the home type changes (e.g. after the user says it's a 2-family)
    opts = ["room", "unit", "none"] if multi else ["room", "none"]
    nm = {"room": L("A room", "Un cuarto"), "unit": L("The other unit", "La otra unidad"), "none": L("Nothing", "Nada")}
    st.markdown(f"<div class='bz-lbl'>{L('What would you rent out?', '¿Qué alquilaría?')}</div>", unsafe_allow_html=True)
    ro = st.segmented_control(L("Rent out", "Alquilar"), opts, key=f"ro_{sid}_{pt}", default=d["rent_out"] if d["rent_out"] in opts else "none", required=True,
                              label_visibility="collapsed", width="stretch", format_func=lambda k: nm[k])
    sel = dict(d, rent_out=ro)
    if ro == "unit":
        c1, c2 = st.columns(2)
        with c1:
            sel["unit_beds"] = st.segmented_control(L("Other unit", "Otra unidad"), [1, 2, 3], key=f"ub_{sid}_{pt}", default=d["unit_beds"], required=True,
                                                    format_func=lambda b: f"{b} {L('bd', 'hab')}")
        if base.get("units_total", 2) >= 3:
            with c2:
                sel["units_n"] = st.segmented_control(L("Units you rent", "Unidades que alquila"), [1, 2, 3], key=f"un_{sid}_{pt}", default=d["units_n"], required=True)
    elif ro == "room":
        spare = max(int(base.get("beds") or 2) - 1, 1)
        if spare >= 2:
            sel["rooms"] = st.segmented_control(L("Rooms", "Cuartos"), [1, 2], key=f"rm_{sid}_{pt}", default=1, required=True)
    sel["lvl"] = {k: ss.get(f"lv_{k}_{sid}") or "typ" for k in ("rent", "mtr", "str")}
    sel["own"] = {k: ss.get(f"own_{k}_{sid}") for k in ("rent", "mtr", "str")}
    sel["growth"] = (ss.get(f"g_{sid}") if ss.get(f"g_{sid}") is not None else 2) / 100
    return sel


RANGE_LBL = {"rent": (("Rent you'd get (a month)", "Renta que recibiría (al mes)"),),
             "mtr": (("30+ day rate (a month, before costs)", "Tarifa 30+ días (al mes, antes de gastos)"),),
             "str": (("Airbnb income (a year, before costs)", "Ingreso de Airbnb (al año, antes de gastos)"),)}


@timed('ranges')
def ranges_block(sid, out):
    lv = {k: v for k, v in (out.get("levels") or {}).items() if v}
    if not lv:
        return
    st.markdown(f"<div class='bz-lbl'>{L('Not sure? Try low, typical or high', '¿No está segura? Pruebe bajo, típico o alto')}</div>", unsafe_allow_html=True)
    for k in ("rent", "mtr", "str"):
        if k not in lv:
            continue
        v = lv[k]
        names = {"low": L("Low", "Bajo"), "typ": L("Typical", "Típico"), "high": L("High", "Alto"), "own": L("✏️ Mine", "✏️ Mío")}
        st.segmented_control(P(RANGE_LBL[k][0]), ["low", "typ", "high", "own"], key=f"lv_{k}_{sid}", default="typ", required=True, width="stretch",
                             format_func=lambda x, v=v, names=names: names[x] if x == "own" else f"{names[x]} {kmoney(v.get(x))}")
        if st.session_state.get(f"lv_{k}_{sid}") == "own":
            st.number_input(L("Your number ($)", "Su número ($)"), min_value=0, max_value=500_000, step=50, value=int(st.session_state.get(f"own_{k}_{sid}") or v["typ"]), key=f"own_{k}_{sid}")
    notes = []
    if lv.get("rent", {}).get("estimate"):
        notes.append(L("Room rent is an estimate from the whole-home rent (few room posts nearby).", "La renta del cuarto es un estimado según la renta de toda la casa (pocos anuncios cerca)."))
    if lv.get("rent", {}).get("hud"):
        notes.append(L("Rent range is HUD's fair rent ±10% (few listings nearby).", "El rango de renta es la renta justa de HUD ±10% (pocos anuncios cerca)."))
    notes.append(L("Low and high = the cheaper and pricier quarter of similar places nearby. Typical = the middle.",
                   "Bajo y alto = la cuarta parte más barata y más cara de lugares parecidos cerca. Típico = el medio."))
    st.caption(" ".join(notes))


@timed('cash')
def cash_card(sid, out, rent_ref):
    cash = out.get("cash")
    if not cash:
        return
    cols = C.labels(out, False)
    avail = [c["key"] for c in cols if c["key"] in cash["five"]]
    names = {c["key"]: P(c["title"]) for c in cols}
    st.markdown(f"#### {L('💵 Cash in, cash out', '💵 Lo que entra y sale')}")
    pick = st.segmented_control(L("Option", "Opción"), avail, key=f"cc_{sid}", default=("long" if "long" in avail else avail[0]), required=True,
                                label_visibility="collapsed", width="stretch", format_func=lambda k: names[k])
    st.segmented_control(L("Home value grows each year", "El valor sube cada año"), [0, 2, 3], key=f"g_{sid}", default=2, required=True, format_func=lambda g: f"{g}%")
    c = next(x for x in out["cols"] if x["key"] == pick)
    f5 = cash["five"][pick]
    furn = cash["furniture"] if pick == "short" else 0
    pay = c["pay"]
    rows = [(L("Cash on closing day", "Dinero el día del cierre"), kmoney(cash["cash_to_close"] + furn),
             L(f"{kmoney(cash['down'])} down + {kmoney(cash['closing'])} fees", f"{kmoney(cash['down'])} inicial + {kmoney(cash['closing'])} de cierre") + (L(f" + {kmoney(furn)} furniture", f" + {kmoney(furn)} muebles") if furn else "")),
            ((L("Each month you pay", "Cada mes paga") if pay >= 0 else L("Each month you earn", "Cada mes gana")), kmoney(abs(pay)), ""),
            (L("Home value in 5 years", "Valor en 5 años"), kmoney(f5["value_5y"]), L(f"at {f5['growth']:.0%} a year (you picked)", f"al {f5['growth']:.0%} al año (usted eligió)")),
            (L("Loan paid down in 5 years", "Préstamo pagado en 5 años"), kmoney(f5["principal_paid"]), ""),
            (L("Your share of the home then", "Su parte de la casa entonces"), kmoney(f5["equity_5y"]), L("value minus what you'd still owe", "valor menos lo que aún debería")),
            (L("Total cash out over 5 years", "Total que sale en 5 años"), kmoney(f5["paid_5y"]), L("closing day + 60 months", "cierre + 60 meses"))]
    if rent_ref:
        rows.append((L("Renting a place like it instead", "Alquilar algo parecido"), kmoney(rent_ref * 60), L(f"{kmoney(rent_ref)}/mo for 60 months, rent kept flat", f"{kmoney(rent_ref)}/mes por 60 meses, renta fija")))
    html("<div class='bz-card'>" + "".join(f"<div class='bz-kv'><span>{H.escape(a)}<br><span class='bz-small'>{H.escape(s)}</span></span><b>{H.escape(b)}</b></div>" for a, b, s in rows) + "</div>")
    st.caption(L("Selling costs, big repairs and rent increases are not included. Value growth is your pick, not a forecast.",
                 "No incluye gastos de venta, reparaciones grandes ni aumentos de renta. El crecimiento del valor lo elige usted; no es un pronóstico."))


def _place_rent(c):
    url = c.get("url") if str(c.get("url", "")).startswith("http") else None
    bd = f"{int(c['beds'])} {L('bd', 'hab')}" if c.get("beds") not in (None, "") and c.get("beds") == c.get("beds") else ""
    name = H.escape(S.listing_name(c))[:60]
    return (f"<div class='bz-place'><div><div class='t'>{name}</div><div class='m'>{money(c.get('price'))}{L('/mo', '/mes')} · {bd} · {S.miles(c.get('dist_km'))} · {H.escape(str(c.get('source') or ''))}</div>"
            + (f"<a href='{H.escape(url)}' target='_blank'>{L('Open', 'Abrir')}</a>" if url else "") + "</div></div>")


def _place_iab(c, kind):
    url = c.get("listing_url") if str(c.get("listing_url", "")).startswith("http") else None
    img = c.get("picture_url") if str(c.get("picture_url", "")).startswith("https://") else None
    bd = f"{int(c['bedrooms'])} {L('bd', 'hab')}" if c.get("bedrooms") not in (None, "") and c.get("bedrooms") == c.get("bedrooms") else L("room", "cuarto")
    if kind == "mtr":
        m = f"{money(c.get('price_num'))}{L('/night listed', '/noche')} (≈{money((c.get('price_num') or 0) * 30.4)}{L('/mo', '/mes')}) · {L('min', 'mín')} {int(c.get('minimum_nights') or 0)} {L('nights', 'noches')}"
    else:
        m = f"{money(c.get('price_num'))}{L('/night', '/noche')} · ≈{int(c.get('estimated_occupancy_l365d') or 0)} {L('nights/yr', 'noches/año')} · {money(c.get('estimated_revenue_l365d'))}{L('/yr', '/año')}"
    return (f"<div class='bz-place'>" + (f"<img src='{H.escape(img)}' loading='lazy' alt=''>" if img else "")
            + f"<div><div class='t'>{H.escape(str(c.get('name') or ''))[:60]}</div><div class='m'>{bd} · {m} · {S.miles(c.get('dist_km'))}</div>"
            + (f"<a href='{H.escape(url)}' target='_blank'>Airbnb</a>" if url else "") + "</div></div>")


@timed('places')
def places_block(lists, rules, town, datasets, ok_airbnb, d30, head=True):
    if head:
        st.markdown(f"#### {L('🏘️ Similar places', '🏘️ Lugares parecidos')}")
    t1, t2, t3 = st.tabs([L("To rent", "Para alquilar"), L(f"{d30}+ day", f"{d30}+ días"), "Airbnb"])
    borrowed = town and datasets and not any(town.lower().replace(" ", "-") in d for d in datasets)
    rough = L(f"Rough estimate: these listings are in {', '.join(sorted({d.split('/')[1].replace('-', ' ').title() for d in datasets}))}, not {town}.",
              f"Estimado aproximado: estos anuncios están en {', '.join(sorted({d.split('/')[1].replace('-', ' ').title() for d in datasets}))}, no en {town}.") if borrowed else ""
    with t1:
        rows = lists.get("rent") or []
        html("".join(_place_rent(c) for c in rows[:8]) if rows else f"<div class='bz-small'>{L('No rentals found nearby right now.', 'No encontramos alquileres cerca ahora.')}</div>")
    with t2:
        rows = lists.get("mtr") or []
        if rough:
            st.caption("⚠️ " + rough)
        html("".join(_place_iab(c, "mtr") for c in rows[:8]) if rows else f"<div class='bz-small'>{L('No furnished monthly listings nearby.', 'No hay anuncios amueblados mensuales cerca.')}</div>")
    with t3:
        if ok_airbnb is False:
            html(f"<div class='bz-warn'>🚫 {L('Airbnb (short stays) is not allowed for this home here. These show the market only.', 'Airbnb (estadías cortas) no se permite para esta casa aquí. Esto solo muestra el mercado.')}</div>")
        elif ok_airbnb is None:
            html(f"<div class='bz-warn'>❓ {L('We are not sure Airbnb is allowed here. Ask the town before counting on it.', 'No sabemos si Airbnb se permite aquí. Pregunte al municipio antes de contar con eso.')}</div>")
        if rough:
            st.caption("⚠️ " + rough)
        rows = lists.get("str") or []
        html("".join(_place_iab(c, "str") for c in rows[:8]) if rows else f"<div class='bz-small'>{L('No active Airbnb listings nearby.', 'No hay anuncios activos de Airbnb cerca.')}</div>")
    st.caption(L("Airbnb and 30+ day listings: Inside Airbnb (public data). Photos come from those listings.", "Anuncios de Airbnb y 30+ días: Inside Airbnb (datos públicos). Las fotos son de esos anuncios."))


@timed('season')
def season_block(s, town, head=True):
    if not s:
        return
    idx = (s.get("short") or {}).get("index") or []
    if not idx or None in idx:
        return
    mx = max(idx)
    bars = "".join(f"<div class='{'lo' if v < 1 else ''}' style='height:{max(v / mx, .05) * 100:.0f}%' title='{v:.2f}'></div>" for v in idx)
    mons = "".join(f"<span>{P(m)}</span>" for m in MONTHS)
    city = s["city"].replace("-", " ").title()
    if head:
        st.markdown(f"#### {L('📅 Busy vs slow months', '📅 Meses de mucho y poco movimiento')}")
    busy = [P(("Jan", "Ene")), P(("Feb", "Feb")), P(("Mar", "Mar")), P(("Apr", "Abr")), P(("May", "May")), P(("Jun", "Jun")), P(("Jul", "Jul")), P(("Aug", "Ago")),
            P(("Sep", "Sep")), P(("Oct", "Oct")), P(("Nov", "Nov")), P(("Dec", "Dic"))]
    top = [busy[i] for i in sorted(range(12), key=lambda i: -idx[i])[:3]]
    low = [busy[i] for i in sorted(range(12), key=lambda i: idx[i])[:2]]
    html(f"<div class='bz-bars'>{bars}</div><div class='bz-mon'>{mons}</div>")
    md(L(f"Busiest: {', '.join(top)}. Slowest: {', '.join(low)}.", f"Más movidos: {', '.join(top)}. Más lentos: {', '.join(low)}."))
    st.caption(L(f"Stand-in for bookings: guest reviews per month for {city} Airbnb listings, {s['window'][0][:4]}-{s['window'][1][:4]} ({s['short']['n_reviews']:,} reviews, Inside Airbnb)."
                 + (f" Borrowed from {city} for {town}: rough estimate." if town and city.lower() != town.lower() else ""),
                 f"Aproximación de reservas: reseñas por mes de anuncios de Airbnb en {city}, {s['window'][0][:4]}-{s['window'][1][:4]} ({s['short']['n_reviews']:,} reseñas, Inside Airbnb)."
                 + (f" Tomado de {city} para {town}: estimado aproximado." if town and city.lower() != town.lower() else "")))


def rules_card(sr, town):
    icon, en, es = S.airbnb_line(sr, "owner")
    conf = sr.get("confidence")
    cl = {"high": L("sure", "seguro"), "medium": L("fairly sure", "bastante seguro"), "low": L("not sure", "poco seguro")}.get(conf, "")
    links = [f"<a href='{H.escape(m.group(0).rstrip(')'))}' target='_blank'>{H.escape(m.group(0).split('/')[2])}</a>" for m in (re.search(r"https?://\S+", x) for x in sr.get("sources", [])) if m]
    html(f"<div class='bz-card'><div class='t'>{icon} {H.escape(es if ES() else en)}</div><div class='m'>{H.escape(S.plain(sr.get('summary_es' if ES() else 'summary_en', '')))}</div>"
         f"<div class='bz-small'>{L('Source', 'Fuente')}: {', '.join(links[:2])}" + (f" · {L('checked', 'revisado')} {sr.get('checked') or sr.get('last_verified') or ''}" if (sr.get('checked') or sr.get('last_verified')) else "")
         + (f" · {L('how sure', 'certeza')}: {cl}" if cl else "") + "</div></div>")


def report_cv(out, drive, first, extra_lines=()):
    cols = C.labels(out, first)
    return {"cols": [{k: c[k] for k in ("title", "pay_lbl", "pay", "sub", "badge")} for c in cols],
            "drive": (C.drive_text(drive, False), C.drive_text(drive, True)) if drive else None, "lines": list(extra_lines)}


def lists_for_property(r, sel):
    ex = r.get("extra") or {}
    ro = sel["rent_out"]
    if ro == "room":
        return {"rent": (r.get("rooms") or {}).get("comps") or [], "mtr": (ex.get("room_mtr") or {}).get("comps") or [], "str": (ex.get("room_str") or {}).get("comps") or []}
    if ro == "unit":
        u = (ex.get("units") or {}).get(str(sel["unit_beds"])) or (ex.get("units") or {}).get(sel["unit_beds"]) or {}
        return {"rent": u.get("ltr_comps") or [], "mtr": (u.get("mtr") or {}).get("comps") or [], "str": (u.get("str") or {}).get("comps") or []}
    return {"rent": (r.get("ltr") or {}).get("comps") or [], "mtr": (r.get("mtr") or {}).get("comps") or [], "str": (r.get("str") or {}).get("comps") or []}


# ------------------------------------------------------------------ FHA or normal loan? (county limits, HUD condo list, co-ops, fixer/cash flags)
from bellazu.sources import fha as FHA                           # noqa: E402

FHA_KIND = {"condo": "condo", "co-op": "coop", "single-family": "house", "townhouse": "house", "2-family": "2fam", "3-4-family": "3-4fam",
            "multi-family": "2fam"}


def fha_for_row(h):
    """Feed card: no extra call. Type from the list call, condo building from the prebuilt HUD list, price vs the county limit."""
    k = "coop" if "coop" in str(h.get("type") or "") else {"condo": "condo", "2fam": "2fam", "house": "house"}.get(h.get("kind"), "other")
    return FHA.assess(k, h.get("price"), h.get("town") or h.get("_t"), h.get("address"), h.get("zip"), flags={f: True for f in h.get("flags") or []})


def fha_for_addr(addr, r=None):
    """Opened listing / checked address: the type chosen (or from the listing), the town and ZIP from the check, the listing text if we have it."""
    ss = st.session_state
    fo = facts_for(addr)
    meta = (ss.get("addr_meta") or {}).get(addr.strip().lower()) or {}
    g = (ss.get("gallery") or {}).get(addr.strip().lower()) or {}
    f = (r or {}).get("facts") or {}
    t = fo.get("type") or meta.get("type") or ui_type_of(r)
    if not t:
        return None
    price = fo.get("price") or f.get("price") or g.get("price")
    town = (r or {}).get("town") or meta.get("town") or g.get("town")
    z = (r or {}).get("zip") or meta.get("zip") or g.get("zip")
    return FHA.assess(FHA_KIND.get(t, "other"), price, town, (r or {}).get("address") or addr, z, text=g.get("text"),
                      flags={x: True for x in g.get("flags") or []}, units=4 if t == "3-4-family" else None)


def ui_type_of(r):
    own = str(((r or {}).get("facts") or {}).get("ownership") or "").lower()
    if not own:
        return None
    if "co-op" in own or "coop" in own:
        return "co-op"
    if "condo" in own:
        return "condo"
    if "multi" in own:
        return "3-4-family" if ((r or {}).get("extra") or {}).get("units_total", 2) >= 3 else "2-family"
    if "single" in own or "house" in own or "town" in own:
        return "single-family"
    return None


def _prop_comps(r, sel, base, own, rent, sid):
    f = r.get("facts") or {}
    multi = own == "multi-family"
    if multi:
        b = int(sel.get("unit_beds") or 2)
        u = (base.get("units") or {}).get(b) or {}
        est, lbl, hudv, mtr, strs = (u.get("ltr") or {}).get("typ"), L("for the other unit", "para la otra unidad"), u.get("hud"), u.get("mtr"), u.get("str")
    else:
        b = f.get("beds")
        est, lbl, mtr, strs = rent, None, r.get("mtr"), r.get("str")
        hudv = (r.get("benchmarks") or {}).get("hud_safmr")
        if isinstance(hudv, dict):
            hudv = hudv.get(f"{min(max(int(b or 0), 0), 4)}br") or hudv.get("rent")
    if not isinstance(hudv, (int, float)):
        hudv = _hud_for(r.get("town"), b)
    kind = "condo" if ("condo" in own or "co-op" in own) else "house" if "single" in own else None
    rent_comps_box("p_" + sid, r.get("town"), b, kind, r.get("lat"), r.get("lon"), est, lbl, hudv, (r.get("rentcast") or {}).get("avm_comps"),
                   r.get("str_rules"), strs, mtr, air_ok=C.airbnb_ok(r.get("str_rules") or {}, "multi-family" if multi else "single-family", "unit" if multi else "room"))


def fha_for_saved(x):
    tk = (x.get("type_lbl") or [""])[0].lower()
    k = "condo" if tk == "condo" else "coop" if tk == "co-op" else "house" if tk in ("house", "townhouse") else "2fam" if tk.startswith("2") else \
        "3-4fam" if tk.startswith("3") else None
    if not k:
        return None
    return FHA.assess(k, x.get("price"), x.get("town"), x.get("addr"), None)


def fha_loan_lbl(fa, ln=None):
    if not fa or fa.get("loan") == "fha":
        return L("FHA, 3.5% down", "FHA, 3.5% inicial")
    pct = f"{fa['down'] * 100:g}%"
    why = {"coop": L("co-op", "co-op"), "condo_no": L("building not on the FHA list", "edificio fuera de la lista FHA"),
           "condo_unknown": L("building not confirmed for FHA", "edificio no confirmado para FHA"), "over_limit": L("above the FHA limit", "sobre el límite FHA")}.get(fa.get("code"), "")
    return L(f"normal loan, {pct} down", f"préstamo normal, {pct} inicial") + (f" ({why})" if why else "")


@timed('fha_card')
def fha_card(fa, where, inline=False):
    if not fa:
        return
    c = fa.get("code")
    cls = "ok" if c in ("ok", "condo_ok") else "no" if c in ("coop", "condo_no", "over_limit") else "q"
    notes = [P(FHA.FLAG_NOTE[x]) for x in fa.get("flags") or [] if x in FHA.FLAG_NOTE]
    lim = fa.get("limit")
    sub = []
    if c in ("ok", "condo_ok") and lim:
        sub.append(L(f"{(fa.get('county') or '').title()} County FHA limit {money(lim)} ({fa.get('units', 1)} unit{'s' if fa.get('units', 1) > 1 else ''}, HUD 2026).",
                     f"Límite FHA del condado de {(fa.get('county') or '').title()}: {money(lim)} ({fa.get('units', 1)} unidad{'es' if fa.get('units', 1) > 1 else ''}, HUD 2026)."))
    if c == "condo_ok" and fa.get("match"):
        sub.append(L(f"On HUD's list as “{fa['match']['name'].title()}”.", f"En la lista de HUD como “{fa['match']['name'].title()}”."))
    if c == "condo_no" and fa.get("match"):
        m = fa["match"]
        stt = {"Expired": ("expired", "vencida"), "Withdrawn": ("withdrawn", "retirada"), "Rejected": ("rejected", "rechazada"),
               "Rejected Single-Unit Approval": ("single-unit approval rejected", "aprobación de unidad rechazada")}.get(m.get("status"), (m.get("status", "").lower(), m.get("status", "").lower()))
        sub.append(L(f"HUD list: “{m['name'].title()}”, {stt[0]}" + (f" {fa['exp']}" if fa.get("exp") else "") + ".",
                     f"Lista de HUD: “{m['name'].title()}”, {stt[1]}" + (f" {fa['exp']}" if fa.get("exp") else "") + "."))
    if fa.get("loan") == "conv" and c in ("condo_no", "condo_unknown") and loan_prof()["kind"] == "fha":
        sub.append(L("The numbers still use your FHA terms. Ask your lender about a single-unit approval; otherwise you'd need a normal loan (often 10% down).",
                     "Los números siguen usando sus términos FHA. Pregunte a su banco por una aprobación de unidad individual; si no, necesitaría un préstamo normal (a menudo 10% inicial)."))
    elif c in ("condo_ok", "condo_no", "condo_unknown") and loan_prof()["kind"] != "fha":
        sub.append(L("You're using a conventional loan, so the building doesn't need HUD's FHA approval.",
                     "Usted usa un préstamo convencional, así que el edificio no necesita la aprobación FHA de HUD."))
    elif fa.get("loan") == "conv":
        sub.append(L(f"So the numbers below use a normal loan with at least {fa['down'] * 100:g}% down. Change it in ⚙️ My settings.",
                     f"Por eso los números usan un préstamo normal con al menos {fa['down'] * 100:g}% inicial. Cámbielo en ⚙️ Mis ajustes."))
    sub.append(L("Your lender has the final say.", "Su banco tiene la última palabra."))
    html(f"<div class='bz-fha {cls}'><b>{H.escape(P(FHA.badge(fa)))}</b>" + "".join(f"<div class='n'>⚠️ {H.escape(x)}</div>" for x in notes)
         + f"<div class='s'>{H.escape(' '.join(sub))}</div></div>")
    fha_explainer(where, inline)


def fha_explainer(where, inline=False):
    """The FHA explainer in its own expander, or (inline=True) as plain text inside an expander the caller already opened."""
    if inline:
        st.markdown(f"**{L('What is FHA approval?', '¿Qué es la aprobación FHA?')}**")
        _fha_text()
        return
    with st.expander(L("What is FHA approval?", "¿Qué es la aprobación FHA?"), key=f"fhax_{where}"):
        _fha_text()


def _fha_text():
    if True:
        md(L("**FHA** is a government-backed loan that lets you buy with **3.5% down** if you'll live in the home. It works for houses and 2-4 family homes "
             "if the price is under the county limit and the home passes the FHA appraisal (safe, sound, working heat, water and power).\n\n"
             "**Condos:** the whole building must be on HUD's FHA-approved list (approvals expire every few years). If it isn't, you need a normal loan "
             "(often 10% down or more), or your lender can try a single-unit approval.\n\n"
             "**Co-ops:** FHA almost never works. Expect a co-op loan with 10-20% down plus board approval and income rules.\n\n"
             "**Fixers:** an FHA 203(k) loan can include repair money. Cash-only and auction homes usually can't use a loan.\n\n"
             "Your lender has the final say. Sources: HUD 2026 FHA loan limits and HUD's FHA condo list.",
             "**FHA** es un préstamo respaldado por el gobierno que le permite comprar con **3.5% inicial** si va a vivir en la casa. Sirve para casas y de 2 a 4 familias "
             "si el precio está bajo el límite del condado y la casa pasa el avalúo FHA (segura, sólida, con calefacción, agua y luz funcionando).\n\n"
             "**Condos:** todo el edificio debe estar en la lista de HUD aprobada por FHA (las aprobaciones vencen cada pocos años). Si no está, necesita un préstamo normal "
             "(a menudo 10% inicial o más), o su banco puede intentar una aprobación de unidad individual.\n\n"
             "**Co-ops:** FHA casi nunca sirve. Espere un préstamo de co-op con 10-20% inicial más aprobación de la junta y reglas de ingreso.\n\n"
             "**Casas para arreglar:** un préstamo FHA 203(k) puede incluir dinero para reparaciones. Las casas solo en efectivo o en subasta casi nunca aceptan préstamo.\n\n"
             "Su banco tiene la última palabra. Fuentes: límites FHA 2026 de HUD y la lista de condos FHA de HUD."))


def fha_badge_short(fa):
    if not fa:
        return ""
    t = L("✅ FHA OK · 3.5% down", "✅ FHA sí · 3.5% inicial") if fa.get("code") == "ok" else P(FHA.badge(fa))
    fl = [P(FHA.FLAG_RX[[k for k, _, _ in FHA.FLAG_RX].index(x)][2]) for x in fa.get("flags") or [] if x in [k for k, _, _ in FHA.FLAG_RX]]
    return t + (" · ⚠️ " + ", ".join(fl) if fl else "")


# ------------------------------------------------------------------ "What similar places rent for": for-rent listings nearby, median + range, our estimate vs them
def _miles(a, b, c, d):
    import math
    try:
        la1, lo1, la2, lo2 = map(math.radians, (float(a), float(b), float(c), float(d)))
    except Exception:
        return None
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def _q(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    i = (len(xs) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def _load_rentals(town):
    """Button callback: the one for-rent list call for this town (18h cache)."""
    st.session_state.setdefault("rc_load", set()).add(town)


@timed('comps')
def rent_comps_box(key, town, beds, kind=None, lat=None, lon=None, est=None, est_lbl=None, hud=None, rc_comps=None, rules=None, strs=None, mtr=None,
                   calls_ok=True, air_ok=None):
    """Realty in US for-rent list (cached per town; a call only on a tap, or never when calls_ok=False), else RentCast comps already
    fetched, plus HUD fair rent; furnished 30+ day / Airbnb from Inside Airbnb when legal."""
    ss = st.session_state
    b = int(beds) if beds is not None else None
    rows, src, res = [], None, None
    if town and listings.available():
        if listings.cached(town, "for_rent") or (calls_ok and town in (ss.get("rc_load") or set())):
            res = feed(town, "for_rent")
            if res.get("ok"):
                rows, src = res["rows"], "realty"
    m = [r for r in rows if r.get("price") and (b is None or r.get("beds") == b or (b >= 3 and (r.get("beds") or 0) >= 3))]
    typed = False
    if kind in ("condo", "house"):
        mk = [r for r in m if r.get("kind") == kind]
        if len(mk) >= 4:
            m, typed = mk, True
    for r in m:
        r = r
        r["_mi"] = _miles(lat, lon, r.get("lat"), r.get("lon")) if lat and lon and r.get("lat") else None
    if lat and lon:
        m.sort(key=lambda r: (r["_mi"] is None, r["_mi"] or 0))
    if not m and rc_comps:
        m = [{"price": c.get("price"), "beds": c.get("beds"), "baths": c.get("baths"), "address": c.get("address"), "_mi": (c.get("dist_km") or 0) / 1.609,
              "days": c.get("days_old"), "url": c.get("url"), "photo": None} for c in rc_comps if c.get("price") and (b is None or c.get("beds") == b)]
        src = "rentcast" if m else None
    prices = [float(r["price"]) for r in m]
    bl = (L("studio", "estudio") if b == 0 else (L(f"{b}-bedroom", f"de {b} habitaciones") if b is not None else ""))
    head = L(f"🏷️ What similar places rent for", f"🏷️ Lo que se alquila algo parecido")
    body = ""
    if prices:
        n = len(prices)
        med = _q(prices, .5)
        lo, hi = (_q(prices, .1), _q(prices, .9)) if n >= 10 else (min(prices), max(prices))
        where = (L(f"{bl} rentals listed now in {town}" + (" (same type)" if typed else ""), f"alquileres {bl} publicados ahora en {town}" + (" (mismo tipo)" if typed else ""))
                 if src == "realty" else L(f"{bl} rentals RentCast found near this address", f"alquileres {bl} que RentCast encontró cerca de esta dirección"))
        body += f"<div class='sub'>{H.escape(where)}</div>"
        body += (f"<div class='st'><div><span>{L('Median', 'Mediana')}</span><b>{money(med)}</b></div><div><span>{L('Low-high', 'Bajo-alto')}</span>"
                 f"<b>{money(lo)}-{money(hi)}</b></div><div><span>{L('Listings', 'Anuncios')}</span><b>{n}</b></div></div>")
        if est:
            share = sum(1 for p_ in prices if p_ < est) / n
            pos = (L("on the low side of", "en la parte baja de") if share < .25 else L("on the high side of", "en la parte alta de") if share > .75
                   else L("in the middle of", "en el medio de"))
            body += f"<div class='cmp'>{L(f'Our estimate {money(est)}', f'Nuestro estimado {money(est)}')}{(' ' + H.escape(est_lbl)) if est_lbl else ''} {L('is', 'está')} {pos} {n} {L('similar rentals', 'alquileres parecidos')}.</div>"
        for r in m[:5]:
            d = r.get("days")
            dl = (L("today", "hoy") if d == 0 else L("1 day", "1 día") if d == 1 else L(f"{d} days", f"{d} días")) if d is not None else ""
            dist = (f"{r['_mi']:.1f} mi" if r.get("_mi") is not None else (r.get("town") or ""))
            facts = " · ".join(x for x in [f"{r['beds']} {L('bd', 'hab')}" if r.get("beds") is not None else "", f"{float(r['baths']):g} {L('ba', 'baño' if float(r['baths']) == 1 else 'baños')}" if r.get("baths") else "", dist, dl] if x)
            img = f"<img src='{H.escape(r['photo'])}' loading='lazy' alt=''>" if r.get("photo") else "<div class='ni'>🏠</div>"
            a0, a1 = (f"<a href='{H.escape(r['url'])}' target='_blank' rel='noopener'>", "</a>") if r.get("url") else ("", "")
            body += f"{a0}<div class='row'>{img}<div><b>{money(r['price'])}{L('/mo', '/mes')}</b><div class='f'>{H.escape(facts)}</div><div class='f a'>{H.escape((r.get('address') or '').split(',')[0])}</div></div></div>{a1}"
    else:
        body += f"<div class='sub'>{L('No rentals listed now to compare with.', 'No hay alquileres publicados ahora para comparar.') if src or res else L('Rentals listed now in this town are not loaded yet.', 'Los alquileres publicados en este pueblo aún no se cargaron.')}</div>"
        if est:
            body += f"<div class='cmp'>{L(f'Our estimate: {money(est)}', f'Nuestro estimado: {money(est)}')}{(' ' + H.escape(est_lbl)) if est_lbl else ''}.</div>"
    extra = []
    if hud:
        extra.append(L(f"HUD fair rent ({bl or 'this size'}, this ZIP): {money(hud)}/mo", f"Renta justa de HUD ({bl or 'este tamaño'}, este ZIP): {money(hud)}/mes"))
    if mtr and mtr.get("ok") and mtr.get("monthly_equiv_median"):
        extra.append(L(f"Furnished 30+ day stays: about {money(mtr['monthly_equiv_median'])}/mo ({mtr.get('n', 0)} nearby)",
                       f"Amueblado 30+ días: unos {money(mtr['monthly_equiv_median'])}/mes ({mtr.get('n', 0)} cerca)"))
    sm = (strs or {}).get("summary") or {}
    if air_ok is True and sm.get("adr_median"):
        extra.append(L(f"Airbnb (with the town permit): about {money(sm['adr_median'])}/night ({sm.get('n', 0)} nearby)",
                       f"Airbnb (con permiso del pueblo): unos {money(sm['adr_median'])}/noche ({sm.get('n', 0)} cerca)"))
    if extra:
        body += "<div class='ex'>" + "<br>".join(H.escape(x) for x in extra) + "</div>"
    srcs = [L("realtor.com via Realty in US", "realtor.com vía Realty in US") if src == "realty" else "", "RentCast" if src == "rentcast" else "",
            "HUD" if hud else "", "Inside Airbnb" if extra and (mtr or sm) else ""]
    body += f"<div class='src'>{L('Sources', 'Fuentes')}: {', '.join(x for x in srcs if x) or '—'}</div>"
    html(f"<div class='bz-rc'><div class='h'>{head}</div>{body}</div>")
    if town and listings.available() and not src and calls_ok and not listings.cached(town, "for_rent"):
        st.button(L(f"🔎 Show rentals listed now in {town}", f"🔎 Ver alquileres publicados en {town}"), key=f"rcl_{key}", width="stretch",
                  on_click=_load_rentals, args=(town,))
    elif town and src == "realty" and len(m) > 5 and res:
        st.caption(L(f"Showing the 5 closest of {len(m)}. See them all under “For rent” in the town's homes list.",
                     f"Mostramos los 5 más cercanos de {len(m)}. Véalos todos en “En alquiler” en la lista de casas del pueblo."))


ARV_KIND = {"condo": "condos", "co-op": "coop", "single-family": "single_family", "multi-family": "multi_family", "townhouse": "townhomes"}


def _sqft_of(text):
    m = re.search(r"(\d[\d,]{2,5})\s*(?:sq\.?\s?ft|sqft|square f|sf\b|s\.f\.)", str(text or ""), re.I)
    try:
        v = int(m.group(1).replace(",", "")) if m else None
    except ValueError:
        v = None
    return v if v and 250 <= v <= 8000 else None


def _load_sold(town):
    """Button callback: the one sold-list call for this town (kept 30 days)."""
    st.session_state.setdefault("sold_load", set()).add(town)


def _arv_row(c, sold, es=False):
    """One comp: photo, price (sold/asking), $/sqft, facts, address, distance, condition cues."""
    ps = c.get("_ppsf")
    d = c.get("sold_date")
    if sold:
        try:
            dd = dt.date.fromisoformat(d)
            when = L("sold ", "vendida ") + dd.strftime("%b %Y") if not ES() else "vendida " + ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"][dd.month - 1] + f" {dd.year}"
        except Exception:
            when = L("sold", "vendida")
        pr = f"{money(c['price'])}"
        sub = when
    else:
        pr = f"{money(c['price'])}"
        sub = L("asking, not sold", "precio pedido, no vendida")
    facts = " · ".join(x for x in [f"{c['beds']} {L('bd', 'hab')}" if c.get("beds") is not None else "",
                                   f"{float(c['baths']):g} {L('ba', 'baño' if float(c['baths']) == 1 else 'baños')}" if c.get("baths") else "",
                                   f"{int(c['sqft']):,} ft²" if c.get("sqft") else "", f"{money(ps)}/ft²" if ps else "",
                                   f"{c['_mi']:.1f} mi" if c.get("_mi") is not None else ""] if x)
    ck = c.get("_cues") or []
    cues = ARV.cue_labels([k for k in ck if k != "work"], ES())
    warn = ARV.cue_labels([k for k in ck if k == "work"], ES())
    cu = (f"<div class='cue'>{H.escape(' · '.join(cues))}</div>" if cues else "") + (f"<div class='cue w'>{H.escape(' · '.join(warn))}</div>" if warn else "")
    img = f"<img src='{H.escape(c['photo'])}' loading='lazy' alt=''>" if c.get("photo") else "<div class='ni'>🏠</div>"
    return (f"<div class='row'>{img}<div><b>{pr}</b> <span class='f'>{H.escape(sub)}</span><div class='f'>{H.escape(facts)}</div>"
            f"<div class='f a'>{H.escape((c.get('address') or '').split(',')[0])}</div>{cu}</div></div>")


_ARV_TOK = "\x00COMP%d\x00"


def _comp_app_row(c):
    """The app's own saved listing for a comp (so it opens inside BellaZu), or None. Never calls the API."""
    if c.get("id"):
        r = listings.find_row(c["id"])
        if r:
            return r
    if not c.get("_sold") and c.get("id") and c.get("address") and c.get("price"):
        return c                                          # an active comp is already a listing row from the saved lists
    na = _norm_addr(c.get("address"))
    if na:
        for r in listings.all_cached_rows("for_sale"):    # a sold home that is listed again now
            if _norm_addr(r.get("address")) == na:
                return r
    return None


def _open_comp(row, cur_id, cur_addr):
    """Open a comp inside BellaZu; remember where we came from so there is a way back."""
    ss = st.session_state
    tr = list(ss.get("arv_trail") or [])
    if cur_addr and (not tr or tr[-1][1] != cur_addr):
        tr.append((str(cur_id or ""), cur_addr))
    ss.arv_trail = tr[-8:]
    tn = towns.normalize(row.get("town") or "")
    ss.go = ("listing", dict(row, _t=tn.get("name") or row.get("town")))
    ss._keep_chain = True
    ss._full = True


def _arv_back():
    ss = st.session_state
    tr = list(ss.get("arv_trail") or [])
    if not tr:
        return
    pid, addr = tr.pop()
    ss.arv_trail = tr
    ss._keep_chain = True
    row = listings.find_row(pid) if pid else None
    if row:
        tn = towns.normalize(row.get("town") or "")
        ss.go = ("listing", dict(row, _t=tn.get("name") or row.get("town")))
    else:
        ss.go = ("addr", addr, "keep")
    ss._full = True


def arv_back_button(addr):
    tr = st.session_state.get("arv_trail") or []
    if tr and tr[-1][1] != addr:
        lbl = tr[-1][1].split(",")[0]
        st.button(L(f"← Back to {lbl}", f"← Volver a {lbl}"), key="arv_back_btn", type="tertiary", on_click=_arv_back)


def _arv_comps_render(c, sold, sid, tag, cur_id, cur_addr):
    """A comp row with its own button: 'Open in BellaZu' when we have it saved, else a clearly labeled outside link."""
    app = _comp_app_row(c)
    if app:
        st.button(L("Open in BellaZu ›", "Abrir en BellaZu ›"), key=f"arvo_{sid}_{tag}", type="tertiary", on_click=_open_comp, args=(app, cur_id, cur_addr))
    elif str(c.get("url") or "").startswith("http"):
        st.link_button(L("Not saved in BellaZu: see on realtor.com ↗", "No está guardada en BellaZu: ver en realtor.com ↗"), c["url"], type="tertiary")


def arv_section(r, sid, addr):
    """'If I fix it up': what nicer units in the same building and nearby sold for (or ask), a rough after-repair value, and a rehab check."""
    ss = st.session_state
    f = r.get("facts") or {}
    g = (ss.get("gallery") or {}).get(addr.strip().lower()) or {}
    pid = g.get("id") or None
    d = listings.detail_cached(str(pid)) if pid else None
    d = d if (d and d.get("ok")) else {}
    row = listings.find_row(pid) or {}
    price = f.get("price") or g.get("price") or row.get("price")
    text = d.get("text") or g.get("text") or ""
    sqft = f.get("sqft") or d.get("sqft") or row.get("sqft") or _sqft_of(text)
    own = (f.get("ownership") or "").lower()
    typ = row.get("type") or d.get("type") or ARV_KIND.get(("co-op" if "co-op" in own else "condo" if "condo" in own else "multi-family" if "multi" in own
                                                            else "townhouse" if "town" in own else "single-family"), "condos")
    town = r.get("town") or row.get("town") or g.get("town")
    if not (price and town):
        st.caption(L("Not enough about this home to compare yet.", "Aún no hay suficientes datos de esta casa para comparar."))
        return
    subj = ARV.subject_of(addr, price, f.get("beds") if f.get("beds") is not None else row.get("beds"), f.get("baths") or row.get("baths"), sqft, typ, town,
                          row.get("lat") or r.get("lat"), row.get("lon") or r.get("lon"), pid)
    sold_res = listings.fetch_sold(town, allow_call=town in (ss.get("sold_load") or set())) if listings.available() else {"ok": False, "rows": []}
    sold_rows = sold_res.get("rows") or []
    active = listings.all_cached_rows("for_sale")
    res = ARV.analyze(subj, sold_rows, active)
    for grp in ("sold", "ask"):
        if res.get(grp):
            for c in res[grp]["bld"][:4] + res[grp]["near"][:6]:
                dc = listings.detail_cached(str(c.get("id"))) if (grp == "ask" and c.get("id")) else None
                c["_cues"] = ARV.cue_keys((dc or {}).get("text"))
    head = L("🛠️ If I fix it up", "🛠️ Si la arreglo")
    body = ""
    comps = []

    def _arv_tok(c, sold_, acc):
        acc.append((c, sold_))
        return _ARV_TOK % (len(acc) - 1)
    basis = res["basis"]
    ppsf = res["use_ppsf"]
    sub_ = L("What nicer, fixed-up units cost in this building and nearby, to guess what this one could sell for after repairs.",
             "Lo que cuestan unidades más bonitas y arregladas en este edificio y cerca, para calcular en cuánto podría venderse esta después de arreglarla.")
    body += f"<div class='sub'>{H.escape(sub_)}</div>"
    if basis:
        gx = res[basis]
        st_ = gx["stats"]
        if basis == "sold":
            since = gx.get("since")
            pill = L(f"✔ Based on sold prices: real sales in the last 12 months{' (since ' + since[:7] + ')' if since else ''}", f"✔ Basado en precios de venta reales de los últimos 12 meses{' (desde ' + since[:7] + ')' if since else ''}")
            body += f"<span class='pill s'>{H.escape(pill)}</span>"
        else:
            body += "<span class='pill a'>" + H.escape(L("⚠ Based on ASKING prices of homes listed now, not sold prices. Asking prices run higher than what homes sell for.",
                                                         "⚠ Basado en PRECIOS PEDIDOS de casas publicadas ahora, no en precios de venta. Los precios pedidos suelen ser más altos que lo que se paga.")) + "</span>"
        rad = gx["radius"]
        rl = L("in the town", "en el pueblo") if rad == "town" else L(f"within {rad:g} mi", f"a menos de {rad:g} mi")
        unit = L("price per sq ft", "precio por pie²") if ppsf else L("price (no size listed for this home)", "precio (esta casa no tiene tamaño)")
        body += (f"<div class='sub' style='margin-top:.4rem'>{H.escape(L(f'{st_['n']} similar homes {rl}' + (f', {len(gx['bld'])} in this building' if gx['bld'] else ''), f'{st_['n']} casas parecidas {rl}' + (f', {len(gx['bld'])} en este edificio' if gx['bld'] else '')))}. "
                 f"{H.escape(L('Top quarter by ', 'El cuarto más alto por '))}{H.escape(unit)}: {H.escape(L(str(st_['top_n']) + ' homes', str(st_['top_n']) + ' casas'))}.</div>")
        cells = [(money(st_["p75"]) + "/ft²" if ppsf else money(st_["p75"]), L("top-quarter starts at", "el cuarto más alto empieza en")),
                 (money(st_["med_top"]) + "/ft²" if ppsf else money(st_["med_top"]), L("typical of the top quarter", "típico del cuarto más alto"))]
        body += "<div class='big'>" + "".join(f"<div><span>{H.escape(b)}</span><b>{H.escape(a)}</b></div>" for a, b in cells) + "</div>"
        p = price
        sp = res["spread"]
        sq = f"{int(sqft):,} ft²" if ppsf else L("no size", "sin tamaño")
        body += ("<div class='big'>"
                 f"<div><span>{L('Estimated after-repair value', 'Valor estimado después de reparar')}</span><b>{money(res['mid'])}</b>"
                 f"<div class='sm'>{L('range', 'rango')} {money(res['low'])} – {money(res['high'])}" + (f" · {sq}" if ppsf else "") + "</div></div>"
                 f"<div><span>{L('Asking price now', 'Precio pedido ahora')}</span><b>{money(p)}</b>"
                 f"<div class='sm'>{L('gap before repair costs', 'diferencia antes de costos de reparación')}: <b style='font-size:.85rem'>{'+' if sp >= 0 else '−'}{money(abs(sp))}</b>"
                 f" ({'+' if res['spread_lo'] >= 0 else '−'}{money(abs(res['spread_lo']))} {L('to', 'a')} {'+' if res['spread_hi'] >= 0 else '−'}{money(abs(res['spread_hi']))})</div></div></div>")
        if p and sp > 0.4 * p:
            body += "<div class='cav'>" + H.escape(L("The asking price is far below what similar homes sold for. Find out why before trusting the gap: a co-op with board rules, a lease, a shared or unfinished unit, a small unit, or big hidden repairs can all explain it.",
                                                       "El precio pedido está muy por debajo de lo que se vendieron casas parecidas. Averigüe por qué antes de confiar en la diferencia: una co-op con reglas de la junta, un contrato de alquiler, una unidad compartida o sin terminar, una unidad pequeña o reparaciones grandes ocultas pueden explicarlo.")) + "</div>"
        if sp < 0.05 * p:
            body += "<div class='cav'>" + H.escape(L("The top-quarter comps are about the same as (or below) this home's asking price, so there may be little room to add value here.",
                                                       "Los comparables del cuarto más alto están cerca (o por debajo) del precio pedido, así que quizá hay poco margen para agregar valor.")) + "</div>"
        grp_sold = basis == "sold"
        if gx["bld"]:
            body += f"<div class='g'>{H.escape(L('Same building', 'Mismo edificio') + ' · ' + (L('sold', 'vendidas') if grp_sold else L('asking', 'precios pedidos')))}</div>"
            body += "".join(_arv_tok(c, grp_sold, comps) for c in gx["bld"][:4])
        else:
            body += f"<div class='g'>{H.escape(L('Same building', 'Mismo edificio'))}</div><div class='sub'>{H.escape(L('None found in this building in the saved data.', 'No se encontró ninguna en este edificio en los datos guardados.'))}</div>"
        body += f"<div class='g'>{H.escape(L('Nearby, highest first', 'Cerca, de mayor a menor') + ' · ' + (L('sold', 'vendidas') if grp_sold else L('asking', 'precios pedidos')))}</div>"
        body += "".join(_arv_tok(c, grp_sold, comps) for c in gx["near"][:5])
        if grp_sold and (res.get("ask") or {}).get("bld"):
            body += f"<div class='g'>{H.escape(L('Listed now in this building · asking, not sold', 'Publicadas ahora en este edificio · precio pedido, no vendidas'))}</div>"
            body += "".join(_arv_tok(c, False, comps) for c in res["ask"]["bld"][:3])
        if gx.get("far"):
            body += "<div class='sub'>" + H.escape(L(f"Left out {gx['far']} much pricier homes (new luxury buildings) that don't say much about this one.",
                                                    f"Se dejaron fuera {gx['far']} casas mucho más caras (edificios nuevos de lujo) que dicen poco de esta.")) + "</div>"
        srcs = [L("Sold prices: realtor.com via Realty in US (sold list)", "Precios de venta: realtor.com vía Realty in US (lista de vendidas)") if grp_sold else "",
                L("Asking prices: realtor.com via Realty in US (saved lists)", "Precios pedidos: realtor.com vía Realty in US (listas guardadas)") if (not grp_sold or (res.get('ask') or {}).get('bld')) else ""]
        body += f"<div class='src'>{L('Sources', 'Fuentes')}: {H.escape('; '.join(x for x in srcs if x))}. " + \
                H.escape(L("Condition words come from listing descriptions we have saved; sold comps have none, so “nicer” means a higher price per sq ft.",
                           "Las palabras sobre el estado vienen de las descripciones guardadas; las ventas no tienen, así que “más bonita” significa mayor precio por pie².")) + "</div>"
    else:
        need = town not in (ss.get("sold_load") or set()) and not listings.sold_cached(town) and listings.available()
        body += "<div class='sub' style='margin-top:.4rem'>" + H.escape(L("Not enough similar homes with a price per sq ft to estimate a value yet.", "Aún no hay suficientes casas parecidas para estimar un valor.")) + "</div>"
        if need:
            body += "<div class='sub'>" + H.escape(L("Recent sales in this town are not loaded yet.", "Las ventas recientes de este pueblo aún no se cargaron.")) + "</div>"
    own_cues = ARV.cue_keys(text)
    if own_cues:
        body += ("<div class='sub' style='margin-top:.45rem'>" + H.escape(L("This listing's own description mentions: ", "La descripción de este anuncio menciona: "))
                 + H.escape(", ".join(ARV.cue_labels(own_cues, ES()))) + ".</div>")
    with st.container(key=f"arvbox_{sid}"):
        segs = re.split("\x00COMP(\\d+)\x00", f"<div class='h'>{head}</div>{body}")
        for j, seg in enumerate(segs):
            if j % 2 == 0:
                if seg:
                    html(f"<div class='bz-rc plain'>{seg}</div>")
            else:
                c_, sold_ = comps[int(seg)]
                html(f"<div class='bz-rc plain'>{_arv_row(c_, sold_)}</div>")
                _arv_comps_render(c_, sold_, sid, seg, pid, addr)
    if listings.available() and town not in (ss.get("sold_load") or set()) and not listings.sold_cached(town) and basis != "sold":
        st.button(L(f"🔎 Load recent sales in {town} (1 lookup, kept 30 days)", f"🔎 Cargar ventas recientes en {town} (1 consulta, se guarda 30 días)"),
                  key=f"sold_{sid}", width="stretch", on_click=_load_sold, args=(town,))
    if basis and price:
        c1, c2 = st.columns(2)
        with c1:
            rehab = st.number_input(L("Fix-up budget ($)", "Presupuesto de arreglos ($)"), 0, 2_000_000, step=5_000, key=f"arv_rehab_{sid}")
        with c2:
            sc = st.number_input(L("Selling costs (%)", "Costos de venta (%)"), 0.0, 15.0, value=ARV.SELL_COST * 100, step=0.5, key=f"arv_sell_{sid}")
        rows_ = [(L("low", "bajo"), res["low"]), (L("middle", "medio"), res["mid"]), (L("high", "alto"), res["high"])]
        pv_ = [(n, ARV.profit(v, price, rehab, sc / 100)) for n, v in rows_]
        cells = "".join(f"<div><span>{H.escape(n)}</span><b>{'+' if x >= 0 else '−'}{money(abs(x))}</b></div>" for n, x in pv_)
        html(f"<div class='bz-rc'><div class='sub'>{H.escape(L(f'Rough profit if it sells at the ARV: sale price − {sc:g}% selling costs − what you pay ({money(price)}) − your fix-up budget ({money(rehab)}).', f'Ganancia aproximada si se vende al valor estimado: precio de venta − {sc:g}% de costos de venta − lo que paga ({money(price)}) − su presupuesto de arreglos ({money(rehab)}).'))}</div>"
             f"<div class='st' style='grid-template-columns:1fr 1fr 1fr'>{cells}</div></div>")
    st.caption(L("⚠ A rough estimate, not an appraisal. It leaves out the fix-up cost (unless you enter it), closing costs to buy, HOA and taxes while you hold it, loan interest, and how long it takes. Ask an agent and a contractor before you count on it.",
                 "⚠ Un estimado aproximado, no un avalúo. No incluye el costo de arreglos (salvo que lo ingrese), gastos de cierre al comprar, HOA e impuestos mientras la tiene, intereses del préstamo ni cuánto tarda. Pregunte a un agente y a un contratista antes de confiar en él."))


def _est_lbl(b, lv):
    """'(2 bd, town typical from 14 listings)' — or HUD's fair rent when too few current listings."""
    n = int((lv or {}).get("n") or 0)
    if (lv or {}).get("hud"):
        few = L(f", only {n} listing{'s' if n != 1 else ''} now", f", solo {n} anuncio{'s' if n != 1 else ''} ahora") if n else ""
        return L(f"({b} bd, HUD fair rent{few})", f"({b} hab, renta justa de HUD{few})")
    if (lv or {}).get("skewed"):
        return L(f"({b} bd, older unit: between HUD's fair rent and the cheaper of {n} listings, mostly new buildings)",
                 f"({b} hab, unidad más antigua: entre la renta justa de HUD y los más baratos de {n} anuncios, casi todos edificios nuevos)")
    return L(f"({b} bd, town typical from {n} listings)", f"({b} hab, típico del pueblo según {n} anuncios)") if n else \
        L(f"({b} bd, town typical)", f"({b} hab, típico del pueblo)")


def _town_comps(a, sid, size, out):
    ss = st.session_state
    two = size == "2fam"
    b = int(ss.get(f"ub_{sid}_mf") or 2) if two else int(size)
    bb = {int(k): v for k, v in (a.get("by_beds") or {}).items()}
    u = bb.get(min(b, 3)) or {}
    lv = (C._unit_levels(u) or {}) if u else {}
    est = lv.get("typ") if lv else None
    rules = a.get("str_rules") or {}
    rent_comps_box("t_" + sid, a.get("town"), b, None, a.get("lat"), a.get("lon"), est, _est_lbl(b, lv) if est else None,
                   u.get("hud"), None, rules, u.get("str"), u.get("mtr"),
                   air_ok=(out or {}).get("airbnb_allowed", C.airbnb_ok(rules, "multi-family" if two else "single-family", "unit" if two else "room")))


def _hud_for(town, beds):
    try:
        from bellazu.sources import hud as _hud
        z = (C.town_info(town) or {}).get("zip")
        return (_hud.safmr(z) or {}).get(f"{min(max(int(beds), 0), 4)}br") if z and beds is not None else None
    except Exception:
        return None


def _num_g(v):
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


@timed('property_view')
def prop_hoa(r, addr):
    """The fee to show for an opened home: what the user typed, else what the listing gave (or its labeled estimate), else from the check."""
    fo = facts_for(addr)
    f = r.get("facts") or {}
    own = (f.get("ownership") or "").lower()
    lab = "maintenance" if "co-op" in own else "hoa"
    if fo.get("hoa_src") == "user":
        return {"state": "real" if fo.get("hoa") else "none", "fee": int(fo.get("hoa") or 0), "label": lab, "src": "user input",
                "inc": includes_engine(fo.get("inc")) if fo.get("inc") is not None else []}
    hi = fo.get("hoa_info")
    if hi and fo.get("hoa_src") in ("real", "est", "none") and int(fo.get("hoa") or 0) == int(hi.get("fee") or 0):
        return hi
    v = f.get("hoa_monthly")
    if v:
        return {"state": "real", "fee": int(v), "label": lab, "src": (r.get("fact_sources") or {}).get("hoa_monthly") or "listing", "inc": f.get("hoa_includes") or []}
    if "single" in own or "multi" in own:
        return {"state": "none", "fee": 0, "label": "hoa", "src": "typical for houses", "inc": []}
    return {"state": "unknown", "fee": None, "label": lab, "src": None, "inc": f.get("hoa_includes") or []} if own else None


def loan_breakdown(c, ln, hi, f, r, own, apm):
    """P&I + PMI/MIP + tax + insurance + HOA with My loan, the approved payment, and the cash to close."""
    lp = loan_prof()
    fha = ln.get("kind") == "fha"
    inc = [x.lower() for x in (f.get("hoa_includes") or [])]
    tsrc = (r.get("fact_sources") or {}).get("taxes_annual")
    if tsrc == "user input" and f.get("taxes_annual") and facts_for(st.session_state.get("prop_addr", r["address"])).get("taxes_listing") == int(f["taxes_annual"]):
        tsrc = "listing"                          # the listing's tax figure is passed in like a user fact; label it by where it came from
    if "taxes" in inc:
        tx = L("included in the maintenance (co-op)", "incluidos en el mantenimiento (co-op)")
    elif f.get("taxes_annual"):
        tx = L(f"{money(f['taxes_annual'])}/yr from ", f"{money(f['taxes_annual'])}/año ") + (L("what you entered", "de lo que usted ingresó") if tsrc == "user input" else
                                                                                               L("the home's tax record", "del registro de impuestos de la casa"))
    else:
        tx = L(f"the lender's {money(lp['tax_y'])}/yr (this home's tax bill is unknown)", f"los {money(lp['tax_y'])}/año del banco (no se sabe la factura de esta casa)")
    mi = int(c.get("mortgage_insurance") or 0)
    rows = [(L("Principal and interest", "Capital e intereses"), c.get("principal_interest"),
             L(f"loan {money(ln.get('loan_amount'))}, {rate_lbl()}, {lp['term']} years", f"préstamo {money(ln.get('loan_amount'))}, {rate_lbl()}, {lp['term']} años")),
            ((L("FHA mortgage insurance", "Seguro hipotecario FHA") if fha else L("PMI (est.)", "PMI (est.)")), mi,
             (L("0.55%/yr; the 1.75% upfront fee is added to the loan", "0.55%/año; la cuota inicial de 1.75% se suma al préstamo") if fha else
              (L(f"about {lp['pmi_pct'] * 100:.2f}%/yr of the loan until you reach 20% equity", f"cerca de {lp['pmi_pct'] * 100:.2f}%/año del préstamo hasta tener 20% de valor") if mi else
               L("none: 20% or more down", "ninguno: 20% o más de inicial")))),
            (L("Property tax", "Impuestos a la propiedad"), c.get("property_tax"), tx),
            (L("Home insurance", "Seguro de la casa"), c.get("insurance"),
             L("the lender's figure", "la cifra del banco") + (L("; for a condo or co-op an HO-6 policy is often cheaper", "; para un condo o co-op una póliza HO-6 suele costar menos")
                                                              if ("condo" in own or "co-op" in own) else "")),
            ((L("Maintenance", "Mantenimiento") if (hi or {}).get("label") == "maintenance" else L("HOA / building fee", "HOA / cuota del edificio")), c.get("hoa_or_maintenance"),
             (hoa_txt(hi) + " · " + hoa_src_txt(hi)) if hi else "")]
    tot = sum(int(x[1] or 0) for x in rows)
    mxs = kmoney(lp["max_price"])
    apd = money(apm["loan"]["down_payment"])
    apk, apk_es = ("FHA", "FHA") if lp["kind"] == "fha" else ("Conventional", "Convencional")
    body = "".join(f"<tr><td>{H.escape(a)}<span class='x'>{H.escape(str(sub))}</span></td><td class='n'>{money(v or 0)}</td></tr>" for a, v, sub in rows)
    body += f"<tr class='t'><td>{L('Total a month', 'Total al mes')}</td><td class='n'>{money(tot)}</td></tr>"
    body += (f"<tr><td>{L('Your approved monthly payment', 'Su pago mensual aprobado')}<span class='x'>"
             f"{H.escape(L(f'{apk} at {mxs}, {apd} down, with the lender’s taxes and insurance, no HOA', f'{apk_es} a {mxs}, {apd} de inicial, con los impuestos y seguro del banco, sin HOA'))}</span></td>"
             f"<td class='n'>{money(apm['total'])}</td></tr>")
    html(f"<table class='bz-bd'>{body}</table>")
    if hoa_extra_note(hi):
        cap(hoa_extra_note(hi))
    md(L(f"**Cash to close (est.):** {money(ln.get('down_payment'))} down ({(ln.get('down_pct') or 0) * 100:.1f}%) + about {money(ln.get('closing_costs_est'))} closing costs "
         f"({lp['closing_pct'] * 100:.1f}%, NJ/NY usually 3-4%) = **{money(ln.get('cash_to_close_est'))}**.",
         f"**Efectivo para cerrar (est.):** {money(ln.get('down_payment'))} de inicial ({(ln.get('down_pct') or 0) * 100:.1f}%) + unos {money(ln.get('closing_costs_est'))} de gastos de cierre "
         f"({lp['closing_pct'] * 100:.1f}%, en NJ/NY suele ser 3-4%) = **{money(ln.get('cash_to_close_est'))}**."))
    st.caption(L("Change the loan in ⚙️ My settings. 'What you'd pay each month' below also counts utilities and a repairs reserve, and what a roommate or tenant brings in.",
                 "Cambie el préstamo en ⚙️ Mis ajustes. 'Lo que pagaría cada mes' abajo también cuenta servicios y una reserva para arreglos, y lo que aporta un compañero o inquilino."))


def show_property(r):
    ss = st.session_state
    f = r.get("facts") or {}
    own = (f.get("ownership") or "").lower()
    sc = S.scenarios(r)
    o = sc.get("owner_roommates")
    rent, rent_src = S.rent_used(r)
    sid = safe_name(ss.get("prop_addr", r["address"]))[:30]
    first = ss.get("hmode", "first") == "first"
    ex = r.get("extra") or {}
    # 1) the essentials first: photo, address, price, beds/baths, heart, then three numbers. Everything else is tucked into tap-to-open sections.
    arv_back_button(ss.get("prop_addr", r["address"]))
    gallery_block(ss.get("prop_addr", r["address"]))
    html(f"<div class='bz-addr'>📍 {H.escape(r['address'])}</div>")
    if f.get("price"):
        fl_ = " · ".join(x for x in [f"{f['beds']} {L('bd', 'hab')}" if f.get("beds") is not None else "", f"{_num_g(f['baths'])} {L('ba', 'baño' if float(f['baths']) == 1 else 'baños')}" if f.get("baths") else ""] if x)
        html(f"<div class='bz-price'>{money(f['price'])}" + (f"<span class='f'>{H.escape(fl_)}</span>" if fl_ else "") + "</div>")
    p_addr = ss.get("prop_addr", r["address"])
    hi_p = prop_hoa(r, p_addr)
    if hi_p:
        html(f"<div class='bz-3n' style='margin:.1rem 0 .5rem'>{H.escape(hoa_txt(hi_p))}</div>")
        if hoa_extra_note(hi_p):
            html(f"<div class='bz-3n' style='margin:-.3rem 0 .5rem'>{H.escape(hoa_extra_note(hi_p))}</div>")
    lid = ((ss.get("gallery") or {}).get(p_addr.strip().lower()) or {}).get("id")
    sv_iid = find_home(p_addr, lid) or (saves.item_id("listing", lid) if lid else saves.item_id("address", p_addr))
    ss["_sv_stash_prop"] = (r, None, first, p_addr)
    heart(sv_iid, f"p_{_sv_key(sv_iid)}", _from_stash, ("prop",), wide=True)
    summ = st.container()                     # filled once the numbers below are worked out
    lvl_, _c = C.town_caution(r.get("town"))
    if lvl_ == "exclude":
        safety_note(r.get("town"))
    am = ss.setdefault("addr_meta", {}).setdefault(p_addr.strip().lower(), {})
    am.update(town=r.get("town"), zip=r.get("zip") or am.get("zip"))
    if not facts_for(p_addr).get("type") and ui_type_of(r):
        am["type"] = ui_type_of(r)
    fa = fha_for_addr(p_addr, r)
    base = C.base_from_property(r)
    star = None
    if base:        # the verdict speaks about the same option the compare view stars (read the tap from last run, else the default)
        try:
            d0 = C.default_sel(base)
            pt = "mf" if base["ptype"] == "multi-family" else "sf"
            ro0 = ss.get(f"ro_{sid}_{pt}") or d0["rent_out"]
            if ro0 != "none":
                s0 = dict(d0, rent_out=ro0, unit_beds=ss.get(f"ub_{sid}_{pt}") or d0["unit_beds"])
                c1 = C.compare(base, s0)["cols"][1]
                star = {"pay": c1["pay"], "what": ("the other unit rented", "la otra unidad alquilada") if ro0 == "unit" else
                        (("1 roommate", "1 compañero") if c1.get("n", 1) == 1 else (f"{c1['n']} roommates", f"{c1['n']} compañeros"))}
        except Exception:
            star = None
    ask_missing(r)
    v = S.verdict_property(r, star)
    vbig = {"good": L("Good deal", "Buen negocio"), "maybe": L("Maybe", "Tal vez"), "skip": L("Skip this one", "Mejor no")}.get(v["level"], "")
    with st.expander(L(f"Our take: {vbig}", f"Nuestra opinión: {vbig}"), key=f"pv_{sid}"):
        verdict_box(v)
    if base:
        ln = o["loan"]
        conv = ln.get("kind") == "conv"
        with st.expander(L("What you'd pay each month", "Lo que pagaría cada mes"), key=f"pp_{sid}"):
            sel = sel_for(sid, base)
            out = C.compare(base, sel)
            compare_strip(out, first, L("my loan, ", "mi préstamo, ") + loan_kind_lbl(ln))
            skew_note(base, sel)
            lk = L("normal loan", "préstamo normal") if conv else "FHA"
            md(L(f"Same loan in every column: {lk} {ln['rate_pct']:.2f}%, {money(ln['down_payment'])} down + about {money(ln['closing_costs_est'])} fees = **{money(ln['cash_to_close_est'])} to close**.",
                 f"Mismo préstamo en cada columna: {lk} {ln['rate_pct']:.2f}%, {money(ln['down_payment'])} inicial + unos {money(ln['closing_costs_est'])} de cierre = **{money(ln['cash_to_close_est'])} para cerrar**."))
            q = out.get("qualify")
            if q:
                md(L(f"🏦 A lender can count about **{money(q['counted'])}/mo** ({q['share']:.0%} of the other unit's fair rent) as your income. Roommate rent doesn't count.",
                     f"🏦 El banco puede contar unos **{money(q['counted'])}/mes** ({q['share']:.0%} de la renta justa de la otra unidad) como su ingreso. La renta de compañeros no cuenta."))
                if q.get("self_sufficiency"):
                    ssf = q["self_sufficiency"]
                    md(L(f"3-4 family check: the rents must cover the mortgage payment ({money(ssf['piti'])}) after a 25% cut: about {money(ssf['net_rent_all'])} → {'passes ✓' if ssf['passes'] else 'fails ✗'}.",
                         f"Prueba de 3-4 familias: las rentas deben cubrir el pago ({money(ssf['piti'])}) tras un recorte del 25%: unos {money(ssf['net_rent_all'])} → {'pasa ✓' if ssf['passes'] else 'no pasa ✗'}."))
            elif sel["rent_out"] == "room":
                st.caption(L("Lenders don't count roommate rent when you apply. It still lowers what you pay each month.",
                             "Los bancos no cuentan la renta de compañeros al aplicar. Aun así baja lo que paga cada mes."))
            best = out["cols"][2].get("best")
            if best and best.get("cap"):
                st.caption(L(f"Airbnb here is capped at {best['cap']} nights a year, so we counted at most that.", f"Airbnb aquí tiene un tope de {best['cap']} noches al año; contamos como máximo eso."))
            if best and best.get("capped"):
                st.caption(L("30+ day rate capped at 1.5× normal rent (a safety limit).", "Tarifa de 30+ días limitada a 1.5× la renta normal (límite de seguridad)."))
            ranges_block(sid, out)
        ub = sel.get("unit_beds", 2)
        ref = ((base.get("units") or {}).get(ub) or {}).get("ltr", {}) if own == "multi-family" else None
        rent_ref = (ref or {}).get("typ") if own == "multi-family" else rent
        with st.expander(L("What similar places rent for", "Lo que se alquila algo parecido"), key=f"prc_{sid}"):
            _prop_comps(r, sel, base, own, rent, sid)
        with st.expander(L("Cash in, cash out", "Dinero que entra y sale"), key=f"pcc_{sid}"):
            cash_card(sid, out, rent_ref)
    with st.expander(L("If I fix it up (after-repair value)", "Si la arreglo (valor después de reparar)"), key=f"parv_{sid}"):
        try:
            arv_section(r, sid, p_addr)
        except Exception:
            st.caption(L("Couldn't work out the after-repair value for this home right now.", "No se pudo calcular el valor después de reparar para esta casa ahora."))
    with st.expander(L("FHA and your loan", "FHA y su préstamo"), key=f"pfha_{sid}"):
        if fa:
            fha_card(fa, "p_" + sid, inline=True)
        else:
            fha_explainer("p_" + sid, inline=True)
    with st.expander(L("Drive and town rules", "Viaje y reglas del pueblo"), key=f"pdr_{sid}"):
        drive_badge(ex.get("drive"))
        if lvl_ != "exclude":
            safety_note(r.get("town"))
        rules_card(r.get("str_rules") or {}, r.get("town"))
    if base:
        ok_air = out.get("airbnb_allowed")
        with st.expander(L("Similar places nearby", "Lugares parecidos cerca"), key=f"ppl_{sid}"):
            places_block(lists_for_property(r, sel), r.get("str_rules") or {}, r.get("town"), (r.get("str") or {}).get("datasets") or [], ok_air, out.get("days30", 30), head=False)
        with st.expander(L("Busy vs slow months", "Meses de mucho y poco movimiento"), key=f"pss_{sid}"):
            season_block(C.seasonality((r.get("str") or {}).get("datasets")), r.get("town"), head=False)
        # the three numbers, shown right under the price: My loan's real monthly cost, the rent, the cash to close
        c_ = o.get("costs") or {}
        mtot = sum(int(c_.get(k) or 0) for k in ("principal_interest", "mortgage_insurance", "property_tax", "insurance", "hoa_or_maintenance"))
        apm = approved_monthly()
        tg = ML.tag(f.get("price"), mtot, loan_prof(), apm["total"])
        cells = [(money(mtot), L("a month with my loan (with HOA, taxes, insurance)", "al mes con mi préstamo (con HOA, impuestos, seguro)")),
                 (money(rent_ref) if rent_ref else "—",
                  L("a month the other unit could rent for", "al mes podría rentar la otra unidad") if own == "multi-family" else L("a month it could rent for", "al mes podría rentarse")),
                 (money(ln.get("cash_to_close_est")), L("cash needed to close (est.)", "efectivo para cerrar (est.)"))]
        tt, tc = tag_txt(tg)
        ff_ = fha_flag(fa)
        long_ = {"ok": L(f"Within your approval: price up to {kmoney(loan_prof()['max_price'])} and {money(mtot)}/mo is at or under your approved {money(apm['total'])}/mo.",
                         f"Dentro de su aprobación: precio hasta {kmoney(loan_prof()['max_price'])} y {money(mtot)}/mes es igual o menor a su aprobado de {money(apm['total'])}/mes."),
                 "monthly": L(f"Price OK, but {money(mtot)}/mo is higher than the {money(apm['total'])}/mo you were approved for. The HOA and taxes may push you over: ask your lender.",
                              f"Precio OK, pero {money(mtot)}/mes es más que los {money(apm['total'])}/mes aprobados. La HOA y los impuestos pueden pasarla del límite: pregunte a su banco."),
                 "over": L(f"Over your {kmoney(loan_prof()['max_price'])} approval.", f"Sobre su aprobación de {kmoney(loan_prof()['max_price'])}.")}.get(tg, "")
        with summ:
            html("<div class='bz-3'>" + "".join(f"<div><b>{H.escape(str(n))}</b><span>{H.escape(t)}</span></div>" for n, t in cells) + "</div>"
                 + (f"<div class='bz-tag {tc}'>{H.escape(tt)}</div><div class='bz-3n'>{H.escape(long_)}</div>" if tg else "")
                 + (f"<div class='bz-tag r'>{H.escape(L(*FHA_FLAG[ff_]))}</div><div class='bz-3n'>{H.escape(FHA_LONG(ff_))}</div>" if ff_ else
                    f"<div class='bz-3n'>{H.escape(L(*COOP_LONG))}</div>" if (fa or {}).get("code") == "coop" else "")
                 + f"<div class='bz-3n'>{H.escape(L(f'My loan: {loan_kind_lbl(ln)}, {rate_lbl()}. Tap a section below for the details.', f'Mi préstamo: {loan_kind_lbl(ln)}, {rate_lbl()}. Toque una sección abajo para ver los detalles.'))}</div>")
            with st.expander(L("Monthly cost with my loan", "Costo mensual con mi préstamo"), key=f"pml_{sid}"):
                loan_breakdown(c_, ln, hi_p, f, r, own, apm)
        cv = report_cv(out, ex.get("drive"), first)
        ss["_sv_stash_prop"] = (r, out, first, p_addr)
        old = sv()["items"].get(sv_iid)
        if old and old.get("nums_src") == "town":      # saved from a feed card: swap the quick town estimate for the full check
            e = entry_from_property(sv_iid, r, out, first, p_addr)
            e.update({k: old[k] for k in ("saved", "saved_ms", "status", "note") if k in old})
            e["photos"] = e.get("photos") or old.get("photos") or []
            e["photo"] = e.get("photo") or old.get("photo")
            e["url"] = e.get("url") or old.get("url")
            sv()["items"][sv_iid] = e
            _sv_touch()
    else:
        cv = None
    ss.prop_cv = cv
    fix_facts(r)
    st.download_button(L("⬇️ Download your full report", "⬇️ Descargar su reporte completo"), lambda r=r, lg_=("es" if ES() else "en"), cv=cv: property_html(r, lg_, cv=cv).encode(),
                       L(f"BellaZu_Report_{safe_name(r['address'])}.html", f"BellaZu_Reporte_{safe_name(r['address'])}.html"), "text/html", key="dl_prop", type="primary", width="stretch", on_click="ignore")
    with st.expander(L("See details and words to know", "Ver detalles y palabras clave")):
        property_details(r, f, sc, o, rent, rent_src, own)


# ------------------------------------------------------------------ town view (same layout)
@timed('run_town')
def run_town(name, where):
    ss = st.session_state
    tn = towns.normalize(name)
    key = (tn["name"] or name).lower()
    cache = ss.setdefault("town_cache", {})
    if key in cache:
        ss.town = cache[key]
        return
    with where, st.spinner(L("Looking at the town for you... about 20 to 40 seconds ✨", "Revisando el pueblo por usted... unos 20 a 40 segundos ✨")):
        fj = _feed_jobs([tn["name"]], "for_sale") if tn.get("name") and tn.get("match") in ("exact", "alias", "fuzzy") else []
        res = _parallel([("snap", lambda: town_snap(name))] + fj)       # the homes list loads at the same time
        a = res.get("snap")
        if not isinstance(a, dict):
            a = {"ok": False, "error": a.__class__.__name__, "town_input": name, "town_suggestions": tn["suggestions"]}
        for k, r in res.items():
            if k != "snap":
                r = r if isinstance(r, dict) else {"ok": False, "error": r.__class__.__name__, "rows": []}
                if not r.get("ok"):          # a failed search isn't asked again on every tap (it would spend a search each time)
                    ss.setdefault("_feed_pre", {})[(k[1], k[2])] = r
    if a.get("ok"):
        cache[key] = a
    ss.town = a


def safety_note(town):
    lvl, c = C.town_caution(town)
    if c:
        html(f"<div class='bz-warn{' hi' if lvl == 'exclude' else ''}'>{'⚠️' if lvl == 'exclude' else 'ℹ️'} {H.escape(P(c))}</div>")


@st.fragment
@timed("town_price")
def _town_price_block(a, sid, first):
    """Price / size / what-you-rent-out chips and the monthly numbers. A price tap redraws only this part (a fragment).
    If a tap changes something the rest of the page shows (size, what you rent out, the Airbnb answer), the whole page redraws."""
    ss = st.session_state
    if ss.get("_full"):
        st.rerun(scope="app")
    t = a["town"]
    st.markdown(f"<div class='bz-lbl'>{L('Tap a price you are looking at', 'Toque un precio que esté mirando')}</div>", unsafe_allow_html=True)
    price = st.pills(L("Price", "Precio"), C.PRICE_CHIPS + ["other"], key=f"tp_{sid}", label_visibility="collapsed",
                     format_func=lambda p: L("Other", "Otro") if p == "other" else kmoney(p))
    if price == "other":
        price = st.number_input(L("Price ($)", "Precio ($)"), min_value=50_000, max_value=3_000_000, step=10_000, value=int(ss.get(f"tpo_{sid}") or 350_000), key=f"tpo_{sid}")
    size = st.segmented_control(L("Size", "Tamaño"), C.TOWN_SIZES, key=f"ts_{sid}", default="2fam" if first else "2", required=True, width="stretch",
                                format_func=lambda s_: L("2-family", "2 familias") if s_ == "2fam" else f"{s_} {L('bd', 'hab')}")
    out, cv = None, None
    if not price:
        html(f"<div class='bz-ask'>👆 {L('Tap a price to see what you would pay each month here. We never guess a home value for you.', 'Toque un precio para ver lo que pagaría al mes aquí. Nunca inventamos el valor de una casa.')}</div>")
    else:
        base = C.base_from_town(a, int(price), size, loan=loan_prof())
        sel = sel_for(sid, base)
        out = C.compare(base, sel)
        compare_strip(out, first)
        ss["_sv_stash_town"] = (a, int(price), size, out, first)
        t_iid = saves.item_id("town", f"{t}|{int(price)}|{size}")
        heart(t_iid, f"t_{_sv_key(t_iid)}", _from_stash, ("town",), wide=True)
        skew_note(base, sel)
        ln = base["loan"]
        tx = (L(f"Taxes use {t}'s typical rate, {base['tax_rate']:.2%} of the price (NJ Treasury 2025 average bill ÷ average sale price)", f"Los impuestos usan la tasa típica de {t}, {base['tax_rate']:.2%} del precio (Tesoro de NJ 2025: factura promedio ÷ precio promedio)")
              if not base.get("tax_fallback") else L(f"Taxes use a {base['tax_rate']:.1%} estimate", f"Los impuestos usan un estimado de {base['tax_rate']:.1%}"))
        md(L(f"At {money(price)} with my loan ({loan_kind_lbl(ln)}, {rate_lbl()}): {money(ln['cash_to_close_est'])} to close (est.). {tx}; add any HOA fee on top.",
             f"A {money(price)} con mi préstamo ({loan_kind_lbl(ln)}, {rate_lbl()}): {money(ln['cash_to_close_est'])} para cerrar (est.). {tx}; sume cualquier cuota HOA."))
        q = out.get("qualify")
        if q:
            md(L(f"🏦 A lender can count about **{money(q['counted'])}/mo** of the other unit's rent (75%).", f"🏦 El banco puede contar unos **{money(q['counted'])}/mes** de la renta de la otra unidad (75%)."))
        ranges_block(sid, out)
        ub = sel.get("unit_beds", 2)
        ref = (base["units"].get(ub) or {}).get("ltr") if size == "2fam" else (base["units"].get(int(size)) or {}).get("ltr") if size in ("1", "2", "3") else None
        cash_card(sid, out, (ref or {}).get("typ"))
        cv = report_cv(out, a.get("drive"), first, [(f"Price you picked: {money(price)} · size: {size}", f"Precio elegido: {money(price)} · tamaño: {size}")])
    hold = ss.setdefault(f"_tph_{sid}", {})
    hold["cv"] = cv                              # the report buttons read the latest numbers from here when tapped
    ro_ = (out or {}).get("rent_out")
    sig = (size, ro_, ss.get(f"ub_{sid}_mf"), bool(out), (out or {}).get("airbnb_allowed"))
    prev = hold.get("sig")
    hold.update(size=size, out=out, sig=sig)
    if prev is not None and prev != sig and not hold.pop("full_run", False):
        st.rerun(scope="app")
    hold.pop("full_run", None)


@timed('town_view')
def show_town_view(a):
    ss = st.session_state
    first = ss.get("hmode", "first") == "first"
    t = a["town"]
    sid = "t_" + safe_name(t)[:24]
    if a.get("town_match") in ("alias", "fuzzy") and a.get("town_input"):
        st.caption(L(f"Showing {t} (you typed “{a['town_input']}”).", f"Mostrando {t} (usted escribió “{a['town_input']}”)."))
    html(f"<div class='bz-hello'>{H.escape(t)}</div>")
    drive_line(a.get("drive"))
    sr = a.get("str_rules") or {}
    icon, en_, es_ = S.airbnb_line(sr, "owner")
    lim, cty = FHA.loan_limit(t, 1)
    lim2, _ = FHA.loan_limit(t, 2)
    lvl, _c = C.town_caution(t)
    if lvl == "exclude":
        safety_note(t)                         # a strong caution stays in view; the milder ones are under "About this town"
    with st.expander(L(f"About {t}", f"Sobre {t}"), key=f"tinfo_{sid}"):
        drive_badge(a.get("drive"))
        if lvl != "exclude":
            safety_note(t)
        rules_card(sr, t)
        cn = (cty or "").title()
        if lim:
            fsub = L(f"Up to {money(lim)} (1 unit) or {money(lim2)} (2 units), HUD 2026 limits for {cn} County. ", f"Hasta {money(lim)} (1 unidad) o {money(lim2)} (2 unidades), límites HUD 2026 del condado de {cn}. ")
        else:
            fsub = ""
        fsub += L("Condos need an FHA-approved building; co-ops need a normal loan. Your lender has the final say.",
                  "Los condos necesitan un edificio aprobado por FHA; las co-ops, un préstamo normal. Su banco tiene la última palabra.")
        ftop = L("✅ FHA (3.5% down) works here for houses and 2-4 family homes you live in", "✅ FHA (3.5% inicial) sirve aquí para casas y de 2 a 4 familias donde usted viva")
        html(f"<div class='bz-fha ok'><b>{ftop}</b><div class='s'>{H.escape(fsub)}</div></div>")
        fha_explainer("t_" + sid, inline=True)
    homes_block(t, a.get("drive"), sid)
    st.markdown(f"#### {L('💵 What you would pay here', '💵 Lo que pagaría aquí')}")
    ss.setdefault(f"_tph_{sid}", {})["full_run"] = True
    _town_price_block(a, sid, first)
    hold = ss.get(f"_tph_{sid}") or {}
    size, out, cv = hold.get("size"), hold.get("out"), hold.get("cv")
    with st.expander(L("🏷️ What similar places rent for", "🏷️ Lo que se alquila algo parecido"), key=f"trc_{sid}"):
        _town_comps(a, sid, size, out)
    # Airbnb market card
    mk = a.get("market") or {}
    s_ = mk.get("summary") or {}
    with st.expander(L("🛏️ Airbnb market nearby", "🛏️ Mercado de Airbnb cerca"), key=f"tmk_{sid}"):
        if s_.get("n"):
            rough = not mk.get("covered")
            html("<div class='bz-card'>" + "".join(f"<div class='bz-kv'><span>{H.escape(x)}</span><b>{H.escape(y)}</b></div>" for x, y in [
                (L("Active short-stay homes", "Casas activas de estadía corta"), str(s_["n"])),
                (L("Typical nightly price", "Precio típico por noche"), money(s_.get("adr_median"))),
                (L("Typical nights booked a year", "Noches reservadas típicas al año"), str(round((s_.get("occ_median_sf_model") or 0) * 365))),
                (L("Typical income a year", "Ingreso típico al año"), f"{money(s_.get('revenue_median'))}"),
                (L("Usual range a year", "Rango usual al año"), f"{kmoney(s_.get('revenue_p25'))}-{kmoney(s_.get('revenue_p75'))}"),
                (L("Furnished 30+ day listings (2 bd)", "Anuncios amueblados 30+ días (2 hab)"), str(mk.get("n_30plus") or 0))]) + "</div>")
            st.caption((L(f"Rough estimate borrowed from {', '.join(x.replace('-', ' ').title() for x in mk.get('datasets') or [])} Airbnb data (no Inside Airbnb data for {t}).",
                          f"Estimado aproximado con datos de Airbnb de {', '.join(x.replace('-', ' ').title() for x in mk.get('datasets') or [])} (no hay datos de Inside Airbnb para {t}).") + " " if rough else "")
                       + L("Before costs. Inside Airbnb's model: booked nights from reviews, capped at 70%.", "Antes de gastos. Modelo de Inside Airbnb: noches según reseñas, tope 70%."))
        else:
            st.caption(L("No Airbnb data near this town.", "No hay datos de Airbnb cerca de este pueblo."))
    with st.expander(L("📅 Busy vs slow months", "📅 Meses de mucho y poco movimiento"), key=f"tss_{sid}"):
        season_block(a.get("seasonality"), t, head=False)
    sz = 2 if size == "2fam" else int(size)
    ro = (out or {}).get("rent_out", "unit" if size == "2fam" else "room")
    bb = {int(k): v for k, v in (a.get("by_beds") or {}).items()}
    if ro == "room":
        lists = {"rent": (a.get("rooms") or {}).get("comps") or [], "mtr": (a.get("room_mtr") or {}).get("comps") or [], "str": (a.get("room_str") or {}).get("comps") or []}
    else:
        ub = int(ss.get(f"ub_{sid}_mf") or 2) if ro == "unit" else sz
        u = bb.get(min(ub, 3)) or {}
        lists = {"rent": u.get("ltr_comps") or [], "mtr": (u.get("mtr") or {}).get("comps") or [], "str": (u.get("str") or {}).get("comps") or []}
    ok_air = (out or {}).get("airbnb_allowed", C.airbnb_ok(a.get("str_rules") or {}, "multi-family" if size == "2fam" else "single-family", "unit" if size == "2fam" else "room"))
    with st.expander(L("🏘️ Similar places nearby", "🏘️ Lugares parecidos cerca"), key=f"tpl_{sid}"):
        places_block(lists, a.get("str_rules") or {}, t, mk.get("datasets") and [f"nj/{x}" for x in mk["datasets"]] or [], ok_air, C.days30(a.get("str_rules") or {}), head=False)
    lg_ = "es" if ES() else "en"                      # both files are made only when tapped
    hold_ = ss.get(f"_tph_{sid}") or {}
    st.download_button(L("⬇️ Download the town report", "⬇️ Descargar el reporte del pueblo"), lambda a=a, h=hold_, lg_=lg_: town_html(a, h.get("cv"), lg_).encode(),
                       L(f"BellaZu_Town_{safe_name(t)}.html", f"BellaZu_Pueblo_{safe_name(t)}.html"), "text/html", key="dl_town", type="primary", width="stretch", on_click="ignore")
    xn = (f"BellaZu_Pueblo_{_fslug(a['town'])}_{str(a.get('generated') or '')[:10]}.xlsx" if lg_ == "es" else f"BellaZu_Town_{_fslug(a['town'])}_{str(a.get('generated') or '')[:10]}.xlsx")
    st.download_button(L("⬇️ Spreadsheet (Excel)", "⬇️ Hoja de cálculo (Excel)"), lambda a=a, h=hold_, lg_=lg_: _xlsx_or_note(lambda: _town_xlsx(a, h.get("cv"), lg_)), xn,
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dlx_town", width="stretch", on_click="ignore")


def town_problem(a):
    t = a.get("town") or a.get("town_input") or ""
    sug = a.get("town_suggestions") or []
    st.info(L(f"Hmm, we don't know “{t}” yet 💕 Pick a town below" + (", or did you mean one of these?" if sug else "."),
              f"Mmm, aún no conocemos “{t}” 💕 Elija un pueblo abajo" + (", ¿o quiso decir uno de estos?" if sug else ".")), icon="🌷")
    if sug:
        row = st.container(horizontal=True)
        for i, s_ in enumerate(sug[:4]):
            row.button(s_, key=f"sug_{i}_{s_}", on_click=lambda x=s_: st.session_state.update(go=("town", x)))


# ------------------------------------------------------------------ homes for sale / for rent feed (Realty in US on RapidAPI)
FEED_PRICE = {"for_sale": [None, 300_000, 400_000, 500_000, 650_000], "for_rent": [None, 2000, 2500, 3000, 4000]}
FEED_KIND = {"any": ("All", "Todas"), "condo": ("Condo", "Condo"), "2fam": ("2-family+", "2+ familias"), "house": ("House", "Casa")}
LISTING_TYPE = {"condo": "condo", "2fam": "2-family", "house": "single-family"}


@st.cache_data(ttl=18 * 3600, show_spinner=False)
def _feed_cached(town, status, zip_code=None):
    r = listings.fetch_town(town, status, zip_code=zip_code)
    if not r.get("ok"):
        raise RuntimeError(r.get("error") or "error")
    return r


def feed(town, status):
    try:
        return _feed_cached(town, status, (C.town_info(town) or {}).get("zip"))
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "rows": []}


@timed('cb:open_listing')
def _open_listing(row):
    ss = st.session_state
    v = ss.get("view")
    if v and v[0] == "towns":
        ss.from_towns = tuple(v[1])          # a "back to your towns" button on the home page
    ss.go = ("listing", row)
    ss.pop("arv_trail", None)
    ss._full = True


# Inline photo carousel on each feed card. The list call only carries the cover photo (checked: v3/list gives primary_photo + photo_count,
# no photos array), so a card starts with that one photo; swiping past it loads the full set with ONE detail call (7-day cache, the same
# call the full view uses). If the detail is already cached, all photos show right away with no call.
CZ_CSS = """
.cz{position:relative;width:100%;aspect-ratio:3/2;background:#1c1c1c;border:1px solid var(--line2,#2E2E2E);border-bottom:0;border-radius:22px 22px 0 0;overflow:hidden;box-sizing:border-box}
.tr{display:flex;width:100%;height:100%;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;scrollbar-width:none;-webkit-overflow-scrolling:touch;overscroll-behavior-x:contain;touch-action:pan-x pan-y}
.tr::-webkit-scrollbar{display:none}
.sl{flex:0 0 100%;width:100%;height:100%;scroll-snap-align:start;scroll-snap-stop:always;display:flex;align-items:center;justify-content:center;color:#DADADA;font:500 .85rem system-ui,sans-serif;text-align:center;padding:0 1rem;box-sizing:border-box}
.sl.im{padding:0;cursor:pointer}
.sl img{width:100%;height:100%;object-fit:cover;display:block;user-select:none;-webkit-user-select:none;-webkit-user-drag:none;pointer-events:none}
.sl.no{font-size:2rem}
.nv{position:absolute;top:50%;transform:translateY(-50%);width:36px;height:36px;border-radius:50%;border:0;background:rgba(0,0,0,.55);color:#fff;font-size:22px;line-height:36px;cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center}
.nv[hidden]{display:none}
.pv{left:8px}.nx{right:8px}
.ct{position:absolute;right:10px;bottom:10px;background:rgba(0,0,0,.65);color:#fff;font:600 .72rem system-ui,sans-serif;padding:.2rem .5rem;border-radius:10px;pointer-events:none}
.ct:empty{display:none}
.pb{position:absolute;left:10px;bottom:10px;max-width:calc(100% - 90px);background:rgba(12,12,12,.86);color:#fff;font:800 1.5rem/1.05 Inter,system-ui,sans-serif;letter-spacing:-.02em;padding:.38rem .65rem .4rem;border-radius:14px;border:1px solid rgba(244,167,187,.55);box-shadow:0 2px 10px rgba(0,0,0,.45);pointer-events:none;white-space:nowrap}
.pb:empty{display:none}
.pb small{font-size:.62em;font-weight:700;opacity:.9;margin-left:.08rem}
.pb .tg{display:inline-block;font:800 .62rem/1 Inter,system-ui,sans-serif;letter-spacing:.05em;padding:.28rem .42rem;border-radius:8px;margin-left:.45rem;vertical-align:.3em;color:#111}
.pb .tg.cut{background:#8FE3B5}.pb .tg.new{background:#F4A7BB}
.tw{position:absolute;left:10px;top:10px;background:rgba(0,0,0,.65);color:#fff;font:600 .72rem system-ui,sans-serif;padding:.2rem .55rem;border-radius:10px;pointer-events:none}
.tw:empty{display:none}
"""
CZ_JS = """
export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const d = data || {};
  let s = parentElement.__bz;
  if (!s) {
    const root = document.createElement('div');          // append (never replace parentElement's content: that holds the component's <style>)
    root.innerHTML = '<div class="cz"><div class="tr"></div><button class="nv pv" type="button">&#8249;</button>' +
      '<button class="nv nx" type="button">&#8250;</button><div class="ct"></div><div class="tw"></div><div class="pb"></div></div>';
    parentElement.appendChild(root);
    s = parentElement.__bz = { tr: root.querySelector('.tr'), ct: root.querySelector('.ct'), tw: root.querySelector('.tw'), pb: root.querySelector('.pb'),
      pv: root.querySelector('.pv'), nx: root.querySelector('.nx'), idx: 0, n: -1, extra: -1, slides: 1, asked: false, moved: false, d: d };
    const go = (i) => s.tr.scrollTo({ left: i * s.tr.clientWidth, behavior: 'smooth' });
    s.pv.onclick = (e) => { e.stopPropagation(); go(Math.max(s.idx - 1, 0)); };
    s.nx.onclick = (e) => { e.stopPropagation(); go(Math.min(s.idx + 1, s.slides - 1)); };
    let t = null, sx = 0, sy = 0;
    // a sideways swipe has started: ask for the rest of the photos NOW (not when the finger lands on the empty slide),
    // so the one detail call runs while the swipe animates. A vertical page scroll over the card never asks.
    const early = (dx, dy) => { if (s.extra && !s.asked && dx > 10 && dx > 1.5 * dy) { s.asked = true; setTriggerValue('more', String(s.d.id)); } };
    s.tr.addEventListener('scroll', () => { s.moved = true; clearTimeout(t); t = setTimeout(() => s.upd(), 80); }, { passive: true });
    s.tr.addEventListener('pointerdown', (e) => { sx = e.clientX; sy = e.clientY; s.moved = false; });
    s.tr.addEventListener('pointermove', (e) => { const dx = Math.abs(e.clientX - sx), dy = Math.abs(e.clientY - sy); if (dx > 8 || dy > 8) s.moved = true; early(dx, dy); });
    s.tr.addEventListener('touchstart', (e) => { const p = e.touches[0]; if (p) { sx = p.clientX; sy = p.clientY; s.moved = false; } }, { passive: true });
    s.tr.addEventListener('touchmove', (e) => { const p = e.touches[0]; if (p) early(Math.abs(p.clientX - sx), Math.abs(p.clientY - sy)); }, { passive: true });
    s.nx.addEventListener('pointerdown', () => early(99, 0));
    s.tr.addEventListener('click', (e) => {
      if (s.moved || !e.target.closest('.im')) return;
      if (s.d.open) setTriggerValue('open', String(s.d.id) + ':' + Date.now());
      else if (s.d.url) window.open(s.d.url, '_blank', 'noopener');
    });
    s.upd = () => {
      const w = s.tr.clientWidth || 1;
      s.idx = Math.max(0, Math.min(Math.round(s.tr.scrollLeft / w), s.slides - 1));
      const ph = s.d.photos || [];
      const total = Math.max(s.d.count || 0, ph.length);
      s.ct.textContent = total > 1 ? (Math.min(s.idx + 1, total) + '/' + total) : '';
      s.pv.hidden = s.idx <= 0;
      s.nx.hidden = s.idx >= s.slides - 1;
      if (s.extra && s.idx >= ph.length && !s.asked) { s.asked = true; setTriggerValue('more', String(s.d.id)); }
    };
    let rt = null;
    window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { s.tr.scrollLeft = s.idx * s.tr.clientWidth; }, 120); });
  }
  s.d = d;
  const lb = d.lbl || {};
  s.pv.setAttribute('aria-label', lb.prev || ''); s.nx.setAttribute('aria-label', lb.next || '');
  s.tw.textContent = d.town || '';
  { // price badge: stays in the corner while the photos move under it
    const e = (x) => String(x == null ? '' : x).replace(/[&<>\"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    s.pb.innerHTML = d.price ? e(d.price) + (d.per ? '<small>' + e(d.per) + '</small>' : '') + (d.tag ? '<span class="tg ' + (d.tagc === 'cut' ? 'cut' : 'new') + '">' + e(d.tag) + '</span>' : '') : '';
  }
  const ph = d.photos || [];
  const extra = (d.more && ph.length < (d.count || 0)) ? 1 : 0;
  if (s.n !== ph.length || s.extra !== extra) {
    const esc = (u) => String(u).replace(/[\"'<>]/g, '');
    // photos 1-3 load right away (the 2nd with high priority) so the first swipes show a ready photo; the rest load lazily.
    // Each slide shows realtor.com's tiny 120 px version of its photo (about 4 KB) as a blurred placeholder until the real one arrives.
    const tiny = (u) => /rdcpix\\.com\\/.+-m\\d+[a-z]?(rd|od)-w\\d+_h\\d+\\.jpg$/.test(u) ? String(u).replace(/(rd|od)-w\\d+_h\\d+\\.jpg$/, 's.jpg') : '';
    let h = ph.map((u, i) => { const ty = i ? tiny(u) : '';
      return '<div class="sl im"' + (ty ? ' style="background:#1c1c1c url(\\'' + esc(ty) + '\\') center/cover no-repeat"' : '') + '><img src="' + esc(u) + '"' +
        (i < 3 ? (i === 1 ? ' fetchpriority="high"' : '') : ' loading="lazy"') + ' decoding="async" alt="' + esc(lb.photo || '') + ' ' + (i + 1) + '" draggable="false"></div>'; }).join('');
    if (!ph.length) h = '<div class="sl no">&#128247;</div>';
    if (extra) h += '<div class="sl ld">' + esc(lb.loading || '...') + '</div>';
    if (s.n >= 0 && ph.length > s.n) s.asked = false;
    s.tr.innerHTML = h;
    s.n = ph.length; s.extra = extra; s.slides = Math.max(1, (ph.length || 1) + extra);
    requestAnimationFrame(() => { s.tr.scrollLeft = Math.min(s.idx, s.slides - 1) * s.tr.clientWidth; s.upd(); });
  } else {
    s.upd();
  }
}
"""
_CZ = st.components.v2.component("bz_carousel", css=CZ_CSS, js=CZ_JS)


def _card_photos(h):
    """(photos for the card, total photo count). No API call here."""
    ss = st.session_state
    pid = str(h.get("id") or "")
    full = (ss.get("cz_ph") or {}).get(pid)
    if full is None and pid:
        d = listings.detail_cached(pid)
        if d and d.get("ok") and d.get("photos"):
            full = [_thumb(u) for u in d["photos"] if u]
    if full:
        cover = h.get("photo")
        if cover and cover not in full:
            full = [cover] + full
        return full[:60], max(len(full[:60]), 0)
    return ([h["photo"]] if h.get("photo") else []), int(h.get("photo_count") or 0)


def _cz_more(key, h):
    """Swiped past the last photo we have: one detail call (7-day cache) for the full set."""
    ss = st.session_state
    pid = str(h.get("id") or "")
    if not pid or pid in ss.setdefault("cz_ph", {}):
        return
    d = listings.detail(pid)
    if d.get("ok") and d.get("photos"):
        ss.cz_ph[pid] = [_thumb(u) for u in d["photos"] if u]
    else:
        ss.setdefault("cz_fail", set()).add(pid)


def carousel(h, key, rent, town_lbl=None, on_open=None, more_ok=True):
    ss = st.session_state
    tag, tagc = ((f"↓ {kmoney(h['price_cut'])}", "cut") if h.get("price_cut") else (L("NEW", "NUEVA"), "new") if h.get("new") else ("", ""))
    photos, count = _card_photos(h)
    pid = str(h.get("id") or "")
    more = more_ok and bool(pid) and pid not in (ss.get("cz_fail") or set()) and pid not in (ss.get("cz_ph") or {}) and count > len(photos)
    _CZ(key=key, data={"photos": photos, "count": count, "id": pid, "more": more, "open": not rent, "url": h.get("url") if rent else None,
                       "town": town_lbl or "", "price": money(h["price"]) if h.get("price") else "", "per": L("/mo", "/mes") if rent else "",
                       "tag": tag, "tagc": tagc,
                       "lbl": {"loading": L("Loading more photos... ✨", "Cargando más fotos... ✨"), "prev": L("Previous photo", "Foto anterior"),
                               "next": L("Next photo", "Foto siguiente"), "photo": L("Photo", "Foto")}},
        on_more_change=lambda k=key, x=h: _cz_more(k, x), on_open_change=(on_open or (lambda x=h: _open_listing(x))) if not rent else (lambda: None))


@timed('card')
def _home_card(h, drive, rent, key, town_lbl=None):
    """Just the photos with the price badge on them (price, /mo, NEW or price-cut tag). Days listed, drive, FHA, fee, broker and
    address are in the home's own view (tap the photo or "Details"); the one facts line + heart come right after (feed_block)."""
    carousel(h, f"cz_{key}", rent, None)


def _card_line(h, town_lbl=None):
    """beds · baths · town (several towns) or sqft (one town): the only text under a card's photo."""
    b = [f"{h['beds']} {L('bd', 'hab')}" if h.get("beds") is not None else None,
         f"{float(h['baths']):g} {L('ba', 'baño' if float(h['baths']) == 1 else 'baños')}" if h.get("baths") else None,
         town_lbl if town_lbl else (f"{int(h['sqft']):,} ft²" if h.get("sqft") else None)]
    return " · ".join(x for x in b if x)


FEED_SORT = {"new": ("Newest", "Más nuevas"), "low": ("Price ↑", "Precio ↑"), "high": ("Price ↓", "Precio ↓")}


def _sort_rows(rows, how):
    if how == "new":
        return sorted(rows, key=lambda r: (r.get("days") is None, r.get("days") or 0))
    return sorted(rows, key=lambda r: (r.get("price") is None, (r.get("price") or 0) * (1 if how == "low" else -1)))


def _dedupe(rows):
    out, ids, adr = [], set(), set()
    for r in rows:
        a = _norm_addr(r.get("address"))
        if (r.get("id") and r["id"] in ids) or (a and a in adr):
            continue
        ids.add(r.get("id"))
        adr.add(a)
        out.append(r)
    return out


POOL = 3          # towns looked up at the same time (small: polite to the free sources, and RapidAPI's per-second limit)


def _parallel(jobs, on_done=None):
    """Run [(key, fn)] a few at a time in threads (Streamlit's run context attached so caches work). Returns {key: result or exception}."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    ctx = get_script_run_ctx()

    def wrap(fn):
        def w():
            if ctx is not None:
                add_script_run_ctx(threading.current_thread(), ctx)
            return fn()
        return w
    out = {}
    if not jobs:
        return out
    with ThreadPoolExecutor(max_workers=min(POOL, len(jobs))) as ex:
        futs = {ex.submit(wrap(fn)): k for k, fn in jobs}
        for n, f in enumerate(as_completed(futs), 1):
            k = futs[f]
            try:
                out[k] = f.result()
            except Exception as e:
                out[k] = e
            if on_done:
                on_done(n, len(jobs), k)
    return out


def _feed_jobs(ts, status):
    """Jobs for the towns whose list isn't cached yet, never more than the searches left this month (the 450 cap)."""
    if not listings.available():
        return []
    need = [t for t in ts if not listings.cached(t, status)]
    left = max(int(listings.usage().get("left") or 0), 0)
    return [(("feed", t, status), (lambda t=t: feed(t, status))) for t in need[:max(left, 1)]]


@timed('feed_fetch')
def feeds_for(ts, status, pre=None):
    """One list call per uncached town (up to 3 at once); cached towns cost nothing. Shows progress when something has to load.
    pre = results already fetched in this run ({town: result}), so a failed town is never asked twice."""
    pre = dict(pre or {})
    jobs = [j for j in _feed_jobs(ts, status) if j[0][1] not in pre]
    if jobs:
        if len(ts) > 1:
            bar = st.progress(0.0, text=L("Finding homes... ✨", "Buscando casas... ✨"))
            res = _parallel(jobs, lambda n, m, k: bar.progress(n / m, text=L(f"Finding homes in {k[1]} ({n} of {m})... ✨", f"Buscando casas en {k[1]} ({n} de {m})... ✨")))
            bar.empty()
        else:
            with st.spinner(L("Finding homes... ✨", "Buscando casas... ✨")):
                res = _parallel(jobs)
        for (_, t, _), r in res.items():
            pre[t] = r if isinstance(r, dict) else {"ok": False, "error": r.__class__.__name__, "rows": []}
    return {t: (pre[t] if t in pre else feed(t, status)) for t in ts}


def _cap_msg():
    u = listings.usage()
    st.info(L(f"We've used this month's home searches ({u['used']} of {u['cap']}). They start again on {u.get('resets') or 'the next month'}. Towns you already opened still show.",
              f"Ya usamos las búsquedas de casas de este mes ({u['used']} de {u['cap']}). Vuelven el {u.get('resets') or 'próximo mes'}. Los pueblos ya abiertos se siguen viendo."), icon="🌷")


def homes_block(t, drive, sid):
    feed_block([t], {t: drive}, sid)


@st.fragment
@timed('feed')
def feed_block(ts, drives, sid):
    """Listings feed for one town or several (combined, deduped, town label on each card). Filters and sort apply across all of them."""
    ss = st.session_state
    if ss.get("_full"):                       # a tap in here changed something outside the feed (opened a home, saved one): redraw the page
        st.rerun(scope="app")
    if not listings.available():
        return
    multi = len(ts) > 1
    html(f"<div class='bz-fh'>{H.escape(L('🏡 Homes in ' + ts[0], '🏡 Casas en ' + ts[0]) if not multi else L(f'🏡 Homes in your {len(ts)} towns', f'🏡 Casas en sus {len(ts)} pueblos'))}</div>")
    status = st.segmented_control(L("For sale or rent", "En venta o alquiler"), ["for_sale", "for_rent"], key=f"hst_{sid}", default="for_sale", required=True, label_visibility="collapsed", width="stretch",
                                  on_change=lambda: st.session_state.update(_full=True),
                                  format_func=lambda s_: L("For sale", "En venta") if s_ == "for_sale" else L("For rent", "En alquiler"))
    rent = status == "for_rent"
    fp = ss.get("_feed_pre") or {}
    res = feeds_for(ts, status, {t: fp[(t, status)] for t in ts if (t, status) in fp})
    ok = {t: r for t, r in res.items() if r.get("ok")}
    bad = [t for t, r in res.items() if not r.get("ok")]
    if not ok:
        if any(r.get("error") == "cap" for r in res.values()):
            _cap_msg()
        else:
            st.caption(L("Home listings aren't loading right now. Try again later.", "Los anuncios de casas no cargan ahora. Intente más tarde."))
        return
    if bad:
        if any(res[t].get("error") == "cap" for t in bad):
            _cap_msg()
        st.caption(L(f"Couldn't load homes for {', '.join(bad)} right now; showing the others.", f"No se pudieron cargar las casas de {', '.join(bad)} ahora; mostramos los demás."))
    # filters one tap away (summary in the label) so the first home card shows on the first screen
    _pmax = int(loan_prof()["max_price"])
    _pdef = None if rent else (_pmax if _pmax in FEED_PRICE["for_sale"] else 300_000)
    _mx0 = ss.get(f"hpx_{sid}_{status}", _pdef)
    _ap0 = (not rent) and bool(ss.get(f"happ_{sid}", False))
    _bd0, _kd0, _srt0 = ss.get(f"hbd_{sid}", 0), ss.get(f"hkd_{sid}", "any"), ss.get(f"hsort_{sid}", "new")
    _fl = " · ".join([(L("any price", "cualquier precio") if _mx0 is None else L("up to ", "hasta ") + (money(_mx0) if rent else kmoney(_mx0))),
                      (L("any beds", "cualquier tamaño") if not _bd0 else L(f"{_bd0}+ bd", f"{_bd0}+ hab")),
                      P(FEED_KIND.get(_kd0, FEED_KIND["any"])), P(FEED_SORT.get(_srt0, FEED_SORT["new"]))]
                     + ([L("approved only", "solo aprobadas")] if _ap0 else []))
    with st.expander(L(f"⚙️ Filters: {_fl}", f"⚙️ Filtros: {_fl}"), key=f"hflt_{sid}"):
        st.markdown(f"<div class='bz-lbl'>{L('Price up to', 'Precio hasta')}</div>", unsafe_allow_html=True)
        mx = st.segmented_control(L("Top price", "Precio máximo"), FEED_PRICE[status], key=f"hpx_{sid}_{status}", default=_pdef, required=True, label_visibility="collapsed", width="stretch",
                                  format_func=lambda v: L("Any", "Todo") if v is None else (money(v) if rent else kmoney(v)))
        if not rent:
            st.toggle(L("Only homes I'm approved for", "Solo casas para las que estoy aprobada"), key=f"happ_{sid}",
                      help=L(f"Price up to {kmoney(_pmax)} and a monthly cost (with the HOA and taxes) at or under your approved {money(approved_monthly()['total'])}.",
                             f"Precio hasta {kmoney(_pmax)} y un costo mensual (con HOA e impuestos) igual o menor a su aprobado de {money(approved_monthly()['total'])}."))
        c1, c2 = st.columns([2, 3])
        with c1:
            bd = st.segmented_control(L("Bedrooms", "Habitaciones"), [0, 1, 2, 3], key=f"hbd_{sid}", default=0, required=True, width="stretch",
                                      format_func=lambda b: L("Any", "Todas") if b == 0 else f"{b}+")
        with c2:
            kd = st.segmented_control(L("Type", "Tipo"), list(FEED_KIND), key=f"hkd_{sid}", default="any", required=True, width="stretch", format_func=lambda k: P(FEED_KIND[k]))
        srt = st.segmented_control(L("Sort", "Ordenar"), list(FEED_SORT), key=f"hsort_{sid}", default="new", required=True, width="stretch", format_func=lambda k: P(FEED_SORT[k]))
    allrows = _dedupe([dict(r, town=r.get("town") or t, _t=t) for t, r_ in ok.items() for r in r_["rows"]])
    rows = _sort_rows(listings.filter_rows(allrows, None, mx, bd or None, kd), srt)
    if not rent and ss.get(f"happ_{sid}"):
        rows = [r for r in rows if (home_money(r) or {}).get("tag") == "ok" and not (home_money(r) or {}).get("fha")]
    shown = int(ss.get(f"hn_{sid}", 8))
    listings.prefetch_details([h.get("id") for h in rows[:shown]])      # Pro only: galleries for the cards on screen, on a side thread
    for i, h in enumerate(rows[:shown]):
        hk = f"{sid}_{i}_{h.get('id') or safe_name(h.get('address') or '')[:20]}"
        with st.container(key=f"hcard_{hk}", gap=None):
            _home_card(h, drives.get(h["_t"]), rent, hk, h["_t"] if multi else None)
        iid = find_home(h.get("address"), h.get("id")) or saves.item_id("listing", h.get("id") or h.get("address"))
        with st.container(horizontal=True, vertical_alignment="center", key=f"hrow_{sid}_{i}", gap="small"):
            st.markdown(f"<div class='bz-hl'>{H.escape(_card_line(h, h['_t'] if multi else None))}</div>", unsafe_allow_html=True, width="stretch")
            heart(iid, f"h_{sid}_{i}_{_sv_key(iid)[-12:]}", entry_from_feed, (h, rent))
            if rent:
                if h.get("url"):
                    st.link_button(L("realtor.com ↗", "realtor.com ↗"), h["url"], type="tertiary")
            else:
                st.button(L("Details ›", "Ver ›"), key=f"ho_{sid}_{i}_{h['id']}", type="tertiary", on_click=_open_listing, args=(h,))
        if not rent:
            hm = home_money(h)
            if hm:
                tt, tc = tag_txt(hm["tag"])
                html(f"<div class='bz-cm'><span class='tg {tc}'>{H.escape(tt)}</span> · <b>{money(hm['m']['total'])}{L('/mo', '/mes')}</b>"
                     f"<div class='x'>{H.escape(hoa_txt(hm['hoa']))}"
                     + (H.escape(L(' · taxes: lender figure', ' · impuestos: cifra del banco')) if hm['m']['tax_src'] == 'lender' else '') + "</div>"
                     + (f"<div class='ff'>{H.escape(L(*FHA_FLAG[hm['fha']]))}</div>" if hm.get("fha") else
                        f"<div class='cn'>{H.escape(L(*COOP_NOTE))}</div>" if hm.get("coop") else "")
                     + (f"<div class='x'>{H.escape(hoa_extra_note(hm['hoa']))}</div>" if hoa_extra_note(hm['hoa']) else "") + "</div>")
    if len(rows) > shown:
        st.button(L(f"Show more ({len(rows) - shown} more)", f"Ver más ({len(rows) - shown} más)"), key=f"hmore_{sid}", width="stretch",
                  on_click=lambda: ss.update({f"hn_{sid}": shown + 8}))
    if not rows and not rent and ss.get(f"happ_{sid}") and loan_prof()["kind"] == "fha":
        st.caption(L("No listings here fit your approval with FHA. Most condo buildings around here aren't on HUD's FHA-approved list, and co-ops can't use FHA. "
                     "Turn off 'Only homes I'm approved for' to see homes flagged 'Not FHA-approved' and ask your lender about a single-unit approval.",
                     "Ningún anuncio aquí cabe en su aprobación con FHA. La mayoría de los edificios de condos de la zona no están en la lista FHA de HUD, y los co-ops no pueden usar FHA. "
                     "Apague 'Solo casas para las que estoy aprobada' para ver las casas marcadas 'Sin aprobación FHA' y pregunte a su banco por una aprobación de unidad individual."))
    elif not rows:
        st.caption(L("No listings match. Try another price or type.", "Ningún anuncio coincide. Pruebe otro precio o tipo."))
    upd = min((r_.get("fetched") or "") for r_ in ok.values())[-5:]
    if multi:
        st.caption(L(f"{len(rows)} of the {len(allrows)} newest listings in {len(ok)} towns match (updated {upd}).",
                     f"{len(rows)} de los {len(allrows)} anuncios más nuevos en {len(ok)} pueblos coinciden (actualizado {upd})."))
    else:
        st.caption(L(f"{len(rows)} of the {len(allrows)} newest listings match (updated {upd}).",
                     f"{len(rows)} de los {len(allrows)} anuncios más nuevos coinciden (actualizado {upd})."))
    u = listings.usage()
    st.caption(L(f"Listing data from realtor.com via Realty in US. Prices and details can change; check with the agent. Swipe a photo to see more. Home searches this month: {u['used']} of {u['cap']}.",
                 f"Datos de anuncios de realtor.com vía Realty in US. Los precios y datos pueden cambiar; confirme con el agente. Deslice una foto para ver más. Búsquedas de casas este mes: {u['used']} de {u['cap']}."))


@timed('run_listing')
def run_listing(h, where):
    """Open a listing: one detail call (photos + HOA + taxes, cached), then our analysis with the listing's facts (no RentCast needed for price)."""
    ss = st.session_state
    with where, st.spinner(L("Getting the photos... ✨", "Trayendo las fotos... ✨")):
        d = listings.detail(h["id"]) if h.get("id") else {"ok": False}
    addr = h["address"]
    hi = listings.hoa_info(h, d if d.get("ok") else None)
    if hi["state"] in ("est", "unknown") and hi.get("kind") in HOA.HOA_KINDS and rentcast.available() and ss.get("set_rc", True):
        try:                  # realtor.com has no fee for this condo/co-op: RentCast's copy of the listing sometimes does (1 lookup, cached 3 days;
            if rentcast.remaining() > 3:              # the full check used to spend this same lookup)
                rc_, _s = rentcast.sale_listing(addr)
                fee = ((rc_ or {}).get("hoa") or {}).get("fee")
                if fee and HOA.LO <= float(fee) <= HOA.HI:
                    listings.add_hoa_obs(h.get("id"), h.get("town"), h.get("zip"), hi["kind"], fee, h.get("sqft"), h.get("beds"))
                    if h.get("id"):
                        listings.set_detail_hoa(str(h["id"]), fee, "RentCast sale listing")
                    d = dict(d, hoa_monthly=int(fee), hoa_src="RentCast sale listing")
                    ss.pop("_hm", None)
        except Exception:
            pass
    fo = facts_for(addr)
    fo.update(_listing_facts(h, d))
    hoa = fo.get("hoa")
    ss.setdefault("gallery", {})[addr.strip().lower()] = {"photos": (d.get("photos") if d.get("ok") else None) or h.get("photos") or [], "url": h.get("url"),
                                                          "broker": h.get("broker"), "price": h.get("price"), "hoa": hoa, "count": h.get("photo_count"),
                                                          "id": str(h.get("id") or ""), "text": (d.get("text") if d.get("ok") else None),
                                                          "town": h.get("town"), "zip": h.get("zip"), "flags": h.get("flags") or [], "days": h.get("days")}
    ss.view = ("addr", addr)
    ss.prop_addr = addr
    run_home(addr, where)


def gallery_block(addr):
    g = (st.session_state.get("gallery") or {}).get((addr or "").strip().lower())
    if not g or not g.get("photos"):
        return
    ph = g["photos"][:40]
    html("<div class='bz-gal'>" + "".join(f"<img src='{H.escape(u)}' loading='{'eager' if i < 2 else 'lazy'}' alt=''>" for i, u in enumerate(ph)) + "</div>")
    bits = [L(f"Swipe for {len(ph)} photos", f"Deslice para ver {len(ph)} fotos")] if len(ph) > 1 else []
    dy = g.get("days")
    if isinstance(dy, int):
        bits.append(L("listed today", "publicada hoy") if dy == 0 else L("listed 1 day ago", "publicada hace 1 día") if dy == 1 else
                    L(f"listed {dy} days ago", f"publicada hace {dy} días"))
    if g.get("broker"):
        bits.append(L(f"listed by {g['broker']}", f"publicada por {g['broker']}"))
    st.caption((" · ".join(bits) + ". " if bits else "") + L("Price from the listing (realtor.com via Realty in US).", "Precio del anuncio (realtor.com vía Realty in US).")
               + (f" [realtor.com ↗]({g['url']})" if g.get("url") else ""))


# ------------------------------------------------------------------ search
def omni_search(term):
    t = (term or "").strip()
    if len(t) < 2:
        return []
    out = []
    low = t.lower()
    cur = st.session_state.get("tsel") or []
    for n in [n for n in towns.names() if low in n.lower()][:4]:
        out.append((f"🏙️ {n} · {L('town view', 'ver pueblo')}", f"T|{n}"))
        if cur and n not in cur and n != "New York City":
            out.append((L(f"➕ Add {n} to my {len(cur)} selected", f"➕ Agregar {n} a mis {len(cur)} elegidos"), f"M|{n}"))
    if len(t) >= 5 and re.search(r"\d", t):
        try:
            from bellazu.geo import suggest
            out += [(f"📍 {s_}", f"A|{s_}") for s_ in suggest(t, 4)]
        except Exception:
            pass
    out.append((L(f"✏️ Use exactly: {t}", f"✏️ Usar tal cual: {t}"), f"?|{t}"))
    return out


def resolve(val):
    v = str(val or "").strip()
    kind, text = (v[0], v[2:]) if len(v) > 2 and v[1] == "|" else ("?", v)
    if kind == "?":
        tn = towns.normalize(text)
        if not re.search(r"\d", text) and tn["match"] in ("exact", "alias", "fuzzy"):
            return ("town", tn["name"])
        return ("addr", text)
    return ("town" if kind == "T" else "addtown" if kind == "M" else "addr", text)


@st.fragment
@timed('search')
def search_block():
    ss = st.session_state
    val = None
    if ss.get("plain_addr"):
        st.text_input(L("Address or town", "Dirección o pueblo"), key="omni_plain", placeholder=L("123 Main St, Union · or Hoboken", "123 Main St, Union · o Hoboken"))
        val = ss.get("omni_plain")
    else:
        st.markdown(f"<div class='bz-lbl'>{L('Address or town', 'Dirección o pueblo')}</div>", unsafe_allow_html=True)
        try:
            from streamlit_searchbox import st_searchbox
            val = st_searchbox(omni_search, key="omni_sb", placeholder=L("Type an address or a town", "Escriba una dirección o un pueblo"),
                               debounce=350, default_use_searchterm=True, edit_after_submit="option", rerun_scope="fragment", style_overrides=SB_STYLE)
            if not val:
                val = ((ss.get("omni_sb") or {}).get("search") or "").strip() or None
        except Exception:
            ss.plain_addr = True
            st.rerun(scope="fragment")
    if st.button(L("Check it", "Revisar"), type="primary", key="go_btn", width="stretch"):
        if val and str(val).strip():
            ss.go = resolve(val)
            st.rerun()
        else:
            st.warning(L("Type an address or a town first 💕", "Primero escriba una dirección o un pueblo 💕"))
    if not ss.get("plain_addr"):
        st.button(L("Trouble typing? Use a plain box", "¿Problemas? Use una caja simple"), key="plain_btn", type="tertiary", on_click=lambda: ss.update(plain_addr=True))


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fha_rate():
    try:
        from bellazu.core import _rates
        from bellazu.config import load_assumptions
        return float(_rates(load_assumptions())["fha"])
    except Exception:
        return 6.5


# ------------------------------------------------------------------ several towns at once
MAX_TOWNS = 6


def tsel():
    return st.session_state.setdefault("tsel", [])


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", str(t).lower()).strip("-")


def _tsel_url():
    s_ = tsel()
    try:
        if s_:
            st.query_params["towns"] = ",".join(_slug(t) for t in s_)
        elif "towns" in st.query_params:
            del st.query_params["towns"]
    except Exception:
        pass


def _set_tsel(new, open_view=True):
    """The one place the town selection changes: dedupe, cap at 6 (friendly note), URL, and which view shows."""
    ss = st.session_state
    out = []
    for t in new:
        if t and t not in out:
            out.append(t)
    if len(out) > MAX_TOWNS:
        out = out[:MAX_TOWNS]
        ss.tsel_full = time.time()
    ss.tsel = out
    ss.pop("from_towns", None)
    _tsel_url()
    if not open_view:
        return
    v = ss.get("view")
    if not out:
        if v and v[0] in ("town", "towns"):
            ss.view = None
    elif len(out) == 1:
        ss.go = ("town", out[0])
    else:
        ss.view = ("towns", tuple(out))


def _merge_pick(cur, opts, picked):
    """Widget showed `opts`, now `picked` of them are on: keep other selected towns, drop unticked ones, add new ones at the end."""
    return [t for t in cur if t not in opts or t in picked] + [t for t in picked if t not in cur]


def _chip_towns(hm):
    ss = st.session_state
    _set_tsel(_merge_pick(tsel(), set(ss.get(f"_tchips_opts_{hm}") or []), ss.get(f"tchips_{hm}") or []))


def _pick_towns():
    ss = st.session_state
    _set_tsel(_merge_pick(tsel(), set(ss.get("_tpick_opts") or []), ss.get("tpick") or []))


def _clear_towns():
    _set_tsel([])


def _sync_multi(key, opts):
    """Show the canonical selection on a multi-pick widget before it is drawn (no default, so no double-set warning)."""
    st.session_state[key] = [t for t in tsel() if t in opts]


@timed('chips')
def town_chips(hm):
    ss = st.session_state
    rows = C.mode_towns(hm)
    if hm == "first":
        rows = sorted(rows, key=lambda t: (C.town_info(t) or {}).get("drive_offpeak_min", 99))
    st.markdown(f"<div class='bz-lbl'>{L('Towns near the city (closest drive first)', 'Pueblos cerca de la ciudad (más cerca primero)') if hm == 'first' else L('Towns to compare', 'Pueblos para comparar')}"
                f" · {L('tap one or several', 'toque uno o varios')}</div>", unsafe_allow_html=True)
    ss[f"_tchips_opts_{hm}"] = rows
    _sync_multi(f"tchips_{hm}", rows)
    st.pills(L("Towns", "Pueblos"), rows, selection_mode="multi", key=f"tchips_{hm}", on_change=_chip_towns, args=(hm,), label_visibility="collapsed")
    tsel_bar("c")
    with st.expander(L("🔎 More towns (search)", "🔎 Más pueblos (buscar)"), expanded=bool(ss.get("tpick_q"))):
        q = st.text_input(L("Find a town", "Buscar un pueblo"), key="tpick_q", placeholder=L("Type part of a name, e.g. Nut", "Escriba parte del nombre, ej. Nut"))
        allt = [t for t in towns.names() if t != "New York City"]
        opts = [t for t in allt if (q or "").strip().lower() in t.lower()] if (q or "").strip() else allt
        ss["_tpick_opts"] = opts
        if opts:
            _sync_multi("tpick", opts)
            st.pills(L("All towns", "Todos los pueblos"), opts, selection_mode="multi", key="tpick", on_change=_pick_towns, label_visibility="collapsed")
        else:
            st.caption(L("No town matches that. Try fewer letters.", "Ningún pueblo coincide. Pruebe con menos letras."))


def tsel_bar(where):
    """'N towns selected' + clear all, and the friendly 6-town note."""
    ss = st.session_state
    s_ = tsel()
    if time.time() - ss.get("tsel_full", 0) < 15:
        st.info(L(f"You can compare up to {MAX_TOWNS} towns at once. Tap one to remove it, then add another 💕",
                  f"Puede comparar hasta {MAX_TOWNS} pueblos a la vez. Toque uno para quitarlo y luego agregue otro 💕"), icon="🌷")
    if not s_:
        return
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute", key=f"tselbar_{where}"):
        n = len(s_)
        html(f"<div class='bz-tsel'>✓ <b>{L(f'{n} town selected' if n == 1 else f'{n} towns selected', f'{n} pueblo elegido' if n == 1 else f'{n} pueblos elegidos')}</b> · {H.escape(', '.join(s_))}</div>")
        st.button(L("✕ Clear all", "✕ Borrar todo"), key=f"tclear_{where}", type="tertiary", on_click=_clear_towns)


def _snap(t):
    """Town snapshot from the session cache, or build it (free public data, never RentCast)."""
    ss = st.session_state
    tn = towns.normalize(t)
    key = (tn["name"] or t).lower()
    cache = ss.setdefault("town_cache", {})
    if key in cache:
        return cache[key]
    try:
        a = town_snap(t)
    except Exception as e:
        a = {"ok": False, "error": e.__class__.__name__}
    if a.get("ok"):
        cache[key] = a
    return a


def _safety_short(t):
    sf = (C.town_info(t) or {}).get("safety") or {}
    lvl, c = C.town_caution(t)
    r = sf.get("ratio")
    if r is None:
        if lvl:
            return ("⚠️ " if lvl == "exclude" else "ℹ️ ") + L("Safety note, open the town for details", "Nota de seguridad, abra el pueblo para ver")
        return L("Safety: no state data", "Seguridad: sin datos del estado")
    ic = "⚠️" if lvl == "exclude" else "ℹ️" if lvl == "above" else "✓"
    return f"{ic} " + L(f"Violent crime {r:.1f}× the NJ average", f"Crimen violento {r:.1f}× el promedio de NJ")


@st.fragment
@timed("towns_summary")
def _towns_summary(ts, snaps, sale, first):
    """Price / size chips + one card per town. A chip tap redraws only this part (a fragment), not the whole page."""
    ss = st.session_state
    if ss.get("_full"):
        st.rerun(scope="app")
    st.markdown(f"<div class='bz-lbl'>{L('Tap a price to compare the monthly cost', 'Toque un precio para comparar el costo mensual')}</div>", unsafe_allow_html=True)
    price = st.pills(L("Price", "Precio"), C.PRICE_CHIPS, key="mt_price", label_visibility="collapsed", format_func=kmoney)
    size = st.segmented_control(L("Size", "Tamaño"), C.TOWN_SIZES, key="mt_size", default="2fam" if first else "2", required=True, width="stretch",
                                format_func=lambda s_: L("2-family", "2 familias") if s_ == "2fam" else f"{s_} {L('bd', 'hab')}")
    cards, pay2 = [], {}
    for t in ts:
        a = snaps.get(t) or {}
        if not a.get("ok"):
            cards.append((t, None, f"<div class='c'><div class='t'>{H.escape(t)}</div><div class='s'>{L('Could not load this town right now.', 'No se pudo cargar este pueblo ahora.')}</div></div>"))
            continue
        dr = a.get("drive") or {}
        drv = f"🚗 {dr['min']}-{dr['rush'][1]} min" if dr.get("rush") else "🚗 —"
        rows_ = ((sale.get(t) or {}).get("rows") or []) if (sale.get(t) or {}).get("ok") else []
        ps = sorted(r["price"] for r in rows_ if r.get("price"))
        typ = (f"{kmoney(ps[len(ps) // 2])} · {len(ps)} {L('listings', 'anuncios')}" if ps else "—")
        rules = a.get("str_rules") or {}
        ok_air = C.airbnb_ok(rules, "multi-family" if size == "2fam" else "single-family", "unit" if size == "2fam" else "room")
        body = ""
        if price:
            try:
                base = C.base_from_town(a, int(price), size, loan=loan_prof())
                out = C.compare(base, C.default_sel(base))
                ok_air = out.get("airbnb_allowed", ok_air)
                for c in C.labels(out, first):
                    earn = c["pay_lbl"][0] == "You earn"
                    body += f"<div class='r'><span>{H.escape(P(c['title']))}</span><b class='{'earn' if earn else ''}'>{H.escape(c['pay'])}</b></div>"
                p2 = out["cols"][1].get("pay")
                if p2 is not None:
                    pay2[t] = p2
            except Exception:
                body = f"<div class='s'>{L('Monthly numbers not available.', 'Números del mes no disponibles.')}</div>"
        else:
            body = f"<div class='s'>👆 {L('Tap a price above', 'Toque un precio arriba')}</div>"
        badge = P(C.airbnb_badge(ok_air, C.days30(rules)))
        cards.append((t, pay2.get(t), f"<div class='c{{best}}'><div class='t'>{H.escape(t)}</div><div class='v'>{drv}</div>"
                                       f"<div class='k'>{L('Typical asking price', 'Precio típico pedido')}</div><div class='v'>{H.escape(typ)}</div>"
                                       + (f"<div class='k'>{L('A month', 'Al mes')}</div>" if price else "") + body
                                       + f"<div class='s'>{H.escape(_safety_short(t))}</div><div class='s'>{H.escape(badge)}</div></div>"))
    best = min(pay2, key=pay2.get) if len(pay2) > 1 else None
    if price and pay2:
        cards.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0))
    html("<div class='bz-mt'>" + "".join(c.replace("{best}", " best" if t == best else "") for t, _, c in cards) + "</div>")
    st.caption((L(f"Sorted by what you'd pay with a tenant or roommate (★ lowest: {best}). " if best else "Sorted by what you'd pay with a tenant or roommate. ",
                  f"Ordenado por lo que pagaría con inquilino o compañero (★ más bajo: {best}). " if best else "Ordenado por lo que pagaría con inquilino o compañero. ") if price and pay2 else "")
               + L("Typical asking price: middle of the newest listings under $900k. Drive: typical, not live; second number is rush hour.",
                   "Precio típico pedido: el del medio de los anuncios más nuevos bajo $900k. Trayecto: típico, no en vivo; el segundo número es hora pico.").replace("$", "\\$"))
    with st.container(horizontal=True, key="mt_open"):
        for t, _, _c in cards:
            st.button(L(f"{t} →", f"{t} →"), key=f"mto_{_slug(t)}", on_click=_open_one_town, args=(t,))
    st.caption(L("Tap a town to open its full view.", "Toque un pueblo para abrir su vista completa."))


@timed('towns_view')
def show_towns_view(ts):
    """Several towns side by side: a compact card per town, then one combined listings feed."""
    ss = st.session_state
    first = ss.get("hmode", "first") == "first"
    html(f"<div class='bz-hello'>{L(f'{len(ts)} towns side by side', f'{len(ts)} pueblos lado a lado')}</div>")
    tsel_bar("v")
    need = [t for t in ts if t.lower() not in ss.get("town_cache", {})]
    jobs = [(("snap", t), (lambda t=t: town_snap(t))) for t in need] + _feed_jobs(ts, "for_sale")
    pre = {}
    if jobs:                     # every town that still needs a lookup or a listings search runs at the same time (3 at once)
        bar = st.progress(0.0, text=L("Getting the towns ready... ✨", "Preparando los pueblos... ✨"))
        res = _parallel(jobs, lambda n, m, k: bar.progress(n / m, text=L(f"Looking at {k[1]} ({n} of {m})... ✨", f"Revisando {k[1]} ({n} de {m})... ✨")))
        bar.empty()
        for k, r in res.items():
            if k[0] == "feed":
                pre[k[1]] = r if isinstance(r, dict) else {"ok": False, "error": r.__class__.__name__, "rows": []}
            elif isinstance(r, dict) and r.get("ok"):
                ss.setdefault("town_cache", {})[(towns.normalize(k[1])["name"] or k[1]).lower()] = r
    snaps = {t: _snap(t) for t in ts}
    sale = feeds_for(ts, "for_sale", pre) if listings.available() else {}
    with st.expander(L(f"📊 Compare the {len(ts)} towns: monthly cost, rules, drive", f"📊 Comparar los {len(ts)} pueblos: costo mensual, reglas, manejo"), key="mt_sum"):
        _towns_summary(list(ts), snaps, sale, first)     # kept one tap away so the first home shows on the first screen
    feed_block(list(ts), {t: (snaps.get(t) or {}).get("drive") for t in ts}, "mt")


def _open_one_town(t):
    ss = st.session_state
    ss.from_towns = tuple(tsel())
    ss.go = ("town", t, "keep")
    ss._full = True


def back_to_towns():
    ss = st.session_state
    ft = ss.get("from_towns")
    if ft and len(ft) > 1:
        st.button(L(f"← Back to your {len(ft)} towns", f"← Volver a sus {len(ft)} pueblos"), key="back_towns", type="tertiary",
                  on_click=lambda: ss.update(view=("towns", tuple(ft)), from_towns=None))


# ------------------------------------------------------------------ navigation: scroll to top on a new town/listing, phone Back, "Back to results"
NAV_JS = """
export default function(component) {
  const { data, setTriggerValue } = component;
  const d = data || {};
  const w = window;
  const conts = () => {
    const out = [document.scrollingElement, document.documentElement, document.body];
    for (const sel of ['[data-testid="stMain"]', '[data-testid="stAppViewContainer"]', 'section.main', '.main', '[data-testid="stAppScrollToBottomContainer"]'])
      document.querySelectorAll(sel).forEach(e => out.push(e));
    try { if (w.parent && w.parent !== w) { out.push(w.parent.document.scrollingElement); } } catch (e) {}
    return out.filter(Boolean);
  };
  const where = () => { let m = w.scrollY || 0; for (const c of conts()) m = Math.max(m, c.scrollTop || 0); return m; };
  const go = (y) => { for (const c of conts()) { try { c.scrollTop = y; } catch (e) {} } try { w.scrollTo(0, y); } catch (e) {}
                      try { if (w.parent !== w) w.parent.scrollTo(0, y); } catch (e) {} };
  let g = w.__bznav;
  if (!g) {
    g = w.__bznav = { seq: null, vkey: null, pos: {}, pushed: 0, ignore: 0, busy: 0, stop: false, cur: 0 };
    // remember the scroll place of the view: on a real scroll (finger / wheel / keys), and at every tap (just before the page changes).
    // A scroll that nobody did (the page getting shorter while a new view loads) is not recorded.
    g.inp = 0; g.frozen = false;
    document.addEventListener('scroll', () => { if (g.vkey && !g.busy && !g.frozen && Date.now() - g.inp < 2500) g.pos[g.vkey] = where(); }, { capture: true, passive: true });
    ['touchmove', 'wheel', 'keydown'].forEach(ev => document.addEventListener(ev, () => { g.inp = Date.now(); g.frozen = false; }, { capture: true, passive: true }));
    // a tap: keep the place as it is right now and ignore the page resizing while it redraws (until the user scrolls again or the view changes)
    ['click', 'pointerdown'].forEach(ev => document.addEventListener(ev, () => { if (g.vkey && !g.busy && !g.frozen) { g.pos[g.vkey] = where(); g.frozen = true; } }, { capture: true, passive: true }));
    ['touchstart', 'wheel', 'mousedown'].forEach(ev => document.addEventListener(ev, () => { g.stop = true; }, { capture: true, passive: true }));
    w.addEventListener('popstate', (e) => {
      const s = (e.state && typeof e.state.bz === 'number') ? e.state.bz : 0;
      const fwd = s > (g.cur || 0);
      g.cur = s;
      if (g.ignore > 0) { g.ignore--; return; }
      if (fwd) { g.ignore++; try { history.back(); } catch (x) { g.ignore--; } return; }   // phone Forward: stay put
      if (g.pushed > 0) { g.pushed--; if (g.set) g.set('back', String(Date.now())); }
    });
  }
  g.set = setTriggerValue;
  if (g.seq === null) { g.seq = d.seq; g.vkey = d.vkey; return; }
  if (d.seq === g.seq) return;
  g.seq = d.seq;
  const anc = () => { const a = d.anchor && !d.restore ? document.querySelector('.bz-restop') : null;   // top of the results, just under the search box
                      return a ? Math.max(0, Math.round(a.getBoundingClientRect().top + where() - 6)) : null; };
  let y = d.restore ? (g.pos[d.vkey] || 0) : 0;
  g.vkey = d.vkey; g.frozen = false;
  if (d.push) { try { history.pushState({ bz: d.seq }, ''); g.pushed++; g.cur = d.seq; } catch (e) {} }
  if (d.pyback && g.pushed > 0) { const n = Math.min(Number(d.pyback) || 1, g.pushed); g.pushed -= n; g.ignore++; try { history.go(-n); } catch (e) { g.ignore--; } }
  g.stop = false; g.busy = 1;
  const t0 = Date.now();
  const again = () => { if (g.stop && Date.now() - t0 > 150) { g.busy = 0; return; }
                        const ay = anc(); if (ay !== null) y = ay;
                        go(y);
                        if (Date.now() - t0 < (d.anchor || d.restore ? 3000 : 1400)) setTimeout(again, 200); else g.busy = 0; };
  again();
}
"""
_NAV = st.components.v2.component("bz_nav", js=NAV_JS)


def _vkey(v):
    return json.dumps(list(v) if v else None, default=list)


@timed('nav')
def nav_mount():
    """Count view changes (new town selection, opened listing, back). Only then does the page jump: to the top, or back to the saved place."""
    ss = st.session_state
    v = ("saved",) if ss.get("page") == "saved" else ss.get("view")      # the Saved homes list counts as a view: own history entry and own scroll place
    k = _vkey(v)
    if ss.get("go") and ss.get("nav_k") == _vkey(("saved",)) and ss.get("page") != "saved":
        k = ss.nav_k                                  # opening a home from Saved homes: the next run (the home itself) counts as the one change
    push = False
    pyback = 0
    if k != ss.get("nav_k"):
        if not (v and v[0] in ("addr", "town", "saved")):
            ss.pop("sv_chain", None)                 # left the home/town that was opened from Saved homes
        if "nav_k" in ss:
            if ss.pop("nav_isback", False):
                pyback = int(ss.pop("nav_pyback", 0) or 0)
            else:
                ss.setdefault("vstack", []).append(ss.get("nav_v"))
                ss.vstack = ss.vstack[-20:]
                push = True
        ss.nav_k, ss.nav_v = k, v
        ss.nav_seq = int(ss.get("nav_seq", 0)) + 1
        ss.nav_rs = bool(ss.pop("nav_restore", False))
        ss.nav_push, ss.nav_pb = push, pyback
    _NAV(key="bz_nav", data={"seq": ss.get("nav_seq", 0), "vkey": k, "restore": ss.get("nav_rs", False), "push": ss.get("nav_push", False),
                             "pyback": ss.get("nav_pb", 0), "anchor": bool(v) and v[0] in ("town", "towns", "addr")}, on_back_change=lambda: nav_back(False))


def nav_back(from_button=True):
    """One step back: town(s) view, listing, or the home page. Restores the scroll place there."""
    ss = st.session_state
    stk = ss.get("vstack") or []
    if not stk:
        return
    prev = stk.pop()
    was_saved = ss.get("page") == "saved"
    ss.nav_isback, ss.nav_restore, ss.nav_pyback = True, True, (1 if from_button else 0)
    ss.tpick_open = False
    if prev and prev[0] == "saved":                    # phone Back from a home that was opened from Saved homes: the list again, as it was
        ss.page = "saved"
        _restore_sel()
        ss.pop("arv_trail", None)
        return
    ss.page = "main"
    ss._keep_chain = True
    if not prev:
        ss.view = None
        return
    prev = tuple(prev)
    if was_saved and ss.get("view") and tuple(ss.view) == prev:       # leaving Saved homes for the view the user was on: it is still there
        return
    tr = list(ss.get("arv_trail") or [])
    if prev[0] == "addr" and tr and tr[-1][1] == prev[1]:      # phone Back inside a chain of comps: the "← Back to ..." button follows
        tr.pop()
        ss.arv_trail = tr
    if prev[0] == "towns":
        ss.tsel = list(prev[1])
        _tsel_url()
        ss.view = ("towns", tuple(prev[1]))
    elif prev[0] == "town":
        if prev[1] not in tsel():
            ss.tsel = [prev[1]]
            _tsel_url()
        ss.go = ("town", prev[1], "keep")
    else:
        ss.go = ("addr", prev[1], "keep")


def back_link():
    ss = st.session_state
    stk = ss.get("vstack") or []
    prev = tuple(stk[-1]) if stk and stk[-1] else None
    if not prev or prev[0] not in ("town", "towns"):
        return
    lbl = L(f"← Back to your {len(prev[1])} towns", f"← Volver a sus {len(prev[1])} pueblos") if prev[0] == "towns" else \
        L(f"← Back to results · {prev[1]}", f"← Volver a los resultados · {prev[1]}")
    st.button(lbl, key="back_res", type="tertiary", on_click=nav_back)


def _saved_idx():
    """Index in the view stack of the Saved homes entry we came from, or None."""
    stk = st.session_state.get("vstack") or []
    for i in range(len(stk) - 1, -1, -1):
        if stk[i] and stk[i][0] == "saved":
            return i
    return None


def _restore_sel():
    """Opening a saved town/home replaces the town selection; coming back to Saved homes puts the user's own selection back."""
    ss = st.session_state
    snap = ss.pop("sv_prev_sel", None)
    if snap is not None:
        ss.tsel = list(snap.get("tsel") or [])
        _tsel_url()
        if snap.get("from_towns"):
            ss.from_towns = tuple(snap["from_towns"])


def from_saved():
    """True while the open home/town was opened from Saved homes (also after hopping to comps from it)."""
    ss = st.session_state
    v = ss.get("view")
    return bool(ss.get("sv_chain")) and ss.get("page") != "saved" and bool(v) and v[0] in ("addr", "town") and _saved_idx() is not None


def back_to_saved():
    """Back to the Saved homes list in one tap, however many comps were opened since. The list comes back as it was left
    (scroll place, sort, filter, open sections: kept by _keep_ui + bz_nav) and nothing the user chose on the main page is touched."""
    ss = st.session_state
    stk = list(ss.get("vstack") or [])
    i = _saved_idx()
    n = (len(stk) - i) if i is not None else 0
    if i is not None:
        ss.vstack = stk[:i]
    ss.nav_isback, ss.nav_restore, ss.nav_pyback = True, True, n
    ss.tpick_open = False
    ss.pop("arv_trail", None)
    ss.pop("sv_chain", None)
    _restore_sel()
    ss.page = "saved"


def back_to_search():
    """'← Back to search' on the Saved page: one step back in the app's own history (the view the user was on), else the home page."""
    ss = st.session_state
    stk = ss.get("vstack") or []
    if stk and not (stk[-1] and stk[-1][0] == "saved"):
        nav_back()
    else:
        ss.page = "main"


def _remove_town(t):
    _set_tsel([x for x in tsel() if x != t])


@timed('town_bar')
def town_bar(view, here=None):
    """Always-visible bar on town, feed and home views: current towns with ✕, and a big Change town button that opens the picker right here."""
    ss = st.session_state
    st.markdown("<div class='bz-restop'></div>", unsafe_allow_html=True)
    back_link()
    with st.container(key="townbar", horizontal=True, vertical_alignment="center", gap="small"):
        if from_saved():
            st.button(L("← Back to Saved homes", "← Volver a Saved homes"), key="back_saved", width="stretch", on_click=back_to_saved)
        s_ = tsel() if view[0] in ("town", "towns") else []
        if s_:
            for t in s_:
                st.button(f"{t}  ✕", key=f"tbx_{_slug(t)}", on_click=_remove_town, args=(t,), help=L(f"Remove {t}", f"Quitar {t}"))
        elif here:
            html(f"<div class='bz-tsel'>📍 <b>{H.escape(here)}</b></div>")
        op = bool(ss.get("tpick_open"))
        st.button((L("✓ Done", "✓ Listo") if op else (L("📍 Change town", "📍 Cambiar ciudad") if len(s_) <= 1 else L("📍 Change towns", "📍 Cambiar ciudades"))),
                  key="tb_change", type="primary", width="stretch", on_click=lambda: ss.update(tpick_open=not op))
    if ss.get("tpick_open"):
        with st.container(key="tpicker", border=True):
            town_picker()


@timed('picker')
def town_picker():
    ss = st.session_state
    ss.setdefault("pk_mode", ss.get("hmode", "first"))
    md_ = st.segmented_control(L("Which towns", "Qué pueblos"), ["first", "next"], key="pk_mode", required=True, label_visibility="collapsed", width="stretch",
                               format_func=lambda k: L("🏙️ Near the city", "🏙️ Cerca de la ciudad") if k == "first" else L("🧭 Anywhere", "🧭 Donde sea"))
    town_chips(md_ or "first")


@st.cache_data(ttl=6 * 3600, max_entries=64, show_spinner=False)
def _rank_shared(hm, price, rate):
    return C.town_rank(hm, price, rate)


@timed('ranking')
def town_ranking(hm):
    ss = st.session_state
    st.markdown(f"#### {L('🏆 Best towns for your first home' if hm == 'first' else '🏆 Towns by the numbers', '🏆 Mejores pueblos para su primera casa' if hm == 'first' else '🏆 Pueblos según los números')}")
    price = st.segmented_control(L("Price you're looking at", "Precio que está mirando"), C.PRICE_CHIPS, key="rank_price", default=C.PRICE_CHIPS[1], required=True, format_func=kmoney)
    rk = _rank_shared(hm, int(price), fha_rate())
    cap(L(f"What you'd pay a month on a {kmoney(price)} 2-family, renting the other unit at HUD's fair rent for the town (2 bd). "
                 + ("Ranked by drive time plus monthly cost." if hm == "first" else "Ranked by monthly cost; drive shown, not counted.") + " Tap a town.",
                 f"Lo que pagaría al mes en una casa de 2 familias de {kmoney(price)}, alquilando la otra unidad a la renta justa de HUD del pueblo (2 hab). "
                 + ("Ordenado por tiempo en carro más costo mensual." if hm == "first" else "Ordenado por costo mensual; el trayecto se muestra pero no cuenta.") + " Toque un pueblo."))
    for i, x in enumerate(rk["rows"][:12], 1):
        d = x["drive"]
        p = x["pay_2fam"]
        pay = (L(f"you pay {money(p)}/mo", f"paga {money(p)}/mes") if p >= 0 else L(f"you earn {money(-p)}/mo", f"gana {money(-p)}/mes")) if p is not None else "?"
        sr = S.airbnb_line(towns_rules(x["town"]), "owner")[0]
        lab = f"{i}. {x['town']} · 🚗 {d['min']}-{d['rush'][1]} min · {pay} · {sr}" + (" · ℹ️ " + L("safety note", "nota de seguridad") if x.get("caution") else "")
        st.button(lab, key=f"rk_{hm}_{i}", width="stretch", on_click=lambda t=x["town"]: st.session_state.update(go=("town", t)))
    st.caption(L("Homes at this price may be rare in some towns. Drive: typical, not live; the second number is a busy rush hour.",
                 "En algunos pueblos es difícil encontrar casas a este precio. Trayecto: típico, no en vivo; el segundo número es hora pico."))


def towns_rules(t):
    from bellazu.sources import str_rules as _sr
    return _sr.rules_for(t)


# ------------------------------------------------------------------ saved homes (favorites): hearts, the list, backup, sync
from datetime import datetime                                     # noqa: E402
from zoneinfo import ZoneInfo                                     # noqa: E402

ET = ZoneInfo("America/New_York")
STATUS_OPTS = ["interested", "toured", "offer", "no"]
STATUS_LBL = {"interested": ("💗 Interested", "💗 Me interesa"), "toured": ("👀 Toured", "👀 La visité"),
              "offer": ("📝 Offer", "📝 Oferta"), "no": ("✖️ Not for me", "✖️ No es para mí")}
MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
FEED_TYPE_LBL = {"condo": ("Condo", "Condo"), "2fam": ("2-family+", "2+ familias"), "house": ("House", "Casa"), "other": ("Home", "Vivienda")}


def _today():
    return datetime.now(ET).strftime("%Y-%m-%d")


def _date_txt(iso):
    try:
        y, m, d = (int(x) for x in str(iso)[:10].split("-"))
        return f"{d} {MON_ES[m - 1]} {y}" if ES() else f"{MON_EN[m - 1]} {d}, {y}"
    except Exception:
        return str(iso or "")


def _norm_addr(a):
    return re.sub(r"[^a-z0-9]", "", str(a or "").lower())


def find_home(addr=None, lid=None):
    """The saved entry for this listing id or address, if any (so the feed card and the opened listing share one heart)."""
    for k, x in sv()["items"].items():
        if x.get("kind") != "home":
            continue
        if lid and str(x.get("listing_id") or "") == str(lid):
            return k
        if addr and _norm_addr(x.get("addr")) == _norm_addr(addr):
            return k
    return None


def _thumb(u):
    return re.sub(r"od-w1024_h768\.jpg$", "rd-w480_h360.jpg", u) if isinstance(u, str) else None


def _facts_line(beds, baths, sqft, type_lbl, hoa, rent=False):
    en, es = [], []
    if beds is not None:
        en.append(f"{beds} bd"), es.append(f"{beds} hab")
    if baths:
        en.append(f"{float(baths):g} ba"), es.append(f"{float(baths):g} baño{'' if float(baths) == 1 else 's'}")
    if sqft:
        en.append(f"{int(sqft):,} ft²"), es.append(f"{int(sqft):,} ft²")
    if type_lbl:
        en.append(type_lbl[0]), es.append(type_lbl[1])
    if isinstance(hoa, dict) and not rent:
        en.append(hoa_txt(hoa, True, False)), es.append(hoa_txt(hoa, True, True))
    elif hoa and not rent:
        en.append(f"HOA {money(hoa)}/mo"), es.append(f"HOA {money(hoa)}/mes")
    return " · ".join(en), " · ".join(es)


def _cols_snap(out, first):
    return [{k: (list(c[k]) if isinstance(c[k], tuple) else c[k]) for k in ("key", "title", "pay_lbl", "pay", "sub", "badge", "star")} for c in C.labels(out, first)]


def _new_entry(iid, kind, title):
    t = saves.now_ms()
    return {"id": iid, "kind": kind, "title": title, "saved": _today(), "saved_ms": t, "updated": t, "status": "interested", "note": ""}


def _caution(town):
    lvl, c = C.town_caution(town)
    return list(c) if c else None


def _listing_facts(h, d=None):
    """Facts from a feed listing (plus its detail call, if we have it), in the shape facts_for() keeps."""
    fo = {}
    if h.get("price"):
        fo["price"] = int(h["price"])
    hi = listings.hoa_info(h, d if (d and d.get("ok")) else None)
    if hi["state"] in ("real", "est", "none"):
        fo["hoa"] = int(hi["fee"] or 0)
        fo["hoa_src"] = hi["state"]
        fo["hoa_info"] = hi
        inc = hi.get("inc") or []
        ui = [k for k in ("taxes", "parking", "internet") if k in inc] + (["heat"] if "heat/hot water" in inc else []) + (["water"] if "water" in inc else []) + \
             (["electric", "gas"] if "utilities" in inc else [])
        if hi.get("kind") == "coop" and hi["state"] in ("real", "est") and "taxes" not in ui:
            ui.append("taxes")                  # NJ co-op maintenance pays the building's taxes: never count them twice
        if ui:
            fo["inc"] = ui
    if d and d.get("ok") and d.get("taxes_annual"):
        fo["taxes"] = fo["taxes_listing"] = int(d["taxes_annual"])
    if h.get("kind") in LISTING_TYPE:
        fo["type"] = "co-op" if (h.get("type") == "coop" or hi.get("kind") == "coop") else LISTING_TYPE[h["kind"]]   # a 'condo' whose fee pays the taxes is a co-op
    if h.get("beds") is not None:
        fo["beds"] = int(h["beds"])
    if h.get("baths"):
        fo["baths"] = float(h["baths"])
    return fo


def entry_from_feed(iid, h, rent):
    """Snapshot of a feed card. For-sale homes get quick numbers from the town's averages (no API call); opening the home later upgrades them."""
    ss = st.session_state
    a = ss.get("town") or {}
    tk = str(h.get("_t") or h.get("town") or "").lower()
    if tk and (ss.get("town_cache") or {}).get(tk):          # combined feed: use the card's own town
        a = ss.town_cache[tk]
    first = ss.get("hmode", "first") == "first"
    tl = list(FEED_TYPE_LBL.get(h.get("kind"), FEED_TYPE_LBL["other"]))
    hm_ = None if rent else home_money(h)
    fl = _facts_line(h.get("beds"), h.get("baths"), h.get("sqft"), tl, (hm_ or {}).get("hoa") or h.get("hoa_monthly"), rent)
    e = _new_entry(iid, "home", h["address"])
    photos = [p_ for p_ in (h.get("photos") or []) if p_]
    e.update(addr=h["address"], town=h.get("town") or a.get("town"), price=h.get("price"), rent=bool(rent), beds=h.get("beds"), baths=h.get("baths"),
             sqft=h.get("sqft"), hoa=h.get("hoa_monthly"), type_lbl=tl, facts_line_en=fl[0], facts_line_es=fl[1], photo=h.get("photo") or _thumb(photos[0] if photos else None),
             photos=photos[:8], url=h.get("url"), listing_id=str(h.get("id") or ""), broker=h.get("broker"), facts_over=_listing_facts(h),
             safety=_caution(h.get("town") or a.get("town")))
    if not rent and h.get("price") and a.get("ok"):
        try:
            size = "2fam" if h.get("kind") == "2fam" else str(min(max(int(h.get("beds") or 2), 1), 3))
            hm = home_money(h) or {}
            hoa = float(((hm.get("hoa") or {}).get("fee")) or 0)
            base = C.base_from_town(a, int(h["price"]), size, loan=loan_prof())
            base["total_cost"] += hoa
            base["piti"] = (base.get("piti") or 0) + hoa
            out = C.compare(base, C.default_sel(base))
            e.update(cols=_cols_snap(out, first), legal=list(C.airbnb_badge(out.get("airbnb_allowed"), out.get("days30", 30))), nums_src="town")
        except Exception:
            pass
    return e


def entry_from_property(iid, r, out, first, addr):
    g = (st.session_state.get("gallery") or {}).get((addr or "").strip().lower()) or {}
    f = r.get("facts") or {}
    own = (f.get("ownership") or "").lower()
    fo = dict(facts_for(addr))
    tl = list(UI_TYPES[fo["type"]]) if fo.get("type") in UI_TYPES else (list(TYPE_LBL[own]) if own in TYPE_LBL else None)
    fl = _facts_line(f.get("beds"), f.get("baths"), f.get("sqft"), tl, prop_hoa(r, addr) or f.get("hoa_monthly"))
    photos = [p_ for p_ in (g.get("photos") or []) if p_]
    e = _new_entry(iid, "home", r.get("address") or addr)
    e.update(addr=addr, town=r.get("town"), price=f.get("price"), rent=False, beds=f.get("beds"), baths=f.get("baths"), sqft=f.get("sqft"),
             hoa=f.get("hoa_monthly"), taxes=f.get("taxes_annual"), type_lbl=tl, facts_line_en=fl[0], facts_line_es=fl[1],
             photo=_thumb(photos[0]) if photos else None, photos=photos[:8], url=g.get("url"), listing_id=str(g.get("id") or ""), broker=g.get("broker"),
             facts_over=fo, safety=_caution(r.get("town")))
    if out:
        e.update(cols=_cols_snap(out, first), legal=list(C.airbnb_badge(out.get("airbnb_allowed"), out.get("days30", 30))), nums_src="full")
    return e


def entry_from_town(iid, a, price, size, out, first):
    t = a["town"]
    size_lbl = ("2-family", "2 familias") if size == "2fam" else (f"{size} bd", f"{size} hab")
    e = _new_entry(iid, "town", f"{t} · {kmoney(price)} · {size_lbl[0]}")
    e.update(town=t, price=price, size=size, rent=False, type_lbl=list(size_lbl), facts_line_en=f"Town estimate · {size_lbl[0]}",
             facts_line_es=f"Estimado del pueblo · {size_lbl[1]}", photo=None, photos=[], url=None, safety=_caution(t))
    if out:
        e.update(cols=_cols_snap(out, first), legal=list(C.airbnb_badge(out.get("airbnb_allowed"), out.get("days30", 30))), nums_src="town")
    return e


def _from_stash(iid, which):
    a = st.session_state.get(f"_sv_stash_{which}")
    if not a:
        return None
    return entry_from_property(iid, *a) if which == "prop" else entry_from_town(iid, *a)


@timed('cb:heart')
def _sv_toggle(iid, builder, *args):
    ss = st.session_state
    items = sv()["items"]
    if iid in items:
        ss.sv_undo = items.pop(iid)
        sv()["removed"][iid] = saves.now_ms()
        st.toast(L("Removed from your saved homes", "Quitada de sus casas guardadas"), icon="💔")
    else:
        try:
            e = builder(iid, *args)
        except Exception:
            e = None
        if not e:
            st.toast(L("Sorry, that didn't save. Try again.", "Perdón, no se guardó. Intente otra vez."), icon="⚠️")
            return
        items[iid] = e
        sv()["removed"].pop(iid, None)
        st.toast(L("Saved! Find it under ♥ Saved at the top.", "¡Guardada! La encuentra en ♥ Guardadas arriba."), icon="💗")
    _sv_touch()


def heart(iid, key, builder, args, wide=False):
    on = iid in sv()["items"]
    st.button(L("♥ Saved", "♥ Guardada") if on else L("♡ Save", "♡ Guardar"), key=f"{'svon' if on else 'svoff'}_{key}", on_click=_sv_toggle,
              args=(iid, builder, *args), width="stretch" if wide else "content")


def _sv_key(iid):
    return re.sub(r"[^A-Za-z0-9]", "_", iid)[:48]


def _sv_set(iid, field, wkey):
    x = sv()["items"].get(iid)
    v = st.session_state.get(wkey)
    if x is None or v is None:
        return
    x[field] = v if field != "note" else str(v)[:1000]
    x["updated"] = saves.now_ms()
    _sv_touch()


def _sv_remove(iid):
    items = sv()["items"]
    if iid in items:
        st.session_state.sv_undo = items.pop(iid)
        sv()["removed"][iid] = saves.now_ms()
        _sv_touch()


def _sv_undo():
    ss = st.session_state
    x = ss.pop("sv_undo", None)
    if x:
        x["updated"] = saves.now_ms()
        sv()["items"][x["id"]] = x
        sv()["removed"].pop(x["id"], None)
        _sv_touch()


def _sv_open(iid):
    """Reopen the full analysis from the snapshot (no listing re-fetch)."""
    ss = st.session_state
    x = sv()["items"].get(iid)
    if not x:
        return
    ss.page = "main"
    ss.sv_chain, ss._keep_chain = iid, True            # the detail view gets a "← Back to Saved homes" button
    ss.sv_prev_sel = {"tsel": list(tsel()), "from_towns": list(ss.get("from_towns") or [])}
    if x.get("kind") == "town":
        sid = "t_" + safe_name(x["town"])[:24]
        if x.get("price") in C.PRICE_CHIPS:
            ss[f"tp_{sid}"] = x["price"]
        elif x.get("price"):
            ss[f"tp_{sid}"], ss[f"tpo_{sid}"] = "other", int(x["price"])
        if x.get("size") in C.TOWN_SIZES:
            ss[f"ts_{sid}"] = x["size"]
        ss.go = ("town", x["town"])
        return
    addr = x.get("addr") or x.get("title")
    if x.get("facts_over"):
        facts_for(addr).update({k: v for k, v in x["facts_over"].items() if v is not None})
    if x.get("photos") or x.get("url"):
        ss.setdefault("gallery", {})[addr.strip().lower()] = {"photos": x.get("photos") or [], "url": x.get("url"), "broker": x.get("broker"),
                                                              "price": x.get("price"), "hoa": x.get("hoa"), "id": x.get("listing_id")}
    ss.go = ("addr", addr)


def _cmp_html(cols, extra_cls=""):
    cells = ""
    for c in cols or []:
        earn = (c.get("pay_lbl") or [""])[0] == "You earn"
        cells += (f"<div class='bz-col{' star' if c.get('star') else ''}'><div class='h'>{H.escape(P(c['title']))}</div><div class='l'>{H.escape(P(c['pay_lbl']))}</div>"
                  f"<div class='n{' earn' if earn else ''}'>{H.escape(str(c.get('pay') or '—'))}</div><div class='s'>{H.escape(P(c['sub']))}</div></div>")
    return f"<div class='bz-cmp {extra_cls}'>{cells}</div>" if cells else ""


def _sv_exp_changed(key):
    ss = st.session_state
    ss.setdefault("sv_exp", {})[key] = bool(ss.get(key))


def _sv_expander(label, key):
    """An expander on a saved card that remembers if it was open, so the list comes back the way it was left after the user opens a home."""
    ss = st.session_state
    if key not in ss and ss.get("sv_exp", {}).get(key):
        ss[key] = True
    return st.expander(label, key=key, on_change=_sv_exp_changed, args=(key,))


@timed('saved_card')
def saved_card(x):
    """Calm saved card: photo carousel with the price on it, one facts line, then tap-to-open details and notes."""
    k = _sv_key(x["id"])
    with st.container(key=f"svcard_{k}"):
        pic = x.get("photo") if str(x.get("photo") or "").startswith("https://") else None
        phs = [u for u in (x.get("photos") or []) if str(u).startswith("https://")] or ([pic] if pic else [])
        price = (money(x["price"]) + (L("/mo", "/mes") if x.get("rent") else "")) if x.get("price") else ""
        fl = x.get("facts_line_es" if ES() else "facts_line_en") or ""
        src = {"full": L("full check", "revisión completa"), "town": L("quick estimate from town averages", "estimado rápido con promedios del pueblo")}.get(x.get("nums_src"), "")
        title = x.get("addr") or x.get("title") or ""
        if x.get("kind") == "home" and phs:
            h = {"id": x.get("listing_id") or "", "photo": phs[0], "photos": phs, "photo_count": len(phs), "price": x.get("price"),
                 "url": x.get("url"), "new": False, "price_cut": None}
            carousel(h, f"svcz_{k}", bool(x.get("rent")), None, on_open=(lambda i=x["id"]: _sv_open(i)), more_ok=False)
        elif price:
            html(f"<div class='bz-price' style='margin-top:.2rem'>{H.escape(price)}</div>")
        html(f"<div class='bz-svh'>{H.escape(title)}" + (f"<br><span class='x'>{H.escape(fl)}</span>" if fl else "") + "</div>")
        with _sv_expander(L("Details", "Detalles"), f"svdt_{k}"):
            st.caption(f"♥ {L('Saved', 'Guardada')} {_date_txt(x.get('saved'))}" + (f" · {src}" if src and x.get("cols") else ""))
            if x.get("cols"):
                html(f"<div class='bz-lbl' style='margin-top:.3rem'>{L('Each month, when saved', 'Cada mes, al guardarla')}</div>" + _cmp_html(x["cols"], "bz-sv-nums"))
            if x.get("legal"):
                html(f"<div class='bz-sv-b'>{H.escape(P(x['legal']))}</div>")
            if x.get("safety"):
                html(f"<div class='bz-sv-b'>ℹ️ {H.escape(P(x['safety']))}</div>")
            if x.get("kind") == "home" and not x.get("rent"):
                fa = fha_for_saved(x)
                if fa:
                    html(f"<div class='bz-sv-b'>{H.escape(fha_badge_short(fa))}</div>")
            if x.get("town") and x.get("kind") in ("home", "town"):
                st.markdown(f"**{L('What similar places rent for', 'Lo que se alquila algo parecido')}**")
                b = x.get("beds") if x.get("kind") == "home" else (2 if x.get("size") == "2fam" else int(x.get("size") or 2))
                if x.get("kind") == "home" and (x.get("type_lbl") or [""])[0].startswith("2") and b:
                    b = 2
                tk = (x.get("type_lbl") or [""])[0].lower()
                rent_comps_box("sv_" + k, x["town"], b, "condo" if tk in ("condo", "co-op") else "house" if tk == "house" else None, None, None,
                               None, None, _hud_for(x["town"], b), None, None, None, None)
        with _sv_expander(L("My status and notes", "Mi estado y notas"), f"svnx_{k}"):
            st.pills(L("Status", "Estado"), STATUS_OPTS, key=f"svst_{k}", default=x.get("status") or "interested", required=True,
                     format_func=lambda s_: P(STATUS_LBL[s_]), on_change=_sv_set, args=(x["id"], "status", f"svst_{k}"))
            st.text_area(L("My notes", "Mis notas"), value=x.get("note") or "", key=f"svnt_{k}", height=80, max_chars=1000,
                         placeholder=L("e.g. loved the kitchen, street is noisy", "p. ej. me encantó la cocina, la calle es ruidosa"),
                         on_change=_sv_set, args=(x["id"], "note", f"svnt_{k}"))
        row = st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center", key=f"svrow_{k}")
        with row:
            if not x.get("rent"):
                st.button(L("Open my numbers", "Abrir mis números"), key=f"svop_{k}", on_click=_sv_open, args=(x["id"],), type="tertiary")
            if str(x.get("url") or "").startswith("http"):
                st.link_button(L("Listing ↗", "Anuncio ↗"), x["url"], type="tertiary")
            st.button(L("Remove", "Quitar"), key=f"svrm_{k}", on_click=_sv_remove, args=(x["id"],), type="tertiary")


def _sv_wait_cloud():
    """Don't block the page on the online copy: show the list now, and _sv_poll redraws it when the background check lands."""
    _sv_pull_merged(apply_lang=False)
    if saves.cloud_busy():
        st.session_state.sv_polling = time.time()


@st.fragment(run_every=1.5)
def _sv_poll():
    """While the online copy is syncing in the background: check every 1.5 s, redraw the page once when it brings something new."""
    ss = st.session_state
    t = ss.get("sv_polling")
    if not t:
        return
    if saves.cloud_busy() and time.time() - t < 30:
        return
    ss.sv_polling = None
    m = saves.cloud_merged()
    if m and not saves.same(saves.merge(sv(), m), sv()):
        st.rerun(scope="app")


def _sv_status_line():
    if not saves.cloud_available():
        return L("⚠️ The online copy is off right now, so the list is only in this browser. Download a backup file to be safe.",
                 "⚠️ La copia en línea está apagada ahora; la lista solo está en este navegador. Descargue un archivo de respaldo por seguridad.")
    s_ = saves.cloud_status()
    if saves.cloud_busy():
        return L("Kept on this device · ⏳ saving the online copy...", "Guardada en este dispositivo · ⏳ guardando la copia en línea...")
    if s_ and s_.get("ok"):
        t = datetime.fromtimestamp(s_["t"], ET).strftime("%-I:%M %p")
        return L(f"✓ Saved online (encrypted), updated {t} ET. The same list shows on any phone or computer where you enter the passcode.",
                 f"✓ Guardada en línea (cifrada), actualizada {t} ET. La misma lista aparece en cualquier teléfono o computadora donde escriba el código de entrada.")
    if s_ and not s_.get("ok"):
        return L("Kept on this device. ⚠️ The online copy couldn't be reached just now; we'll try again on your next change.",
                 "Guardada en este dispositivo. ⚠️ No pudimos llegar a la copia en línea; lo intentaremos en su próximo cambio.")
    return L("✓ Saved online (encrypted) and on this device.", "✓ Guardada en línea (cifrada) y en este dispositivo.")


def backup_block():
    ss = st.session_state
    st.markdown(f"#### 💾 {L('Back up my list', 'Respaldar mi lista')}")
    st.caption(L("If this browser's data gets cleared, a backup file brings everything back. It also opens on its own as a readable list.",
                 "Si se borran los datos de este navegador, un archivo de respaldo lo recupera todo. También se abre solo como una lista para leer."))
    if sv()["items"]:
        st.download_button(L("⬇️ Download my list (backup file)", "⬇️ Descargar mi lista (archivo de respaldo)"), (lambda x=json.loads(json.dumps(sv())), lg_=("es" if ES() else "en"): saves.export_html(x, lg_).encode()),
                           L(f"BellaZu_saved_homes_{_today()}.html", f"BellaZu_casas_guardadas_{_today()}.html"), "text/html", key="sv_dl", width="stretch", on_click="ignore", type="primary")
    st.markdown(f"<style>:root{{--bz-up:'{L('Choose the file', 'Elegir el archivo')}'}}</style>", unsafe_allow_html=True)   # Streamlit's own button text is English-only
    up = st.file_uploader(L("Restore from a backup file", "Recuperar desde un archivo de respaldo"), type=["html", "htm", "json"], key=f"sv_up_{ss.get('sv_upn', 0)}")
    if up is not None:
        d = saves.parse_import(up.getvalue())
        if d is None:
            st.warning(L("That file isn't a BellaZu backup. Pick the file named BellaZu_saved_homes_….", "Ese archivo no es un respaldo de BellaZu. Elija el archivo llamado BellaZu_casas_guardadas_…."))
        else:
            cur = sv()
            before = len(cur["items"])
            for x in d["items"].values():          # a restore brings homes back even if they were removed here later
                if x["id"] not in cur["items"]:
                    x["updated"] = max(int(x.get("updated", 0)), int(cur["removed"].get(x["id"], 0)) + 1)
            ss.sv = saves.merge(cur, dict(d, removed={}, sync=None))
            _sv_touch()
            n = len(ss.sv["items"]) - before
            ss.sv_msg = ("ok", L(f"Restored ✓ {n} home{'s' if n != 1 else ''} added, {len(ss.sv['items'])} in your list.",
                                 f"Recuperada ✓ {n} casa{'s' if n != 1 else ''} agregada{'s' if n != 1 else ''}, {len(ss.sv['items'])} en su lista."))
            ss.sv_msg_t = time.time()
            ss.sv_upn = int(ss.get("sv_upn", 0)) + 1
            st.rerun()


@timed('saved_page')
def saved_page():
    ss = st.session_state
    nav_mount()
    st.button(L("← Back to search", "← Volver a buscar"), key="sv_back", type="tertiary", on_click=back_to_search)
    html(f"<div class='bz-hello'>{L('My saved homes', 'Mis casas guardadas')}</div>")
    m = ss.get("sv_msg")
    if m and time.time() - ss.get("sv_msg_t", 0) < 12:
        (st.success if m[0] == "ok" else st.warning)(m[1])
    if not ss.get("sv_loaded"):
        ss.sv_wait = int(ss.get("sv_wait", 0)) + 1
        if ss.sv_wait > 3:
            st.warning(L("This browser isn't keeping your list (private mode or storage turned off). Download a backup file to keep it.",
                         "Este navegador no está guardando su lista (modo privado o almacenamiento apagado). Descargue un archivo de respaldo para conservarla."))
        else:
            st.caption(L("Loading your list from this device...", "Cargando su lista de este dispositivo..."))
    elif ss.get("sv_storage_ok") is False:
        st.warning(L("This browser isn't keeping your list (private mode or storage turned off). Download a backup file to keep it.",
                     "Este navegador no está guardando su lista (modo privado o almacenamiento apagado). Descargue un archivo de respaldo para conservarla."))
    _sv_wait_cloud()
    items = list(sv()["items"].values())
    st.caption(_sv_status_line())
    if ss.get("sv_undo"):
        st.button(L(f"↩ Undo remove: {ss.sv_undo.get('addr') or ss.sv_undo.get('title')}", f"↩ Deshacer: {ss.sv_undo.get('addr') or ss.sv_undo.get('title')}"),
                  key="sv_undo_btn", on_click=_sv_undo, type="tertiary")
    if not items:
        html(f"<div class='bz-ask'>♡ {L('Nothing saved yet. Tap ♡ Save on any home, address or town and it shows up here with its photo, price and monthly numbers.', 'Aún no hay nada guardado. Toque ♡ Guardar en cualquier casa, dirección o pueblo y aparecerá aquí con su foto, precio y números del mes.')}</div>")
    else:
        sort = st.segmented_control(L("Sort", "Ordenar"), ["new", "low", "high"], key="sv_sort", default="new", required=True, width="stretch",
                                    format_func=lambda k: {"new": L("Newest", "Más nuevas"), "low": L("Price ↑", "Precio ↑"), "high": L("Price ↓", "Precio ↓")}[k])
        cnt = {s_: sum(1 for x in items if (x.get("status") or "interested") == s_) for s_ in STATUS_OPTS}
        filt = st.pills(L("Show", "Mostrar"), ["all"] + [s_ for s_ in STATUS_OPTS if cnt[s_]], key="sv_filt", default="all", required=True,
                        format_func=lambda s_: f"{L('All', 'Todas')} ({len(items)})" if s_ == "all" else f"{P(STATUS_LBL[s_])} ({cnt[s_]})")
        if filt and filt != "all":
            items = [x for x in items if (x.get("status") or "interested") == filt]
        if sort == "new":
            items.sort(key=lambda x: -int(x.get("saved_ms") or 0))
        else:
            items.sort(key=lambda x: (x.get("price") is None, (x.get("price") or 0) * (1 if sort == "low" else -1)))
        listings.prefetch_details([x.get("listing_id") for x in items], limit=12)   # Pro only: saved homes' galleries, side thread
        for x in items:
            saved_card(x)
        st.caption(L("Numbers are a snapshot from the day you saved. Prices and rules can change; open the home again for today's numbers.",
                     "Los números son una foto del día en que guardó. Los precios y las reglas pueden cambiar; abra la casa otra vez para ver los números de hoy."))
    backup_block()





# ------------------------------------------------------------------ the one page
@timed('main')
def main_page():
    ss = st.session_state
    nav_mount()
    hm = st.segmented_control(L("Mode", "Modo"), ["first", "next"], key="hmode", default="first", required=True, label_visibility="collapsed", width="stretch",
                              format_func=lambda k: L("🏙️ My first home, near the city", "🏙️ Mi primera casa, cerca de la ciudad") if k == "first"
                              else L("🧭 Next homes, anywhere", "🧭 Próximas casas, donde sea"))
    view = ss.get("view")
    if not view:
        header_hero()
    search_block()
    res_box = st.container()
    if ss.pop("tsel_boot", False) and not view and tsel():      # opened with ?towns=...
        if len(tsel()) == 1:
            ss.go = ("town", tsel()[0])
        else:
            ss.view = view = ("towns", tuple(tsel()))
    go = ss.pop("go", None)
    keep_chain = ss.pop("_keep_chain", False)
    if go and not keep_chain:
        ss.pop("sv_chain", None)                                 # a new search / town / listing: no longer "opened from Saved homes"
    _hb = ss.pop("home_boot", None)
    if _hb and not go and not view:                              # deep link: ?home=<id> (the saved list of homes carries the town and the row)
        _row = listings.find_row(_hb)
        if _row:
            _tn = towns.normalize(_row.get("town") or "")
            if _tn.get("name") and _tn["name"] != "New York City":
                ss.tsel = [_tn["name"]]
            go = ("listing", dict(_row, _t=_tn.get("name") or _row.get("town")))
        else:
            st.caption(L("That home link isn't in the saved lists any more. Search the town to find it.", "Ese enlace ya no está en las listas guardadas. Busque el pueblo para encontrarla."))
    if ss.pop("auto_go", False):
        go = ("addr", ss.get("addr"))
    if go and go[0] == "addtown":
        _set_tsel(tsel() + [go[1]])
        st.rerun()
    if go and go[0] == "listing":
        run_listing(go[1], res_box)
        st.rerun()
    elif go:
        keep = len(go) > 2 and go[2] == "keep"
        go = tuple(go[:2])
        ss.view = go
        if not keep:
            ss.pop("from_towns", None)
            ss.pop("arv_trail", None)
            if go[0] == "town":
                tn_ = towns.normalize(go[1])
                ss.tsel = [tn_["name"] or go[1]] if tn_.get("match") in ("exact", "alias", "fuzzy") else []
                _tsel_url()
        if go[0] == "addr":
            ss.prop_addr = go[1]
            run_home(go[1], res_box)
        else:
            run_town(go[1], res_box)
        st.rerun()
    elif view and view[0] == "addr" and ss.get("prop") and ss.prop.get("ok") and \
            json.dumps([ss.prop_addr.strip().lower(), home_opts(ss.prop_addr)], sort_keys=True, default=str) != ss.get("prop_key"):
        run_home(ss.prop_addr, res_box)
        st.rerun()
    with res_box:
        if view and view[0] in ("addr", "town", "towns"):
            town_bar(view, here=(ss.get("prop") or {}).get("town") if view[0] == "addr" else None)
        if view and view[0] == "towns":
            show_towns_view(list(view[1]))
        elif view and view[0] == "addr":
            r = ss.get("prop")
            if r and not r.get("ok"):
                not_found(r)
            elif r:
                show_property(r)
        elif view and view[0] == "town":
            a = ss.get("town")
            if a and not a.get("ok"):
                town_problem(a)
            elif a:
                show_town_view(a)
    if view:
        st.divider()
    if not view:
        ss.tpick_open = False
    if not ss.get("tpick_open"):
        town_chips(hm)
    rec = ss.get("recent", [])[:3]
    if rec:
        st.markdown(f"<div class='bz-lbl'>{L('Recent', 'Recientes')}</div>", unsafe_allow_html=True)
        for i, x in enumerate(rec):
            st.button(f"↺  {x}", key=f"rec_{i}", on_click=lambda x=x: st.session_state.update(go=("addr", x)), width="stretch")
    row = st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center")
    with row:
        settings_popover()
        if example() and not view:
            st.button(L("Try an example", "Probar un ejemplo"), key="ex_btn", on_click=use_example, type="tertiary")
    if not view:
        how_it_works()
        town_ranking(hm)
        marquee()


# ------------------------------------------------------------------ page
settings_defaults()
_keep_ui()
if st.session_state.get("authed") and st.session_state.get("sv_loaded") and not st.session_state.get("picks_seeded"):
    st.session_state.picks_seeded = True           # once per session, after the browser + online copies merged: the shared picked homes join the list
    _n0 = len(sv()["items"])
    _seed_picks()
    if len(sv()["items"]) != _n0:
        _sv_touch()                                # write to this browser and the online copy
if st.session_state.get("page") == "saved":
    saved_page()
else:
    main_page()

st.write("")
with st.expander(L("About BellaZu", "Sobre BellaZu"), icon="ℹ️"):
    md(L("BellaZu helps first-time buyers in North Jersey compare buying, renting out and Airbnb or 30+ day stays for a home or a town, using free public data "
         "(Inside Airbnb, HUD, Census, Freddie Mac, OpenStreetMap and OSRM for drive times, Craigslist, realtor.com rentals via Realty in US, Rent.com where it answers, Redfin and, if set up, RentCast).\n\n"
         "**Privacy:** what you type stays in this browser session. Saved homes are kept in this browser and in an encrypted online copy that opens only with the passcode. Nothing is saved to an account.\n\n"
         "**Important:** these are estimates, not financial, legal or lending advice.",
         "BellaZu ayuda a primeros compradores en el norte de NJ a comparar comprar, alquilar y Airbnb o estadías de 30+ días para una casa o un pueblo, con datos públicos gratuitos "
         "(Inside Airbnb, HUD, Censo, Freddie Mac, OpenStreetMap, Craigslist, alquileres de realtor.com vía Realty in US, Rent.com donde responde, Redfin y, si está configurado, RentCast).\n\n"
         "**Privacidad:** lo que escribe se queda en esta sesión del navegador. Las casas guardadas se quedan en este navegador y en una copia en línea cifrada que solo se abre con el código de entrada. No se guarda en ninguna cuenta.\n\n"
         "**Importante:** son estimados, no asesoría financiera, legal ni hipotecaria."))
    st.caption(rc_usage_line())
    if st.button(L("Check which data sources work from this server", "Revisar qué fuentes funcionan desde este servidor"), key="probe"):
        import requests
        from bellazu.http import UA_BROWSER
        checks = [("Craigslist", "https://www.craigslist.org/search/city/fort-lee-nj?cat=apa", "cl-static-search-result"),
                  ("Rent.com", "https://www.rent.com/new-jersey/fort-lee-apartments", "__NEXT_DATA__"),
                  ("Redfin", "https://www.redfin.com/city/6283/NJ/Fort-Lee/apartments-for-rent", "application/ld+json"),
                  ("Zillow", "https://www.zillow.com/fort-lee-nj/rentals/", "__NEXT_DATA__"),
                  ("Inside Airbnb", "https://insideairbnb.com/get-the-data/", "jersey-city"),
                  ("Census Reporter", "https://api.censusreporter.org/1.0/data/show/latest?table_ids=B25031&geo_ids=86000US07024", "B25031"),
                  ("FRED", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US", "MORTGAGE30US"),
                  ("Freddie Mac PMMS", "https://www.freddiemac.com/pmms/docs/PMMS_history.csv", "pmms30"),
                  ("HUD (website)", "https://www.huduser.gov/portal/datasets/fmr/smallarea/index.html", "Small Area"),
                  ("OpenStreetMap", "https://nominatim.openstreetmap.org/search?q=Fort+Lee,+NJ&format=json&limit=1", "lat"),
                  ("Photon (address suggestions)", "https://photon.komoot.io/api/?q=Fort+Lee+NJ&limit=1", "coordinates")]
        rows = []
        for name, url, needle in checks:
            try:
                ua = "BellaZu/0.1 (personal real-estate research; low volume)" if ("nominatim" in url or "photon" in url) else UA_BROWSER
                rr = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"}, timeout=20)
                rows.append({"source": name, "works": "yes" if rr.status_code == 200 and needle.encode() in rr.content else "no", "http": rr.status_code})
            except Exception as e:
                rows.append({"source": name, "works": "no", "http": e.__class__.__name__})
            time.sleep(1.2)
        st.dataframe(rows, hide_index=True, width="stretch")
    if st.button(L("Log out", "Salir"), key="logout", type="tertiary"):
        for k in list(st.session_state.keys()):
            if k != "lang":
                del st.session_state[k]
        st.rerun()

storage_bridge()
if st.session_state.get("sv_polling"):
    _sv_poll()
_tm_show()
