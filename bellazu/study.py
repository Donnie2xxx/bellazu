"""NJ real-estate exam study content and progress (no Streamlit, no network).

Content comes from data/study/catalog.json in the source tree, or from
data/study.lock (compressed + encrypted with the app passcode) on the server.
Progress is a plain dict meant to live on the saved-homes list (saves.normalize
keeps it, encrypted like the homes themselves). Nothing here reads a listing
API or a RentCast key.
"""
from __future__ import annotations

import base64
import json
import random
import re
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import keylock

ROOT = Path(__file__).resolve().parent.parent
PLAIN = ROOT / "data" / "study" / "catalog.json"   # readable copy (source tree only)
LOCK = ROOT / "data" / "study.lock"                # what ships
TZ = ZoneInfo("America/New_York")
_MEMO = {}

EXAM_Q = 110
EXAM_MIN = 240
EXAM_PASS = 70


def today() -> str:
    return datetime.now(TZ).date().isoformat()


def pack(plain_json: str) -> str:
    return base64.b64encode(zlib.compress(plain_json.encode(), 9)).decode()


def unpack(txt: str) -> str:
    return zlib.decompress(base64.b64decode(txt)).decode()


def load(passcode=None):
    """Catalog dict or None. Plain JSON when present, else the lock opened with the passcode."""
    try:
        if PLAIN.exists():
            k = ("plain", PLAIN.stat().st_mtime)
            if k not in _MEMO:
                _MEMO.clear()
                _MEMO[k] = json.loads(PLAIN.read_text(encoding="utf-8"))
            return _MEMO[k]
        if LOCK.exists() and passcode:
            k = ("lock", passcode)
            if k not in _MEMO:
                raw = keylock.unlock(LOCK, passcode)
                _MEMO.clear()
                _MEMO[k] = json.loads(unpack(raw)) if raw else None
            return _MEMO[k]
    except Exception:
        return None
    return None


def empty_progress():
    return {
        "t": 0,
        "exam_date": None,
        "target": 75,
        "streak_last": None,
        "streak": 0,
        "best_streak": 0,
        "days": [],
        "lessons": {},
        "cards": {},
        "qs": {},
        "errors": {},
        "seeded": False,
    }


def _ymd(s):
    if isinstance(s, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            date.fromisoformat(s)
            return s
        except Exception:
            return None
    return None


def _int(v, lo, hi, default=0):
    try:
        n = int(v)
    except Exception:
        return default
    return max(lo, min(hi, n))


def _float(v, lo, hi, default=0.0):
    try:
        n = float(v)
    except Exception:
        return default
    return max(lo, min(hi, n))


def norm_progress(d):
    """Keep only study fields (no names, no money, no addresses)."""
    if not isinstance(d, dict):
        return None
    out = empty_progress()
    out["t"] = _int(d.get("t"), 0, 10**15, 0)
    out["exam_date"] = _ymd(d.get("exam_date"))
    out["target"] = _int(d.get("target"), 50, 100, 75)
    out["streak_last"] = _ymd(d.get("streak_last"))
    out["streak"] = _int(d.get("streak"), 0, 10000, 0)
    out["best_streak"] = max(out["streak"], _int(d.get("best_streak"), 0, 10000, 0))
    days = d.get("days") if isinstance(d.get("days"), list) else []
    out["days"] = [x for x in days if _ymd(x)][-120:]
    out["seeded"] = bool(d.get("seeded"))
    lessons = d.get("lessons") if isinstance(d.get("lessons"), dict) else {}
    for lid, rec in list(lessons.items())[:40]:
        if not isinstance(lid, str) or not isinstance(rec, dict):
            continue
        out["lessons"][lid[:24]] = {
            "manual": bool(rec.get("manual")),
            "quiz_best": _int(rec.get("quiz_best"), 0, 100, 0),
            "tf_best": _int(rec.get("tf_best"), 0, 100, 0),
            "seen": _int(rec.get("seen"), 0, 100000, 0),
        }
    cards = d.get("cards") if isinstance(d.get("cards"), dict) else {}
    for cid, rec in list(cards.items())[:2500]:
        if not isinstance(cid, str) or not isinstance(rec, dict):
            continue
        out["cards"][cid[:96]] = {
            "ef": _float(rec.get("ef"), 1.3, 3.0, 2.5),
            "iv": _int(rec.get("iv"), 0, 3650, 0),
            "n": _int(rec.get("n"), 0, 10000, 0),
            "l": _int(rec.get("l"), 0, 10000, 0),
            "due": _ymd(rec.get("due")) or today(),
            "last": _ymd(rec.get("last")),
        }
    qs = d.get("qs") if isinstance(d.get("qs"), dict) else {}
    for qid, rec in list(qs.items())[:4000]:
        if not isinstance(qid, str) or not isinstance(rec, dict):
            continue
        out["qs"][qid[:80]] = {
            "n": _int(rec.get("n"), 0, 10000, 0),
            "w": _int(rec.get("w"), 0, 10000, 0),
            "ok": _int(rec.get("ok"), 0, 10000, 0),
            "last": _ymd(rec.get("last")),
            "last_ok": bool(rec.get("last_ok")),
        }
    errors = d.get("errors") if isinstance(d.get("errors"), dict) else {}
    for qid, rec in list(errors.items())[:2000]:
        if not isinstance(qid, str) or not isinstance(rec, dict):
            continue
        out["errors"][qid[:80]] = {
            "n": _int(rec.get("n"), 1, 10000, 1),
            "ok_streak": _int(rec.get("ok_streak"), 0, 100, 0),
            "pick": str(rec.get("pick") or "")[:4],
            "src": str(rec.get("src") or "app")[:12],
            "last": _ymd(rec.get("last")),
        }
    return out


def merge_progress(a, b):
    """Union of two progress blobs. Per card/question the newest review wins; errors are united."""
    a = norm_progress(a) or empty_progress()
    b = norm_progress(b) or empty_progress()
    if not a.get("t") and not (a.get("cards") or a.get("qs") or a.get("errors") or a.get("exam_date")):
        return b
    if not b.get("t") and not (b.get("cards") or b.get("qs") or b.get("errors") or b.get("exam_date")):
        return a
    newer, older = (a, b) if int(a.get("t") or 0) >= int(b.get("t") or 0) else (b, a)
    out = empty_progress()
    out["t"] = max(int(a.get("t") or 0), int(b.get("t") or 0))
    out["exam_date"] = newer.get("exam_date") or older.get("exam_date")
    out["target"] = newer.get("target") or 75
    out["seeded"] = bool(a.get("seeded") or b.get("seeded"))
    # streak: later calendar day wins; same day keeps the higher count
    sa, sb = a.get("streak_last") or "", b.get("streak_last") or ""
    if sa > sb:
        out["streak_last"], out["streak"] = a.get("streak_last"), a.get("streak") or 0
    elif sb > sa:
        out["streak_last"], out["streak"] = b.get("streak_last"), b.get("streak") or 0
    else:
        out["streak_last"] = sa or None
        out["streak"] = max(int(a.get("streak") or 0), int(b.get("streak") or 0))
    out["best_streak"] = max(int(a.get("best_streak") or 0), int(b.get("best_streak") or 0), out["streak"])
    out["days"] = sorted(set((a.get("days") or []) + (b.get("days") or [])))[-120:]
    for lid in set(a.get("lessons", {})) | set(b.get("lessons", {})):
        x, y = (a.get("lessons") or {}).get(lid) or {}, (b.get("lessons") or {}).get(lid) or {}
        out["lessons"][lid] = {
            "manual": bool(x.get("manual") or y.get("manual")),
            "quiz_best": max(int(x.get("quiz_best") or 0), int(y.get("quiz_best") or 0)),
            "tf_best": max(int(x.get("tf_best") or 0), int(y.get("tf_best") or 0)),
            "seen": max(int(x.get("seen") or 0), int(y.get("seen") or 0)),
        }
    for cid in set(a.get("cards", {})) | set(b.get("cards", {})):
        x, y = (a.get("cards") or {}).get(cid), (b.get("cards") or {}).get(cid)
        if not x:
            out["cards"][cid] = y
        elif not y:
            out["cards"][cid] = x
        else:
            out["cards"][cid] = x if (x.get("last") or "") >= (y.get("last") or "") else y
    for qid in set(a.get("qs", {})) | set(b.get("qs", {})):
        x, y = (a.get("qs") or {}).get(qid), (b.get("qs") or {}).get(qid)
        if not x:
            out["qs"][qid] = y
        elif not y:
            out["qs"][qid] = x
        else:
            out["qs"][qid] = {
                "n": max(int(x.get("n") or 0), int(y.get("n") or 0)),
                "w": max(int(x.get("w") or 0), int(y.get("w") or 0)),
                "ok": max(int(x.get("ok") or 0), int(y.get("ok") or 0)),
                "last": x.get("last") if (x.get("last") or "") >= (y.get("last") or "") else y.get("last"),
                "last_ok": (x if (x.get("last") or "") >= (y.get("last") or "") else y).get("last_ok"),
            }
    for qid in set(a.get("errors", {})) | set(b.get("errors", {})):
        x, y = (a.get("errors") or {}).get(qid), (b.get("errors") or {}).get(qid)
        if not x:
            out["errors"][qid] = y
        elif not y:
            out["errors"][qid] = x
        else:
            out["errors"][qid] = {
                "n": max(int(x.get("n") or 0), int(y.get("n") or 0)),
                "ok_streak": min(int(x.get("ok_streak") or 0), int(y.get("ok_streak") or 0)),
                "pick": (x.get("pick") or y.get("pick") or "")[:4],
                "src": x.get("src") or y.get("src") or "app",
                "last": x.get("last") if (x.get("last") or "") >= (y.get("last") or "") else y.get("last"),
            }
    return out


def ensure_seeded(prog, catalog):
    """Add missed items from the class error log the first time progress is created."""
    if not catalog or prog.get("seeded"):
        return False
    for qid in catalog.get("seed_errors") or []:
        if qid not in prog["errors"]:
            prog["errors"][qid] = {"n": 1, "ok_streak": 0, "pick": "", "src": "log", "last": None}
    prog["seeded"] = True
    return True


def note_activity(prog, day=None):
    """Mark a study action today and update the daily streak (America/New_York)."""
    day = day or today()
    if day not in prog["days"]:
        prog["days"].append(day)
        prog["days"] = sorted(set(prog["days"]))[-120:]
    last = prog.get("streak_last")
    if last == day:
        return False
    if last:
        try:
            gap = (date.fromisoformat(day) - date.fromisoformat(last)).days
        except Exception:
            gap = 99
        prog["streak"] = (prog.get("streak") or 0) + 1 if gap == 1 else 1
    else:
        prog["streak"] = 1
    prog["streak_last"] = day
    prog["best_streak"] = max(int(prog.get("best_streak") or 0), int(prog["streak"]))
    return True


def lesson_map(catalog):
    return {x["id"]: x for x in (catalog or {}).get("lessons") or []}


def questions_for(catalog, lesson=None, kind=None):
    out = []
    for q in (catalog or {}).get("questions") or []:
        if lesson and q.get("lesson") != lesson:
            continue
        if kind and q.get("kind") != kind:
            continue
        out.append(q)
    return out


def terms_for(catalog, lesson=None):
    out = []
    for t in (catalog or {}).get("terms") or []:
        if lesson and t.get("lesson") != lesson:
            continue
        out.append(t)
    return out


def q_by_id(catalog, qid):
    for q in (catalog or {}).get("questions") or []:
        if q.get("id") == qid:
            return q
    return None


def term_by_id(catalog, tid):
    for t in (catalog or {}).get("terms") or []:
        if t.get("id") == tid:
            return t
    return None


def review_card(card, quality, day=None):
    """Simple spaced repetition. quality: 0 again, 1 hard, 2 good, 3 easy."""
    day = day or today()
    card = dict(card or {})
    ef = _float(card.get("ef"), 1.3, 3.0, 2.5)
    iv = _int(card.get("iv"), 0, 3650, 0)
    n = _int(card.get("n"), 0, 10000, 0)
    lapses = _int(card.get("l"), 0, 10000, 0)
    q = _int(quality, 0, 3, 0)
    if q == 0:
        ef = max(1.3, ef - 0.2)
        iv = 0
        lapses += 1
        due = day  # due again today
    elif q == 1:
        ef = max(1.3, ef - 0.15)
        iv = 1 if iv <= 0 else max(1, round(iv * 1.2))
        due = (date.fromisoformat(day) + timedelta(days=iv)).isoformat()
    else:
        if q == 3:
            ef = min(3.0, ef + 0.15)
        if n == 0:
            iv = 1 if q == 2 else 2
        elif n == 1:
            iv = 3 if q == 2 else 4
        else:
            iv = max(1, round(iv * ef * (1.3 if q == 3 else 1.0)))
        due = (date.fromisoformat(day) + timedelta(days=iv)).isoformat()
    n += 1
    return {"ef": round(ef, 3), "iv": int(iv), "n": n, "l": lapses, "due": due, "last": day}


def due_cards(catalog, prog, lesson=None, limit=20):
    day = today()
    terms = terms_for(catalog, lesson)
    cards = prog.get("cards") or {}
    unseen, due, later = [], [], []
    for t in terms:
        rec = cards.get(t["id"])
        if not rec:
            unseen.append(t)
        elif (rec.get("due") or day) <= day:
            due.append(t)
        else:
            later.append(t)
    # unseen first, then due (more lapses first), then upcoming if needed
    due.sort(key=lambda t: -int((cards.get(t["id"]) or {}).get("l") or 0))
    queue = unseen + due
    if len(queue) < limit:
        later.sort(key=lambda t: (cards.get(t["id"]) or {}).get("due") or "9999")
        queue += later
    return queue[:limit]


def grade_answer(q, pick):
    """pick is 'A'/'B'/... or 'V'/'F'. Returns (ok, correct_letter)."""
    if not q:
        return False, ""
    correct = str(q.get("answer") or "").strip().upper()[:1]
    got = str(pick or "").strip().upper()[:1]
    if q.get("kind") == "tf":
        # UI may send 0/1 or V/F or A/B
        trans = {"0": "V", "1": "F", "A": "V", "B": "F", "V": "V", "F": "F", "T": "V"}
        got = trans.get(got, got)
        correct = trans.get(correct, correct)
    return got == correct and bool(correct), correct


def record_answer(prog, q, pick, ok):
    """Update per-question stats and the missed-item list."""
    if not q:
        return
    qid = q["id"]
    rec = prog.setdefault("qs", {}).setdefault(qid, {"n": 0, "w": 0, "ok": 0, "last": None, "last_ok": False})
    rec["n"] = int(rec.get("n") or 0) + 1
    rec["last"] = today()
    rec["last_ok"] = bool(ok)
    if ok:
        rec["ok"] = int(rec.get("ok") or 0) + 1
        err = (prog.get("errors") or {}).get(qid)
        if err:
            err["ok_streak"] = int(err.get("ok_streak") or 0) + 1
            err["last"] = today()
            if err["ok_streak"] >= 2:
                prog["errors"].pop(qid, None)
    else:
        rec["w"] = int(rec.get("w") or 0) + 1
        err = prog.setdefault("errors", {}).setdefault(qid, {"n": 0, "ok_streak": 0, "pick": "", "src": "app", "last": None})
        err["n"] = int(err.get("n") or 0) + 1
        err["ok_streak"] = 0
        err["pick"] = str(pick or "")[:4]
        err["last"] = today()
        if not err.get("src"):
            err["src"] = "app"
    lid = q.get("lesson")
    if lid:
        ls = prog.setdefault("lessons", {}).setdefault(lid, {"manual": False, "quiz_best": 0, "tf_best": 0, "seen": 0})
        ls["seen"] = int(ls.get("seen") or 0) + 1


def record_quiz_score(prog, lesson, kind, pct):
    if not lesson:
        return
    ls = prog.setdefault("lessons", {}).setdefault(lesson, {"manual": False, "quiz_best": 0, "tf_best": 0, "seen": 0})
    key = "tf_best" if kind == "tf" else "quiz_best"
    ls[key] = max(int(ls.get(key) or 0), int(pct))


def mark_manual(prog, lesson):
    ls = prog.setdefault("lessons", {}).setdefault(lesson, {"manual": False, "quiz_best": 0, "tf_best": 0, "seen": 0})
    ls["manual"] = True


def pick_questions(catalog, prog, *, lesson=None, kind="mc", n=10, prefer_errors=True, seed=None):
    pool = questions_for(catalog, lesson, kind)
    if not pool:
        return []
    errs = []
    rest = []
    eids = set((prog or {}).get("errors") or {})
    for q in pool:
        (errs if (prefer_errors and q["id"] in eids) else rest).append(q)
    rng = random.Random(seed if seed is not None else (today() + str(n) + (lesson or "") + (kind or "any")))
    rng.shuffle(errs)
    # mix lessons when lesson is None
    if lesson is None:
        buckets = {}
        for q in rest:
            buckets.setdefault(q.get("lesson") or "x", []).append(q)
        for v in buckets.values():
            rng.shuffle(v)
        mixed = []
        while any(buckets.values()):
            for k in list(buckets):
                if buckets[k]:
                    mixed.append(buckets[k].pop())
        rest = mixed
    else:
        rng.shuffle(rest)
    # unseen / previously missed first among the rest
    qs = (prog or {}).get("qs") or {}
    rest.sort(key=lambda q: (int((qs.get(q["id"]) or {}).get("n") or 0), -int((qs.get(q["id"]) or {}).get("w") or 0)))
    picked, seen = [], set()
    for q in errs + rest:
        if q["id"] in seen:
            continue
        picked.append(q)
        seen.add(q["id"])
        if len(picked) >= n:
            break
    return picked


def official_exam(catalog, prog, seed=None):
    """110 mixed multiple-choice items, PSI-style count (not official PSI items)."""
    n = min(EXAM_Q, len(questions_for(catalog, kind="mc")))
    return pick_questions(catalog, prog, kind="mc", n=n, prefer_errors=True, seed=seed)


def score_pct(ok, total):
    if not total:
        return 0
    return int(round(100.0 * ok / total))


def days_until(exam_date):
    if not exam_date:
        return None
    try:
        return (date.fromisoformat(exam_date) - date.fromisoformat(today())).days
    except Exception:
        return None


def lesson_progress(catalog, prog, lid):
    terms = terms_for(catalog, lid)
    qs_mc = questions_for(catalog, lid, "mc")
    qs_tf = questions_for(catalog, lid, "tf")
    cards = prog.get("cards") or {}
    known = 0
    for t in terms:
        rec = cards.get(t["id"])
        if rec and int(rec.get("n") or 0) >= 2 and int(rec.get("iv") or 0) >= 3:
            known += 1
    rec = (prog.get("lessons") or {}).get(lid) or {}
    seen_ids = {qid for qid, r in (prog.get("qs") or {}).items() if r.get("n") and any(q["id"] == qid for q in qs_mc + qs_tf)}
    # faster: count qs whose prefix lesson matches via catalog lookup
    qids = {q["id"] for q in qs_mc + qs_tf}
    practiced = sum(1 for qid in qids if (prog.get("qs") or {}).get(qid, {}).get("n"))
    total_q = len(qids)
    pct = 0
    if rec.get("manual"):
        pct += 20
    if terms:
        pct += int(40 * known / len(terms))
    elif rec.get("manual"):
        pct += 10
    if total_q:
        pct += int(20 * practiced / total_q)
        best = max(int(rec.get("quiz_best") or 0), int(rec.get("tf_best") or 0))
        pct += int(20 * best / 100)
    else:
        pct += 10 if rec.get("manual") else 0
    return {
        "pct": min(100, pct),
        "terms": len(terms),
        "known": known,
        "q_total": total_q,
        "q_done": practiced,
        "quiz_best": int(rec.get("quiz_best") or 0),
        "tf_best": int(rec.get("tf_best") or 0),
        "manual": bool(rec.get("manual")),
        "mc": len(qs_mc),
        "tf": len(qs_tf),
    }


def overall_progress(catalog, prog):
    lessons = [x for x in (catalog or {}).get("lessons") or [] if x["id"] != "repaso"]
    if not lessons:
        lessons = (catalog or {}).get("lessons") or []
    rows = [lesson_progress(catalog, prog, x["id"]) for x in lessons]
    if not rows:
        return 0
    return int(round(sum(r["pct"] for r in rows) / len(rows)))


def counts(catalog):
    cat = catalog or {}
    qs = cat.get("questions") or []
    return {
        "lessons": len(cat.get("lessons") or []),
        "terms": len(cat.get("terms") or []),
        "questions": len(qs),
        "mc": sum(1 for q in qs if q.get("kind") == "mc"),
        "tf": sum(1 for q in qs if q.get("kind") == "tf"),
    }
