"""BellaZu web app (Streamlit). Simple phone-first UI, English/Spanish, passcode-gated.
Run locally:  APP_PASSCODE=... streamlit run app.py   (or put the values in .streamlit/secrets.toml)
Secrets (st.secrets first, then environment variables):
  APP_PASSCODE (required), RENTCAST_API_KEY (optional), RENTCAST_MONTHLY_CAP / RENTCAST_USED_OFFSET (optional).
RentCast key: data/rc.lock holds the key encrypted with the passcode (bellazu/keylock.py); it is tried first and
RENTCAST_API_KEY is the fallback (also used if RentCast refuses the locked key). The key is never shown.
Nothing personal lives in this file: every number is typed by the user and kept only in the browser session."""
import hmac, html as H, json, os, pathlib, re, sys, tempfile, time
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


def _fresh_engine():
    """Streamlit Cloud pulls new commits into a running process, which re-runs app.py but keeps the old bellazu
    modules in memory. Reload them when their files change (or on the first run after such a pull)."""
    import sys, importlib, pathlib as _pl
    root = _pl.Path(__file__).parent / "bellazu"
    stamp = tuple(sorted((str(p), p.stat().st_mtime_ns) for p in root.rglob("*.py")))
    old = getattr(sys, "_bz_stamp", None)
    stale = (old is None and "bellazu" in sys.modules) or (old is not None and old != stamp)
    if stale:
        for name in sorted([m for m in list(sys.modules) if m == "bellazu" or m.startswith("bellazu.")], key=lambda n: -n.count(".")):
            try:
                importlib.reload(sys.modules[name])
            except Exception:
                pass
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

st.set_page_config(page_title="BellaZu", page_icon="🏡", layout="centered", initial_sidebar_state="collapsed")


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
if "rc_budget" not in st.session_state:     # optional test aid: ?rc_budget=N caps live RentCast lookups in this session (only lowers use)
    try:
        _b = st.query_params.get("rc_budget")
        st.session_state.rc_budget = max(int(_b), 0) if _b not in (None, "") else None
    except Exception:
        st.session_state.rc_budget = None

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
.st-key-lang [data-testid="stButtonGroup"] button {min-height:2.2rem; padding:0 .8rem; font-size:.75rem}
/* expanders + popovers */
[data-testid="stExpander"] details {border:none; border-top:1px solid var(--line); border-bottom:1px solid var(--line); border-radius:0; background:transparent}
[data-testid="stExpander"] summary {padding-left:0}
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
.bz-home .p {font-family:var(--disp); font-size:2rem; line-height:1.05; color:var(--paper)}
.bz-home .cut, .bz-home .new {font-family:var(--body, inherit); font-size:.7rem; vertical-align:middle; border-radius:10px; padding:.15rem .45rem; margin-left:.3rem; letter-spacing:.05em}
.bz-home .cut {background:var(--good); color:#111} .bz-home .new {background:var(--rose); color:#111}
.bz-home .m {font-size:.86rem; color:#DADADA; margin-top:.15rem} .bz-home .a {font-size:.8rem; color:var(--mute); margin-top:.3rem}
.bz-home .br {font-size:.66rem; color:var(--mute); margin-top:.2rem}
.bz-gal {display:flex; overflow-x:auto; scroll-snap-type:x mandatory; gap:6px; border-radius:20px; margin:.3rem 0 .2rem; -webkit-overflow-scrolling:touch}
.bz-gal img {flex:0 0 100%; width:100%; aspect-ratio:3/2; object-fit:cover; scroll-snap-align:center; border-radius:20px}
.bz-foot {text-transform:uppercase; letter-spacing:.08em; font-size:.66rem; color:#7D7D7D; text-align:center; margin-top:1.4rem}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ language helpers
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


def header():
    top = st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute", key="topbar")
    top.markdown("<div class='bz-word'>Bella<i>Zu</i></div>", unsafe_allow_html=True)
    top.segmented_control("Language / Idioma", ["EN", "ES"], key="lang", default="EN", required=True, label_visibility="collapsed")
    html("<div style='border-bottom:1px solid #2E2E2E; margin:-.3rem 0 1.1rem'></div>")


def header_hero():
    html(f"<div class='bz-eyebrow'>{L('For first-time buyers in North Jersey', 'Para primeros compradores en el norte de NJ')}</div>"
         f"<div class='bz-h1'>{L('Your first home, <em>made simple.</em>', 'Su primera casa, <em>sin complicaciones.</em>')}</div>"
         f"<div class='bz-lede'>{L('Type an address or a town. See what you would pay each month living there alone, with a tenant, or with Airbnb or 30+ day guests.', 'Escriba una dirección o un pueblo. Vea lo que pagaría al mes viviendo allí sin nadie más, con un inquilino, o con huéspedes de Airbnb o de 30+ días.')}</div>")


def marquee():
    words = [L("Check a home", "Revise una casa"), L("Find rentals", "Busque alquileres"), L("Plain answers", "Respuestas claras"), L("English + Español", "Español + English")]
    seq = "".join(f"<span class='{'f' if i % 2 == 0 else 'o'}'>{H.escape(w)}</span><span class='st'>✺</span>" for i, w in enumerate(words))
    html(f"<div class='bz-marquee' aria-hidden='true'><div class='track'>{seq}{seq}</div></div>")


# ------------------------------------------------------------------ passcode gate
def gate():
    header()
    st.markdown("<div class='bz-eyebrow'>Private beta · Beta privada</div>"
                "<div class='bz-h1'>Welcome to <em>BellaZu</em></div>"
                "<div class='bz-lede'>Bienvenida a BellaZu 💕<br>Type your passcode to come in. · Escriba su código para entrar.</div>", unsafe_allow_html=True)
    pc = secret("APP_PASSCODE").lower()
    if not pc:
        st.error("This app is not set up yet (missing APP_PASSCODE). / La app aún no está configurada (falta APP_PASSCODE).")
        st.stop()
    n = st.session_state.get("fails", 0)
    if n >= 15:
        st.error("Too many tries. Reload the page later. / Demasiados intentos. Recargue la página más tarde.")
        st.stop()
    with st.form("gate"):
        typed = st.text_input("Passcode / Código", type="password")
        ok = st.form_submit_button("Enter / Entrar", type="primary", width="stretch")
    if ok:
        if hmac.compare_digest(typed.strip().lower().encode(), pc.encode()):
            st.session_state.authed = True
            st.session_state.fails = 0
            st.session_state._gate_pc = typed.strip().lower()   # server-side only; unlocks data/rc.lock if secrets lack it
            st.rerun()
        else:
            st.session_state.fails = n + 1
            time.sleep(min(1 + n, 5))       # slow down guessing
            st.error("Hmm, that passcode didn't work. Try again 💕 / Ese código no funcionó. Intente otra vez 💕")
    st.stop()


if not st.session_state.get("authed"):
    gate()

header()


# ------------------------------------------------------------------ shared bits
def xlsx_bytes(r, kind):
    with tempfile.TemporaryDirectory() as d:
        files = write_property(r, d, st.session_state.get("prop_cv")) if kind == "property" else write_arbitrage(r, d)
        return pathlib.Path(files["xlsx"]).read_bytes(), pathlib.Path(files["xlsx"]).name


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


def property_details(r, f, sc, o, rent, rent_src, own):
    A = r.get("assumptions") or {}
    fi = A.get("financing", {})
    # --- the home
    st.markdown(f"#### {L('🏡 The home', '🏡 La casa')}")
    inc = [P(INC_LBL.get(x, (x, x))) for x in (f.get("hoa_includes") or [])]
    lines = [L(f"Price: {money(f.get('price'))}", f"Precio: {money(f.get('price'))}") if f.get("price") else L("Price: unknown", "Precio: no se sabe"),
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
    ok_src = sorted({s["source"].split(":")[0] for s in r.get("sources_status", []) if s.get("ok")})
    bad_src = sorted({s["source"].split(":")[0] for s in r.get("sources_status", []) if not s.get("ok")} - set(ok_src))
    st.caption(L("Data from: ", "Datos de: ") + ", ".join(ok_src) + ((L(". Could not reach: ", ". No se pudo consultar: ") + ", ".join(bad_src)) if bad_src else "") + ".")
    try:
        xb, xn = xlsx_bytes(r, "property")
        st.download_button(L("⬇️ Spreadsheet (Excel)", "⬇️ Hoja de cálculo (Excel)"), xb, xn, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dlx_prop", width="stretch", on_click="ignore")
    except Exception as e:
        st.caption(f"Excel: {e.__class__.__name__}")
    st.caption(L("Estimates from public data, not financial, legal or lending advice. Confirm with your lender, agent and the town.",
                 "Estimados con datos públicos; no es asesoría financiera, legal ni hipotecaria. Confirme con su prestamista, agente y el municipio."))


GLOSSARY = [
    (("Down payment", "Pago inicial (down payment)"), ("The part of the price you pay yourself. The bank lends you the rest.", "La parte del precio que usted paga. El banco le presta el resto.")),
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


def _inc_chip():
    v = st.session_state.get("inc_chip")
    if v is not None:
        st.session_state.set_income = 0 if v == "skip" else int(v)


def settings_popover():
    with st.popover(L("⚙️ My settings", "⚙️ Mis ajustes"), width="content"):
        st.markdown(f"**{L('Your yearly income (before taxes)', 'Su ingreso anual (antes de impuestos)')}**")
        st.caption(L("Only used to check lender and co-op board rules. Never saved.", "Solo se usa para revisar reglas del banco y de la junta. Nunca se guarda."))
        st.pills(L("Quick pick", "Elegir rápido"), INCOME_PICKS, key="inc_chip", on_change=_inc_chip, label_visibility="collapsed",
                 format_func=lambda k: L("Skip", "Omitir") if k == "skip" else f"${k // 1000:,}K")
        st.number_input(L("Exact amount ($)", "Cantidad exacta ($)"), min_value=0, max_value=5_000_000, step=5000, key="set_income")
        st.markdown(f"**{L('Down payment', 'Pago inicial')}**")
        st.pills(L("Down payment", "Pago inicial"), DOWN_PICKS, key="set_down", required=True, label_visibility="collapsed",
                 format_func=lambda k: L("3.5% FHA (usual)", "3.5% FHA (usual)") if k == "usual" else f"{k:g}%")
        st.caption(L("Co-ops can't use FHA, so 'usual' means 10% down there.", "Las co-ops no aceptan FHA; ahí 'usual' significa 10% inicial."))
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
    d = ss.get("set_down", "usual")
    if d != "usual":
        aov["financing"] = {"fha_down_pct": float(d) / 100, "owner_conv_down_pct": float(d) / 100}
    return {"overrides": {k: v for k, v in ov.items() if v is not None}, "income_annual": int(ss.get("set_income") or 0) or None,
            "units_total": 3 if fo.get("type") == "3-4-family" else 2,
            "building_policy": bp, "use_rentcast": bool(ss.get("set_rc")) and rentcast.available(), "assumption_overrides": aov}


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
                    r = analyze_property(addr.strip(), opts)
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
    if f.get("hoa_monthly") in (None, "") and own in ("condo", "co-op", "townhouse"):
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
           "hoa": L("We couldn't find the monthly building fee. Add it for a truer cost ✨", "No encontramos la cuota mensual del edificio. Agréguela para un costo más real ✨")}[k]
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

MONTHS = [("J", "E"), ("F", "F"), ("M", "M"), ("A", "A"), ("M", "M"), ("J", "J"), ("J", "J"), ("A", "A"), ("S", "S"), ("O", "O"), ("N", "N"), ("D", "D")]


def kmoney(v):
    if v is None:
        return "?"
    v = float(v)
    if abs(v) >= 10000:
        k = v / 1000
        return f"${k:,.0f}K" if abs(k - round(k)) < 0.05 or abs(k) >= 100 else f"${k:.1f}K"
    return f"${round(v):,}"


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
        st.caption(L(f"Most rentals listed here are in new buildings (typical {money(u['high'])}/mo), well above HUD's fair rent ({money(u['low'])}). "
                     f"For an older 2-family unit we use {money(u['typ'])}/mo, halfway between HUD and the cheaper listings. Move the rent slider if you know better.",
                     f"La mayoría de los alquileres aquí son de edificios nuevos (típico {money(u['high'])}/mes), muy por encima de la renta justa de HUD ({money(u['low'])}). "
                     f"Para una unidad en una casa de 2 familias usamos {money(u['typ'])}/mes, entre HUD y los anuncios más baratos. Mueva la barra de renta si sabe más."))


def compare_strip(out, first):
    cols = C.labels(out, first)
    cells = ""
    for c in cols:
        earn = c["pay_lbl"][0] == "You earn"
        cells += (f"<div class='bz-col{' star' if c['star'] else ''}'>" + (f"<div class='tag'>⭐ {L('City renters', 'Para la ciudad')}</div>" if c["star"] else "")
                  + f"<div class='h'>{H.escape(P(c['title']))}</div><div class='l'>{H.escape(P(c['pay_lbl']))}</div>"
                  f"<div class='n{' earn' if earn else ''}'>{H.escape(c['pay'])}</div><div class='s'>{H.escape(P(c['sub']))}</div>"
                  f"<div class='b'>{H.escape(P(c['badge']))}</div></div>")
    html(f"<div class='bz-lbl'>{L('What you pay each month, same FHA loan', 'Lo que paga al mes, mismo préstamo FHA')}</div><div class='bz-cmp'>{cells}</div>")


def sel_for(sid, base):
    """Tap-only choices for the compare view. Returns the selection dict for compare()."""
    ss = st.session_state
    d = C.default_sel(base)
    multi = base["ptype"] == "multi-family"
    pt = "mf" if multi else "sf"          # the choice resets when the home type changes (e.g. after the user says it's a 2-family)
    opts = ["room", "unit", "none"] if multi else ["room", "none"]
    nm = {"room": L("A room", "Un cuarto"), "unit": L("The other unit", "La otra unidad"), "none": L("Nothing", "Nada")}
    st.markdown(f"<div class='bz-lbl'>{L('What would you rent out?', '¿Qué alquilaría?')}</div>", unsafe_allow_html=True)
    ro = st.segmented_control("rent out", opts, key=f"ro_{sid}_{pt}", default=d["rent_out"] if d["rent_out"] in opts else "none", required=True,
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


def places_block(lists, rules, town, datasets, ok_airbnb, d30):
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


def season_block(s, town):
    if not s:
        return
    idx = (s.get("short") or {}).get("index") or []
    if not idx or None in idx:
        return
    mx = max(idx)
    bars = "".join(f"<div class='{'lo' if v < 1 else ''}' style='height:{max(v / mx, .05) * 100:.0f}%' title='{v:.2f}'></div>" for v in idx)
    mons = "".join(f"<span>{P(m)}</span>" for m in MONTHS)
    city = s["city"].replace("-", " ").title()
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
    gallery_block(ss.get("prop_addr", r["address"]))
    html(f"<div class='bz-addr'>📍 {H.escape(r['address'])}</div>")
    safety_note(r.get("town"))
    drive_badge(ex.get("drive"))
    verdict_box(S.verdict_property(r))
    ask_missing(r)
    base = C.base_from_property(r)
    if base:
        sel = sel_for(sid, base)
        out = C.compare(base, sel)
        compare_strip(out, first)
        skew_note(base, sel)
        ln = o["loan"]
        md(L(f"Same loan in every column: FHA {ln['rate_pct']:.2f}%, {money(ln['down_payment'])} down + about {money(ln['closing_costs_est'])} fees = **{money(ln['cash_to_close_est'])} to close**.",
             f"Mismo préstamo en cada columna: FHA {ln['rate_pct']:.2f}%, {money(ln['down_payment'])} inicial + unos {money(ln['closing_costs_est'])} de cierre = **{money(ln['cash_to_close_est'])} para cerrar**."))
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
        cash_card(sid, out, (ref or {}).get("typ") if own == "multi-family" else rent)
        ok_air = out.get("airbnb_allowed")
        places_block(lists_for_property(r, sel), r.get("str_rules") or {}, r.get("town"), (r.get("str") or {}).get("datasets") or [], ok_air, out.get("days30", 30))
        season_block(C.seasonality((r.get("str") or {}).get("datasets")), r.get("town"))
        cv = report_cv(out, ex.get("drive"), first)
    else:
        cv = None
    ss.prop_cv = cv
    fix_facts(r)
    st.download_button(L("⬇️ Download your full report", "⬇️ Descargar su reporte completo"), property_html(r, "es" if ES() else "en", cv=cv).encode(),
                       f"BellaZu_Report_{safe_name(r['address'])}.html", "text/html", key="dl_prop", type="primary", width="stretch", on_click="ignore")
    with st.expander(L("See details", "Ver detalles")):
        property_details(r, f, sc, o, rent, rent_src, own)


# ------------------------------------------------------------------ town view (same layout)
def run_town(name, where):
    ss = st.session_state
    tn = towns.normalize(name)
    key = (tn["name"] or name).lower()
    cache = ss.setdefault("town_cache", {})
    if key in cache:
        ss.town = cache[key]
        return
    with where, st.spinner(L("Looking at the town for you... about 20 to 40 seconds ✨", "Revisando el pueblo por usted... unos 20 a 40 segundos ✨")):
        try:
            a = town_snapshot(name, {"use_rentcast": False})
        except Exception as e:
            a = {"ok": False, "error": e.__class__.__name__, "town_input": name, "town_suggestions": tn["suggestions"]}
    if a.get("ok"):
        cache[key] = a
    ss.town = a


def safety_note(town):
    lvl, c = C.town_caution(town)
    if c:
        html(f"<div class='bz-warn{' hi' if lvl == 'exclude' else ''}'>{'⚠️' if lvl == 'exclude' else 'ℹ️'} {H.escape(P(c))}</div>")


def show_town_view(a):
    ss = st.session_state
    first = ss.get("hmode", "first") == "first"
    t = a["town"]
    sid = "t_" + safe_name(t)[:24]
    if a.get("town_match") in ("alias", "fuzzy") and a.get("town_input"):
        st.caption(L(f"Showing {t} (you typed “{a['town_input']}”).", f"Mostrando {t} (usted escribió “{a['town_input']}”)."))
    html(f"<div class='bz-hello'>{H.escape(t)}</div>")
    drive_badge(a.get("drive"))
    safety_note(t)
    rules_card(a.get("str_rules") or {}, t)
    st.markdown(f"<div class='bz-lbl'>{L('Tap a price you are looking at', 'Toque un precio que esté mirando')}</div>", unsafe_allow_html=True)
    price = st.pills("price", C.PRICE_CHIPS + ["other"], key=f"tp_{sid}", label_visibility="collapsed",
                     format_func=lambda p: L("Other", "Otro") if p == "other" else kmoney(p))
    if price == "other":
        price = st.number_input(L("Price ($)", "Precio ($)"), min_value=50_000, max_value=3_000_000, step=10_000, value=int(ss.get(f"tpo_{sid}") or 350_000), key=f"tpo_{sid}")
    size = st.segmented_control(L("Size", "Tamaño"), C.TOWN_SIZES, key=f"ts_{sid}", default="2fam" if first else "2", required=True, width="stretch",
                                format_func=lambda s_: L("2-family", "2 familias") if s_ == "2fam" else f"{s_} {L('bd', 'hab')}")
    out, cv = None, None
    if not price:
        html(f"<div class='bz-ask'>👆 {L('Tap a price to see what you would pay each month here. We never guess a home value for you.', 'Toque un precio para ver lo que pagaría al mes aquí. Nunca inventamos el valor de una casa.')}</div>")
    else:
        d = ss.get("set_down", "usual")
        base = C.base_from_town(a, int(price), size, None if d == "usual" else float(d) / 100)
        sel = sel_for(sid, base)
        out = C.compare(base, sel)
        compare_strip(out, first)
        skew_note(base, sel)
        ln = base["loan"]
        tx = (L(f"Taxes use {t}'s typical rate, {base['tax_rate']:.2%} of the price (NJ Treasury 2025 average bill ÷ average sale price)", f"Los impuestos usan la tasa típica de {t}, {base['tax_rate']:.2%} del precio (Tesoro de NJ 2025: factura promedio ÷ precio promedio)")
              if not base.get("tax_fallback") else L(f"Taxes use a {base['tax_rate']:.1%} estimate", f"Los impuestos usan un estimado de {base['tax_rate']:.1%}"))
        md(L(f"At {money(price)} with FHA {ln['rate_pct']:.2f}%: {money(ln['cash_to_close_est'])} to close. {tx}; add any HOA fee on top.",
             f"A {money(price)} con FHA {ln['rate_pct']:.2f}%: {money(ln['cash_to_close_est'])} para cerrar. {tx}; sume cualquier cuota HOA."))
        q = out.get("qualify")
        if q:
            md(L(f"🏦 A lender can count about **{money(q['counted'])}/mo** of the other unit's rent (75%).", f"🏦 El banco puede contar unos **{money(q['counted'])}/mes** de la renta de la otra unidad (75%)."))
        ranges_block(sid, out)
        ub = sel.get("unit_beds", 2)
        ref = (base["units"].get(ub) or {}).get("ltr") if size == "2fam" else (base["units"].get(int(size)) or {}).get("ltr") if size in ("1", "2", "3") else None
        cash_card(sid, out, (ref or {}).get("typ"))
        cv = report_cv(out, a.get("drive"), first, [(f"Price you picked: {money(price)} · size: {size}", f"Precio elegido: {money(price)} · tamaño: {size}")])
    homes_block(t, a.get("drive"), sid)
    # Airbnb market card
    mk = a.get("market") or {}
    s_ = mk.get("summary") or {}
    st.markdown(f"#### {L('🛏️ Airbnb market nearby', '🛏️ Mercado de Airbnb cerca')}")
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
    season_block(a.get("seasonality"), t)
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
    places_block(lists, a.get("str_rules") or {}, t, mk.get("datasets") and [f"nj/{x}" for x in mk["datasets"]] or [], ok_air, C.days30(a.get("str_rules") or {}))
    st.download_button(L("⬇️ Download the town report", "⬇️ Descargar el reporte del pueblo"), town_html(a, cv, "es" if ES() else "en").encode(),
                       f"BellaZu_Town_{safe_name(t)}.html", "text/html", key="dl_town", type="primary", width="stretch", on_click="ignore")
    try:
        with tempfile.TemporaryDirectory() as d_:
            fx = write_town(a, cv, d_)
            st.download_button(L("⬇️ Spreadsheet (Excel)", "⬇️ Hoja de cálculo (Excel)"), pathlib.Path(fx).read_bytes(), pathlib.Path(fx).name,
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dlx_town", width="stretch", on_click="ignore")
    except Exception as e:
        st.caption(f"Excel: {e.__class__.__name__}")


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


def _open_listing(row):
    st.session_state.go = ("listing", row)


def _home_card(h, drive, rent):
    cut = f"<span class='cut'>↓ {kmoney(h['price_cut'])}</span>" if h.get("price_cut") else ("<span class='new'>" + L("NEW", "NUEVA") + "</span>" if h.get("new") else "")
    bits = [f"{h['beds']} {L('bd', 'hab')}" if h.get("beds") is not None else None, f"{h['baths']:g} {L('ba', 'baños')}" if h.get("baths") else None,
            f"{h['sqft']:,} ft²" if h.get("sqft") else None,
            (L(f"fee {money(h['hoa_monthly'])}/mo", f"cuota {money(h['hoa_monthly'])}/mes") if h.get("hoa_monthly") else None)]
    days = h.get("days")
    dl = (L("Listed today", "Publicada hoy") if days == 0 else L("Listed 1 day ago", "Publicada hace 1 día") if days == 1
          else L(f"Listed {days} days ago", f"Publicada hace {days} días")) if days is not None else ""
    dr = L(f"🚗 {drive['min']}-{drive['rush'][1]} min to Midtown", f"🚗 {drive['min']}-{drive['rush'][1]} min a Midtown") if drive and drive.get("rush") else ""
    img = f"<img src='{H.escape(h['photo'])}' loading='lazy' alt=''>" if h.get("photo") else "<div class='noimg'>📷</div>"
    pc = f"<span class='pc'>📷 {h['photo_count']}</span>" if h.get("photo_count") else ""
    price = money(h["price"]) + (L("/mo", "/mes") if rent else "")
    html(f"<div class='bz-home'><div class='ph'>{img}{pc}</div><div class='bd'><div class='p'>{price} {cut}</div>"
         f"<div class='m'>{' · '.join(b for b in bits if b)}</div><div class='m'>{' · '.join(x for x in (dl, dr) if x)}</div>"
         f"<div class='a'>{H.escape(h['address'])}</div>" + (f"<div class='br'>{L('Listed by', 'Publicada por')} {H.escape(h['broker'])}</div>" if h.get("broker") else "") + "</div></div>")


def homes_block(t, drive, sid):
    ss = st.session_state
    if not listings.available():
        return
    st.markdown(f"#### {L('🏡 Homes in ' + t, '🏡 Casas en ' + t)}")
    status = st.segmented_control("status", ["for_sale", "for_rent"], key=f"hst_{sid}", default="for_sale", required=True, label_visibility="collapsed", width="stretch",
                                  format_func=lambda s_: L("For sale", "En venta") if s_ == "for_sale" else L("For rent", "En alquiler"))
    rent = status == "for_rent"
    with st.spinner(L("Finding homes... ✨", "Buscando casas... ✨")):
        res = feed(t, status)
    if not res.get("ok"):
        u = listings.usage()
        if res.get("error") == "cap":
            st.info(L(f"We've used this month's home searches ({u['used']} of {u['cap']}). They start again on {u.get('resets') or 'the next month'}. Towns you already opened still show.",
                      f"Ya usamos las búsquedas de casas de este mes ({u['used']} de {u['cap']}). Vuelven el {u.get('resets') or 'próximo mes'}. Los pueblos ya abiertos se siguen viendo."), icon="🌷")
        else:
            st.caption(L("Home listings aren't loading right now. Try again later.", "Los anuncios de casas no cargan ahora. Intente más tarde."))
        return
    st.markdown(f"<div class='bz-lbl'>{L('Price up to', 'Precio hasta')}</div>", unsafe_allow_html=True)
    mx = st.segmented_control("max", FEED_PRICE[status], key=f"hpx_{sid}_{status}", default=None if rent else 500_000, required=True, label_visibility="collapsed", width="stretch",
                              format_func=lambda v: L("Any", "Todo") if v is None else (money(v) if rent else kmoney(v)))
    c1, c2 = st.columns([2, 3])
    with c1:
        bd = st.segmented_control(L("Bedrooms", "Habitaciones"), [0, 1, 2, 3], key=f"hbd_{sid}", default=0, required=True, width="stretch",
                                  format_func=lambda b: L("Any", "Todas") if b == 0 else f"{b}+")
    with c2:
        kd = st.segmented_control(L("Type", "Tipo"), list(FEED_KIND), key=f"hkd_{sid}", default="any", required=True, width="stretch", format_func=lambda k: P(FEED_KIND[k]))
    rows = listings.filter_rows(res["rows"], None, mx, bd or None, kd)
    shown = int(ss.get(f"hn_{sid}", 8))
    st.caption(L(f"{len(rows)} of the {len(res['rows'])} newest listings match (updated {res.get('fetched', '')[-5:]}).",
                 f"{len(rows)} de los {len(res['rows'])} anuncios más nuevos coinciden (actualizado {res.get('fetched', '')[-5:]})."))
    for i, h in enumerate(rows[:shown]):
        _home_card(h, drive, rent)
        if rent:
            if h.get("url"):
                st.link_button(L("See photos on realtor.com ↗", "Ver fotos en realtor.com ↗"), h["url"], width="stretch")
        else:
            st.button(L("📷 Photos + my monthly numbers", "📷 Fotos + mis números del mes"), key=f"ho_{sid}_{i}_{h['id']}", width="stretch", type="primary",
                      on_click=_open_listing, args=(h,))
    if len(rows) > shown:
        st.button(L(f"Show more ({len(rows) - shown} more)", f"Ver más ({len(rows) - shown} más)"), key=f"hmore_{sid}", width="stretch",
                  on_click=lambda: ss.update({f"hn_{sid}": shown + 8}))
    if not rows:
        st.caption(L("No listings match. Try another price or type.", "Ningún anuncio coincide. Pruebe otro precio o tipo."))
    u = listings.usage()
    st.caption(L(f"Listing data from realtor.com via Realty in US. Prices and details can change; check with the agent. Home searches this month: {u['used']} of {u['cap']}.",
                 f"Datos de anuncios de realtor.com vía Realty in US. Los precios y datos pueden cambiar; confirme con el agente. Búsquedas de casas este mes: {u['used']} de {u['cap']}."))


def run_listing(h, where):
    """Open a listing: one detail call (photos + HOA + taxes, cached), then our analysis with the listing's facts (no RentCast needed for price)."""
    ss = st.session_state
    with where, st.spinner(L("Getting the photos... ✨", "Trayendo las fotos... ✨")):
        d = listings.detail(h["id"]) if h.get("id") else {"ok": False}
    addr = h["address"]
    fo = facts_for(addr)
    fo["price"] = int(h["price"]) if h.get("price") else fo.get("price")
    hoa = d.get("hoa_monthly") if d.get("ok") else h.get("hoa_monthly")
    if hoa is not None:
        fo["hoa"] = int(hoa)
    elif h.get("kind") in ("2fam", "house"):
        fo["hoa"] = 0
    if d.get("ok") and d.get("taxes_annual"):
        fo["taxes"] = int(d["taxes_annual"])
    if h.get("kind") in LISTING_TYPE:
        fo["type"] = "co-op" if h.get("type") == "coop" else LISTING_TYPE[h["kind"]]
    if h.get("beds") is not None:
        fo["beds"] = int(h["beds"])
    if h.get("baths"):
        fo["baths"] = float(h["baths"])
    ss.setdefault("gallery", {})[addr.strip().lower()] = {"photos": (d.get("photos") if d.get("ok") else None) or h.get("photos") or [], "url": h.get("url"),
                                                          "broker": h.get("broker"), "price": h.get("price"), "hoa": hoa, "count": h.get("photo_count")}
    ss.view = ("addr", addr)
    ss.prop_addr = addr
    run_home(addr, where)


def gallery_block(addr):
    g = (st.session_state.get("gallery") or {}).get((addr or "").strip().lower())
    if not g or not g.get("photos"):
        return
    ph = g["photos"][:40]
    html("<div class='bz-gal'>" + "".join(f"<img src='{H.escape(u)}' loading='{'eager' if i < 2 else 'lazy'}' alt=''>" for i, u in enumerate(ph)) + "</div>")
    bits = [L(f"Swipe for {len(ph)} photos", f"Deslice para ver {len(ph)} fotos")]
    if g.get("hoa") is not None:
        bits.append(L(f"building fee {money(g['hoa'])}/mo", f"cuota {money(g['hoa'])}/mes"))
    if g.get("broker"):
        bits.append(L(f"listed by {g['broker']}", f"publicada por {g['broker']}"))
    st.caption(" · ".join(bits) + ". " + L("Price and fee from the listing (realtor.com via Realty in US).", "Precio y cuota del anuncio (realtor.com vía Realty in US).")
               + (f" [realtor.com ↗]({g['url']})" if g.get("url") else ""))


# ------------------------------------------------------------------ search
def omni_search(term):
    t = (term or "").strip()
    if len(t) < 2:
        return []
    out = []
    low = t.lower()
    for n in [n for n in towns.names() if low in n.lower()][:4]:
        out.append((f"🏙️ {n} · {L('town view', 'ver pueblo')}", f"T|{n}"))
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
    return ("town" if kind == "T" else "addr", text)


@st.fragment
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


def _chip_town():
    v = st.session_state.get("tchip")
    if v:
        st.session_state.go = ("town", v)
    st.session_state.tchip = None


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fha_rate():
    try:
        from bellazu.core import _rates
        from bellazu.config import load_assumptions
        return float(_rates(load_assumptions())["fha"])
    except Exception:
        return 6.5


def town_chips(hm):
    rows = C.mode_towns(hm)
    if hm == "first":
        rows = sorted(rows, key=lambda t: (C.town_info(t) or {}).get("drive_offpeak_min", 99))
    st.markdown(f"<div class='bz-lbl'>{L('Towns near the city (closest drive first)', 'Pueblos cerca de la ciudad (más cerca primero)') if hm == 'first' else L('Towns to compare', 'Pueblos para comparar')}</div>", unsafe_allow_html=True)
    st.pills("towns", rows, key="tchip", on_change=_chip_town, label_visibility="collapsed")


def town_ranking(hm):
    ss = st.session_state
    st.markdown(f"#### {L('🏆 Best towns for your first home' if hm == 'first' else '🏆 Towns by the numbers', '🏆 Mejores pueblos para su primera casa' if hm == 'first' else '🏆 Pueblos según los números')}")
    price = st.segmented_control(L("Price you're looking at", "Precio que está mirando"), C.PRICE_CHIPS, key="rank_price", default=C.PRICE_CHIPS[1], required=True, format_func=kmoney)
    rk = C.town_rank(hm, int(price), fha_rate())
    st.caption(L(f"What you'd pay a month on a {kmoney(price)} 2-family, renting the other unit at HUD's fair rent for the town (2 bd). "
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


# ------------------------------------------------------------------ the one page
def main_page():
    ss = st.session_state
    hm = st.segmented_control("mode", ["first", "next"], key="hmode", default="first", required=True, label_visibility="collapsed", width="stretch",
                              format_func=lambda k: L("🏙️ My first home, near the city", "🏙️ Mi primera casa, cerca de la ciudad") if k == "first"
                              else L("🧭 Next homes, anywhere", "🧭 Próximas casas, donde sea"))
    view = ss.get("view")
    if not view:
        header_hero()
    search_block()
    res_box = st.container()
    go = ss.pop("go", None)
    if ss.pop("auto_go", False):
        go = ("addr", ss.get("addr"))
    if go and go[0] == "listing":
        run_listing(go[1], res_box)
        st.rerun()
    elif go:
        ss.view = go
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
        if view and view[0] == "addr":
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
main_page()

st.write("")
with st.expander(L("About BellaZu", "Sobre BellaZu"), icon="ℹ️"):
    md(L("BellaZu helps first-time buyers in North Jersey compare buying, renting out and Airbnb or 30+ day stays for a home or a town, using free public data "
         "(Inside Airbnb, HUD, Census, Freddie Mac, OpenStreetMap and OSRM for drive times, Craigslist, Rent.com, Redfin and, if set up, RentCast).\n\n"
         "**Privacy:** what you type stays in this browser session. Nothing is saved to an account.\n\n"
         "**Important:** these are estimates, not financial, legal or lending advice.",
         "BellaZu ayuda a primeros compradores en el norte de NJ a comparar comprar, alquilar y Airbnb o estadías de 30+ días para una casa o un pueblo, con datos públicos gratuitos "
         "(Inside Airbnb, HUD, Censo, Freddie Mac, OpenStreetMap, Craigslist, Rent.com, Redfin y, si está configurado, RentCast).\n\n"
         "**Privacidad:** lo que escribe se queda en esta sesión del navegador. No se guarda en ninguna cuenta.\n\n"
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
