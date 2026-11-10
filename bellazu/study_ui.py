"""Streamlit UI for the BellaZu study section (Spanish-first, phone-friendly).

No listing or RentCast calls. Progress is mutated in the dict the app already
stores with saved homes, then on_change() writes it (browser + encrypted copy).
"""
from __future__ import annotations

import html as H
import time

import streamlit as st

from . import study

TTS_CSS = """
.bz-ttsbar {display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 12px}
.bz-ttsbar button {min-height:2.8rem; padding:0 1.15rem; border-radius:999px; border:1px solid #fff;
  background:transparent; color:#fff; text-transform:uppercase; letter-spacing:.06em; font-size:.8rem; cursor:pointer}
.bz-ttsbar button:hover {background:#fff; color:#141414}
"""
TTS_JS = """
export default function({ data, parentElement }) {
  const parts = (data && data.parts) || [];
  const lang = (data && data.lang) || "es-US";
  let box = parentElement.__box;
  if (!box) {
    box = document.createElement("div");
    box.className = "bz-ttsbar";
    box.innerHTML = '<button type="button" data-a="play"></button><button type="button" data-a="stop"></button>';
    parentElement.appendChild(box);
    parentElement.__box = box;
  }
  const play = box.querySelector('[data-a=play]');
  const stop = box.querySelector('[data-a=stop]');
  play.textContent = (data && data.play) || "Listen";
  stop.textContent = (data && data.stop) || "Stop";
  parentElement.__parts = parts;
  parentElement.__lang = lang;
  play.onclick = () => {
    try { window.speechSynthesis.cancel(); } catch (e) {}
    const list = parentElement.__parts || [];
    const rec = (i) => {
      if (i >= list.length) return;
      const u = new SpeechSynthesisUtterance(list[i]);
      u.lang = parentElement.__lang || "es-US";
      u.rate = 0.95;
      u.onend = () => rec(i + 1);
      try { window.speechSynthesis.speak(u); } catch (e) {}
    };
    rec(0);
  };
  stop.onclick = () => { try { window.speechSynthesis.cancel(); } catch (e) {} };
}
"""
_TTS = st.components.v2.component("bz_study_tts", css=TTS_CSS, js=TTS_JS)

SECTIONS = [
    ("plan", "Plan", "Plan"),
    ("manual", "Manual", "Manual"),
    ("cards", "Cards", "Tarjetas"),
    ("quiz", "Quiz", "Cuestionario"),
    ("tf", "True/False", "Verdadero/Falso"),
    ("exam", "Mock exam", "Simulacro"),
    ("tutor", "Tutor mode", "Modo tutor"),
    ("errors", "Missed items", "Mis errores"),
    ("podcast", "Podcast", "Podcast"),
]


def _es():
    return st.session_state.get("lang", "EN") == "ES"


def T(en, es):
    return es if _es() else en


def esc(s):
    return H.escape(s or "").replace("$", "&#36;")


def hwrite(s):
    st.markdown(s.replace("$", "&#36;"), unsafe_allow_html=True)


def _css():
    hwrite("""<style>
.bz-st-bar{height:8px;background:#2E2E2E;border-radius:99px;overflow:hidden;margin:.3rem 0 .85rem}
.bz-st-bar i{display:block;height:100%;background:#F4A7BB;border-radius:99px}
.bz-st-box{border:1px solid #F4A7BB;border-radius:16px;padding:12px 14px;margin:10px 0;color:#fff;line-height:1.45;font-size:.95rem}
.bz-st-box .k{color:#F4A7BB;text-transform:uppercase;letter-spacing:.08em;font-size:.72rem;margin-bottom:6px}
.bz-st-gk{border:1px dashed #A9A9A9;border-radius:12px;padding:8px 12px;color:#CFCFCF;font-size:.9rem;margin:8px 0}
.bz-st-card{border:1px solid #3A3A3A;border-radius:24px;padding:32px 18px;text-align:center;min-height:190px;
  display:flex;flex-direction:column;justify-content:center;margin:12px 0;background:#1B1B1B}
.bz-st-card .t{font-size:1.45rem;font-weight:600;line-height:1.25;color:#fff}
.bz-st-card .en{color:#F4A7BB;margin-top:10px;font-size:1rem}
.bz-st-card .def{color:#EEEEEE;font-size:1.05rem;line-height:1.45;text-align:left}
.bz-st-ok{color:#8FE3B5;font-weight:600}
.bz-st-no{color:#FF9DB5;font-weight:600}
.bz-st-meta{color:#A9A9A9;font-size:.88rem;line-height:1.45;margin:0 0 12px}
.bz-st-stem{font-size:1.08rem;line-height:1.45;margin:8px 0 14px;color:#fff}
.bz-st-row{border-top:1px solid #2E2E2E;padding:10px 0}
</style>""")


def _title(lesson):
    if not lesson:
        return T("All lessons", "Todas las clases")
    return lesson["title_es"] if _es() else lesson["title_en"]


def _bar(pct):
    p = max(0, min(100, int(pct)))
    hwrite(f"<div class='bz-st-bar' aria-label='{p}%'><i style='width:{p}%'></i></div>")


def _lessons(cat, include_all=True, with_terms=False):
    rows = list(cat.get("lessons") or [])
    if with_terms:
        have = {t["lesson"] for t in cat.get("terms") or []}
        # keep lessons even without terms if include_all path is for quizzes
    opts = []
    if include_all:
        opts.append(("all", T("All lessons", "Todas las clases")))
    for x in rows:
        opts.append((x["id"], _title(x)))
    return opts


def _pick_lesson(cat, key, include_all=True, with_terms=False):
    opts = _lessons(cat, include_all=include_all, with_terms=with_terms)
    if with_terms:
        have = {t["lesson"] for t in cat.get("terms") or []}
        keep = [("all", T("All lessons", "Todas las clases"))] if include_all else []
        keep += [(i, n) for i, n in opts if i == "all" or i in have]
        if len(keep) > (1 if include_all else 0):
            opts = keep
    ids = [o[0] for o in opts]
    labels = {o[0]: o[1] for o in opts}
    cur = st.session_state.get(key)
    if cur not in ids:
        st.session_state[key] = ids[0] if ids else "all"
    pick = st.selectbox(T("Lesson", "Clase"), ids, key=key, format_func=lambda i: labels.get(i, i))
    return None if pick == "all" else pick


def _render_blocks(blocks):
    for b in blocks or []:
        kind = b.get("t")
        if kind == "h":
            st.markdown(f"**{b.get('x') or ''}**")
        elif kind == "p":
            st.markdown((b.get("x") or "").replace("$", "\\$"))
        elif kind == "ul":
            st.markdown("\n".join(f"- {(x or '').replace('$', '\\$')}" for x in b.get("xs") or []))
        elif kind == "clave":
            badge = T(" · general knowledge", " · conocimiento general") if b.get("gk") else ""
            hwrite(f"<div class='bz-st-box'><div class='k'>{esc(T('To memorize', 'Para memorizar'))}{esc(badge)}</div>{esc(b.get('x'))}</div>")
        elif kind == "gk":
            hwrite(f"<div class='bz-st-gk'>{esc(T('General knowledge:', 'Conocimiento general:'))} {esc(b.get('x'))}</div>")
        elif kind == "table":
            heads = b.get("heads") or []
            rows = b.get("rows") or []
            width = max([len(heads)] + [len(r) for r in rows] + [0])
            if not width:
                continue
            def pad(row):
                row = list(row) + [""] * (width - len(row))
                return "|" + "|".join((c or "").replace("|", "/") for c in row) + "|"
            lines = []
            if heads:
                lines.append(pad(heads))
                lines.append("|" + "|".join("---" for _ in range(width)) + "|")
            for r in rows:
                lines.append(pad(r))
            if lines:
                st.markdown("\n".join(lines).replace("$", "\\$"))


def _choices(q):
    if q.get("kind") == "tf":
        return [("V", T("True", "Verdadero")), ("F", T("False", "Falso"))]
    letters = "ABCD"
    return [(letters[i], c) for i, c in enumerate(q.get("choices") or [])]


def _stem(q):
    badge = f" <span class='bz-st-gk' style='display:inline;border:none;padding:0'>({esc(T('general knowledge', 'conocimiento general'))})</span>" if q.get("gk") else ""
    hwrite(f"<div class='bz-st-stem'>{esc(q.get('stem'))}{badge}</div>")


def _explain(q, ok, correct):
    klass = "bz-st-ok" if ok else "bz-st-no"
    label = T("Correct", "Correcto") if ok else T(f"Not quite. The answer is {correct}.", f"Casi. La respuesta es {correct}.")
    hwrite(f"<p class='{klass}'>{esc(label)}</p>")
    if q.get("explain"):
        st.markdown((q.get("explain") or "").replace("$", "\\$"))


# ------------------------------------------------------------------ sections
def _plan(cat, prog, on_change):
    streak = int(prog.get("streak") or 0)
    best = int(prog.get("best_streak") or 0)
    if streak:
        hwrite(f"<p class='bz-st-fire'>🔥 {esc(T(f'{streak} day streak' if streak != 1 else '1 day streak', f'{streak} días seguidos' if streak != 1 else '1 día seguido'))}"
               f"{' · ' + esc(T(f'best {best}', f'mejor {best}')) if best else ''}</p>")
    else:
        hwrite(f"<p class='bz-st-meta'>{esc(T('Study a little today to start a streak.', 'Estudie un poco hoy para empezar una racha.'))}</p>")

    overall = study.overall_progress(cat, prog)
    hwrite(f"<div class='bz-st-meta'>{esc(T('Overall progress', 'Progreso general'))} · {overall}%</div>")
    _bar(overall)

    ex = cat.get("exam_style") or {}
    hwrite("<div class='bz-st-meta'>" + esc(T(
        f"Official NJ salesperson exam (PSI bulletin, updated 1 Feb 2026): {ex.get('questions', 110)} multiple-choice questions, "
        f"{ex.get('minutes', 240)} minutes, passing score {ex.get('pass_pct', 70)}% ({ex.get('pass_count', 77)} correct).",
        f"Examen oficial de vendedor de NJ (boletín de PSI, actualizado el 1 feb 2026): {ex.get('questions', 110)} preguntas de selección múltiple, "
        f"{ex.get('minutes', 240)} minutos, se aprueba con {ex.get('pass_pct', 70)}% ({ex.get('pass_count', 77)} correctas)."
    )) + "</div>")

    col1, col2 = st.columns(2)
    with col1:
        if "st_exam_date" not in st.session_state:
            default = None
            try:
                if prog.get("exam_date"):
                    default = __import__("datetime").date.fromisoformat(prog["exam_date"])
            except Exception:
                default = None
            st.session_state.st_exam_date = default
        picked = st.date_input(T("Exam date", "Fecha del examen"), key="st_exam_date", format="MM/DD/YYYY")
        new = picked.isoformat() if picked else None
        if new != prog.get("exam_date"):
            prog["exam_date"] = new
            on_change()
        left = study.days_until(prog.get("exam_date"))
        if left is None:
            st.caption(T("Pick a date to see a countdown.", "Elija una fecha para ver la cuenta regresiva."))
        elif left > 1:
            st.caption(T(f"{left} days left.", f"Faltan {left} días."))
        elif left == 1:
            st.caption(T("Tomorrow.", "Mañana."))
        elif left == 0:
            st.caption(T("That's today.", "Es hoy."))
        else:
            st.caption(T(f"{abs(left)} days ago.", f"Fue hace {abs(left)} días."))
    with col2:
        if "st_target" not in st.session_state:
            st.session_state.st_target = int(prog.get("target") or 75)
        tg = st.slider(T("Target score (%)", "Meta de puntaje (%)"), 60, 100, step=5, key="st_target")
        if tg != prog.get("target"):
            prog["target"] = int(tg)
            on_change()
        st.caption(T(f"The official passing score is {ex.get('pass_pct', 70)}%.", f"El puntaje oficial para aprobar es {ex.get('pass_pct', 70)}%."))

    st.markdown(f"**{T('Progress by lesson', 'Progreso por clase')}**")
    for les in cat.get("lessons") or []:
        info = study.lesson_progress(cat, prog, les["id"])
        bits = [f"{info['pct']}%"]
        if info["terms"]:
            bits.append(T(f"{info['known']}/{info['terms']} cards", f"{info['known']}/{info['terms']} tarjetas"))
        if info["mc"]:
            bits.append(T(f"{info['mc']} quiz", f"{info['mc']} cuestionario"))
        if info["tf"]:
            bits.append(T(f"{info['tf']} T/F", f"{info['tf']} V/F"))
        if not info["mc"] and not info["tf"]:
            bits.append(T("no quiz yet", "aún sin cuestionario"))
        if info["manual"]:
            bits.append(T("manual read", "manual leído"))
        hwrite(f"<div class='bz-st-row'><b>{esc(_title(les))}</b> · {esc(' · '.join(bits))}</div>")
        _bar(info["pct"])

    errs = len(prog.get("errors") or {})
    if errs:
        st.info(T(f"{errs} missed item(s) will show up more often.", f"{errs} error(es) volverán a salir con más frecuencia."))

    hwrite("<div class='bz-st-gk'>" + esc(T(
        "Photo of a problem (Snap and Solve) and a live AI chat are not built in: this app has no AI service connected. Send a photo in the chat and we can go through it there.",
        "Foto de un ejercicio (Snap and Solve) y un chat de IA en vivo no están aquí: esta app no tiene un servicio de IA conectado. Envíe la foto por el chat y lo vemos juntas."
    )) + "</div>")


def _manual(cat, prog, on_change):
    lid = _pick_lesson(cat, "st_man_l", include_all=False)
    les = study.lesson_map(cat).get(lid)
    if not les:
        return
    hwrite(f"<p class='bz-st-meta'>{esc(les.get('subtitle') or '')}"
           + (f" · {esc(T('Units', 'Unidades'))} {esc(les.get('units'))}" if les.get("units") else "") + "</p>")
    if les.get("claves"):
        hwrite(f"<div class='bz-st-box'><div class='k'>{esc(T('To memorize', 'Para memorizar'))}</div>"
               + "".join(f"<p>{esc(c)}</p>" for c in les["claves"]) + "</div>")
    for note in les.get("gk_notes") or []:
        hwrite(f"<div class='bz-st-gk'>{esc(T('General knowledge:', 'Conocimiento general:'))} {esc(note)}</div>")
    for sec in les.get("sections") or []:
        with st.expander(sec.get("h") or T("Section", "Apartado"), expanded=False):
            _render_blocks(sec.get("blocks"))
    if st.button(T("Mark this lesson as read", "Marcar esta clase como leída"), key="stb_man_read", type="primary", width="stretch"):
        study.mark_manual(prog, lid)
        study.note_activity(prog)
        on_change()
        st.success(T("Saved.", "Guardado."))


def _cards(cat, prog, on_change):
    lid = _pick_lesson(cat, "st_card_l", include_all=True, with_terms=True)
    terms = study.terms_for(cat, lid)
    if not terms:
        st.info(T("This lesson has no glossary cards yet.", "Esta clase aún no tiene tarjetas de glosario."))
        return
    st.session_state.setdefault("st_card_lang", "es")
    side = st.segmented_control(T("Show term in", "Mostrar el término en"), ["es", "en"], key="st_card_lang",
                                format_func=lambda k: "Español" if k == "es" else "English")
    ss = st.session_state
    queue = ss.get("st_card_q")
    q_les = ss.get("st_card_les")
    if not queue or q_les != (lid or "all"):
        ss.st_card_q = [t["id"] for t in study.due_cards(cat, prog, lid, limit=30)]
        ss.st_card_les = lid or "all"
        ss.st_card_i = 0
        ss.st_card_flip = False
    queue = ss.st_card_q
    i = int(ss.get("st_card_i") or 0)
    if i >= len(queue):
        st.success(T("That set is done. Start another round when ready.", "Terminó esta ronda. Puede empezar otra cuando quiera."))
        if st.button(T("Another round", "Otra ronda"), key="stb_card_more"):
            ss.st_card_q = [t["id"] for t in study.due_cards(cat, prog, lid, limit=30)]
            ss.st_card_i = 0
            ss.st_card_flip = False
            st.rerun()
        return
    term = study.term_by_id(cat, queue[i])
    if not term:
        ss.st_card_i = i + 1
        st.rerun()
        return
    st.caption(T(f"Card {i+1} of {len(queue)}", f"Tarjeta {i+1} de {len(queue)}"))
    front = term.get("es") if side != "en" else (term.get("en") or term.get("es"))
    other = term.get("en") if side != "en" else term.get("es")
    if not ss.get("st_card_flip"):
        extra = f"<div class='en'>{esc(other)}</div>" if other and other != front else ""
        hwrite(f"<div class='bz-st-card'><div class='t'>{esc(front)}</div>{extra}</div>")
        if st.button(T("Show definition", "Ver definición"), key="stb_card_show", type="primary", width="stretch"):
            ss.st_card_flip = True
            st.rerun()
    else:
        gk = ""
        if term.get("gk") or term.get("gk_note"):
            gk = f"<div class='en'>{esc(T('General knowledge', 'Conocimiento general'))}"
            if term.get("gk_note"):
                gk += f": {esc(term['gk_note'])}"
            gk += "</div>"
        hwrite(f"<div class='bz-st-card'><div class='t'>{esc(front)}</div>"
               f"<div class='en'>{esc(other)}</div><div class='def'>{esc(term.get('def'))}</div>{gk}</div>")
        cols = st.columns(4)
        labels = [
            (0, T("Again", "Otra vez")),
            (1, T("Hard", "Difícil")),
            (2, T("Good", "Bien")),
            (3, T("Easy", "Fácil")),
        ]
        clicked = None
        for col, (qval, lab) in zip(cols, labels):
            if col.button(lab, key=f"stb_card_q{qval}", width="stretch"):
                clicked = qval
        if clicked is not None:
            rec = (prog.get("cards") or {}).get(term["id"])
            prog.setdefault("cards", {})[term["id"]] = study.review_card(rec, clicked)
            study.note_activity(prog)
            on_change()
            ss.st_card_i = i + 1
            ss.st_card_flip = False
            st.rerun()


def _start_set(ss, key, ids):
    ss[key] = {"ids": ids, "i": 0, "answers": {}, "done": False}


def _run_set(cat, prog, on_change, *, key, kind, title):
    ss = st.session_state
    data = ss.get(key)
    if not data or not data.get("ids"):
        return
    ids = data["ids"]
    if data.get("done"):
        ok = sum(1 for qid, pick in data["answers"].items()
                 if study.grade_answer(study.q_by_id(cat, qid), pick)[0])
        total = len(ids)
        pct = study.score_pct(ok, total)
        st.success(T(f"Score: {ok} of {total} ({pct}%)", f"Puntaje: {ok} de {total} ({pct}%)"))
        target = int(prog.get("target") or 75)
        if pct >= target:
            st.caption(T(f"That meets the {target}% target.", f"Alcanzó la meta del {target}%."))
        else:
            st.caption(T(f"Target is {target}%. Try the missed items next.", f"La meta es {target}%. Luego practique lo que falló."))
        for n, qid in enumerate(ids, 1):
            q = study.q_by_id(cat, qid)
            if not q:
                continue
            pick = data["answers"].get(qid)
            good, correct = study.grade_answer(q, pick)
            st.markdown(f"**{n}. {q.get('stem')}**")
            _explain(q, good, correct)
            st.divider()
        if st.button(T("Practice again", "Practicar de nuevo"), key=f"b{key}_again"):
            ss.pop(key, None)
            st.rerun()
        return
    i = int(data.get("i") or 0)
    if i >= len(ids):
        # finalize
        lesson_ids = set()
        for qid, pick in data["answers"].items():
            q = study.q_by_id(cat, qid)
            ok, _ = study.grade_answer(q, pick)
            study.record_answer(prog, q, pick, ok)
            if q:
                lesson_ids.add(q.get("lesson"))
        ok = sum(1 for qid, pick in data["answers"].items()
                 if study.grade_answer(study.q_by_id(cat, qid), pick)[0])
        pct = study.score_pct(ok, len(ids))
        if len(lesson_ids) == 1:
            study.record_quiz_score(prog, next(iter(lesson_ids)), kind, pct)
        study.note_activity(prog)
        on_change()
        data["done"] = True
        st.rerun()
        return
    q = study.q_by_id(cat, ids[i])
    st.caption(f"{title} · {i+1}/{len(ids)}")
    if not q:
        data["i"] = i + 1
        st.rerun()
        return
    _stem(q)
    pending = data.get("pending")
    if pending and pending.get("i") == i:
        ok, correct = pending["ok"], pending["correct"]
        _explain(q, ok, correct)
        if st.button(T("Next", "Siguiente"), key=f"b{key}_next", type="primary", width="stretch"):
            data["pending"] = None
            data["i"] = i + 1
            st.rerun()
        return
    for letter, text in _choices(q):
        if st.button(f"{letter}) {text}", key=f"b{key}_{i}_{letter}", width="stretch"):
            ok, correct = study.grade_answer(q, letter)
            data.setdefault("answers", {})[q["id"]] = letter
            data["pending"] = {"i": i, "ok": ok, "correct": correct}
            st.rerun()


def _quiz(cat, prog, on_change):
    lid = _pick_lesson(cat, "st_quiz_l", include_all=True)
    st.session_state.setdefault("st_quiz_n", 10)
    n = st.selectbox(T("How many questions", "Cuántas preguntas"), [5, 10, 15, 20], key="st_quiz_n")
    pool = study.questions_for(cat, lid, "mc")
    if not pool:
        st.info(T("No multiple-choice questions for this lesson yet.", "Aún no hay preguntas de selección múltiple para esta clase."))
        return
    if st.button(T("Start quiz", "Empezar cuestionario"), key="stb_quiz_go", type="primary", width="stretch"):
        picked = study.pick_questions(cat, prog, lesson=lid, kind="mc", n=min(int(n), len(pool)))
        _start_set(st.session_state, "st_quiz", [q["id"] for q in picked])
        st.rerun()
    _run_set(cat, prog, on_change, key="st_quiz", kind="mc", title=T("Quiz", "Cuestionario"))


def _tf(cat, prog, on_change):
    lid = _pick_lesson(cat, "st_tf_l", include_all=True)
    st.session_state.setdefault("st_tf_n", 10)
    n = st.selectbox(T("How many statements", "Cuántas afirmaciones"), [5, 10, 15, 20], key="st_tf_n")
    pool = study.questions_for(cat, lid, "tf")
    if not pool:
        st.info(T("No true/false statements for this lesson yet.", "Aún no hay afirmaciones verdadero/falso para esta clase."))
        return
    if st.button(T("Start true/false", "Empezar verdadero/falso"), key="stb_tf_go", type="primary", width="stretch"):
        picked = study.pick_questions(cat, prog, lesson=lid, kind="tf", n=min(int(n), len(pool)))
        _start_set(st.session_state, "st_tf", [q["id"] for q in picked])
        st.rerun()
    _run_set(cat, prog, on_change, key="st_tf", kind="tf", title=T("True/False", "Verdadero/Falso"))


@st.fragment(run_every=1)
def _exam_clock():
    end = st.session_state.get("st_exam_end")
    if not end or st.session_state.get("st_exam_over"):
        return
    left = int(end - time.time())
    if left <= 0:
        st.session_state.st_exam_over = True
        st.warning(T("Time is up. Your answers are being scored.", "Se acabó el tiempo. Se están calificando las respuestas."))
        st.rerun()
        return
    m, s = divmod(max(left, 0), 60)
    h, m = divmod(m, 60)
    label = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    st.caption(T(f"Time left: {label}", f"Tiempo restante: {label}"))


def _exam(cat, prog, on_change):
    ss = st.session_state
    ex = cat.get("exam_style") or {}
    official_n = min(int(ex.get("questions") or 110), len(study.questions_for(cat, kind="mc")))
    st.session_state.setdefault("st_exam_mode", "official")
    mode = st.segmented_control(T("Type", "Tipo"), ["official", "custom"], key="st_exam_mode",
                                format_func=lambda k: T("Official NJ style", "Examen estilo oficial NJ") if k == "official"
                                else T("Custom", "Personalizado"))
    n = official_n
    minutes = int(ex.get("minutes") or 240)
    if mode == "custom":
        lid = _pick_lesson(cat, "st_exam_l", include_all=True)
        opts_n = sorted({10, 25, 50, 75, official_n})
        st.session_state.setdefault("st_exam_n", 25 if 25 in opts_n else opts_n[0])
        st.session_state.setdefault("st_exam_min", 30)
        n = st.select_slider(T("Questions", "Preguntas"), options=opts_n, key="st_exam_n")
        minutes = st.select_slider(T("Minutes", "Minutos"), options=[10, 20, 30, 45, 90, 150, 240], key="st_exam_min")
    else:
        lid = None
        st.caption(T(
            f"{official_n} mixed multiple-choice questions, {minutes} minutes, explanations after you finish. "
            f"Passing score on the real exam is {ex.get('pass_pct', 70)}% ({ex.get('pass_count', 77)} correct). These are practice items from class notes, not PSI's official bank.",
            f"{official_n} preguntas mixtas de selección múltiple, {minutes} minutos, con explicación de cada una al terminar. "
            f"En el examen real se aprueba con {ex.get('pass_pct', 70)}% ({ex.get('pass_count', 77)} correctas). Estas son preguntas de práctica de sus notas, no el banco oficial de PSI."
        ))
    data = ss.get("st_exam")
    if not data or data.get("done"):
        if data and data.get("done"):
            ok = sum(1 for qid, pick in data["answers"].items()
                     if study.grade_answer(study.q_by_id(cat, qid), pick)[0])
            total = len(data["ids"])
            pct = study.score_pct(ok, total)
            target = int(prog.get("target") or 75)
            official_pass = int(ex.get("pass_pct") or 70)
            st.success(T(f"Score: {ok} of {total} ({pct}%)", f"Puntaje: {ok} de {total} ({pct}%)"))
            flags = []
            flags.append(T(f"Target {target}%: {'met' if pct >= target else 'not met'}",
                           f"Meta {target}%: {'alcanzada' if pct >= target else 'no alcanzada'}"))
            flags.append(T(f"Official 70% line: {'would pass' if pct >= official_pass else 'would not pass'}",
                           f"Línea oficial del 70%: {'aprobaría' if pct >= official_pass else 'no aprobaría'}"))
            st.caption(" · ".join(flags))
            st.markdown(f"**{T('Every question, with an explanation', 'Cada pregunta, con su explicación')}**")
            for n_, qid in enumerate(data["ids"], 1):
                q = study.q_by_id(cat, qid)
                if not q:
                    continue
                pick = data["answers"].get(qid)
                good, correct = study.grade_answer(q, pick)
                chose = pick or "—"
                st.markdown(f"**{n_}. {q.get('stem')}**")
                st.caption(T(f"Your answer: {chose} · Correct: {correct}", f"Su respuesta: {chose} · Correcta: {correct}"))
                _explain(q, good, correct)
                st.divider()
        if st.button(T("Start mock exam", "Empezar simulacro"), key="stb_exam_go", type="primary", width="stretch"):
            if mode == "official":
                picked = study.official_exam(cat, prog)
            else:
                pool = study.questions_for(cat, lid, "mc")
                picked = study.pick_questions(cat, prog, lesson=lid, kind="mc", n=min(int(n), len(pool)))
            ss.st_exam = {"ids": [q["id"] for q in picked], "i": 0, "answers": {}, "done": False, "n": len(picked)}
            ss.st_exam_end = time.time() + int(minutes) * 60
            ss.st_exam_over = False
            st.rerun()
        return

    if ss.get("st_exam_over") and not data.get("done"):
        # time expired: score whatever was answered (unanswered count as wrong)
        for qid in data["ids"]:
            data["answers"].setdefault(qid, "")
        _finish_exam(cat, prog, on_change, data)
        st.rerun()
        return

    _exam_clock()
    i = int(data.get("i") or 0)
    ids = data["ids"]
    if i >= len(ids):
        _finish_exam(cat, prog, on_change, data)
        st.rerun()
        return
    q = study.q_by_id(cat, ids[i])
    st.caption(T(f"Question {i+1} of {len(ids)}", f"Pregunta {i+1} de {len(ids)}"))
    if not q:
        data["i"] = i + 1
        st.rerun()
        return
    _stem(q)
    for letter, text in _choices(q):
        if st.button(f"{letter}) {text}", key=f"stb_ex_{i}_{letter}", width="stretch"):
            data.setdefault("answers", {})[q["id"]] = letter
            data["i"] = i + 1
            st.rerun()
    if st.button(T("Skip", "Saltar"), key=f"stb_ex_skip_{i}", type="tertiary"):
        data.setdefault("answers", {})[q["id"]] = ""
        data["i"] = i + 1
        st.rerun()


def _finish_exam(cat, prog, on_change, data):
    for qid, pick in data["answers"].items():
        q = study.q_by_id(cat, qid)
        ok, _ = study.grade_answer(q, pick)
        study.record_answer(prog, q, pick, ok)
    study.note_activity(prog)
    on_change()
    data["done"] = True
    st.session_state.st_exam_over = True


def _tutor(cat, prog, on_change):
    ss = st.session_state
    lid = _pick_lesson(cat, "st_tu_l", include_all=True)
    pool = study.questions_for(cat, lid, "mc") or study.questions_for(cat, lid, None)
    if not pool:
        st.info(T("No questions for this lesson yet.", "Aún no hay preguntas para esta clase."))
        return
    st.caption(T(
        "Hints come first. The full explanation waits until after an answer.",
        "Primero las pistas. La explicación completa espera a que conteste."
    ))
    state = ss.get("st_tutor")
    if not state:
        if st.button(T("Next prompt", "Siguiente consigna"), key="stb_tu_new", type="primary", width="stretch"):
            picked = study.pick_questions(cat, prog, lesson=lid, kind=None, n=1)
            if picked:
                ss.st_tutor = {"id": picked[0]["id"], "hints": 0, "pick": None}
            st.rerun()
        return
    q = study.q_by_id(cat, state["id"])
    if not q:
        ss.pop("st_tutor", None)
        st.rerun()
        return
    _stem(q)
    hints = q.get("hints") or []
    shown = int(state.get("hints") or 0)
    for i, h in enumerate(hints[:shown]):
        st.info(T(f"Hint {i+1}: ", f"Pista {i+1}: ") + h)
    if shown < len(hints) and state.get("pick") is None:
        if st.button(T("Give me a hint", "Dame una pista"), key="stb_tu_hint", width="stretch"):
            state["hints"] = shown + 1
            st.rerun()
    if state.get("pick") is None:
        st.caption(T("When ready, choose an answer:", "Cuando esté lista, elija una respuesta:"))
        for letter, text in _choices(q):
            if st.button(f"{letter}) {text}", key=f"stb_tu_{letter}", width="stretch"):
                ok, correct = study.grade_answer(q, letter)
                study.record_answer(prog, q, letter, ok)
                study.note_activity(prog)
                on_change()
                state["pick"] = letter
                state["ok"] = ok
                state["correct"] = correct
                st.rerun()
    else:
        _explain(q, state.get("ok"), state.get("correct"))
        if st.button(T("Another question", "Otra pregunta"), key="stb_tu_next", type="primary", width="stretch"):
            picked = study.pick_questions(cat, prog, lesson=lid, kind=None, n=1)
            ss.st_tutor = {"id": picked[0]["id"], "hints": 0, "pick": None} if picked else None
            st.rerun()


def _errors(cat, prog, on_change):
    eids = list((prog.get("errors") or {}).keys())
    if not eids:
        st.success(T("Nothing in the missed list right now. Missed answers will show up here.",
                     "No hay nada en la lista de errores ahora. Lo que falle en la app aparecerá aquí."))
        return
    st.caption(T(f"{len(eids)} item(s). They also come up more often in quizzes and the mock exam.",
                 f"{len(eids)} ítem(s). También salen más seguido en los cuestionarios y el simulacro."))
    if st.button(T("Practice missed items", "Practicar lo que fallé"), key="stb_err_go", type="primary", width="stretch"):
        ids = [i for i in eids if study.q_by_id(cat, i)]
        _start_set(st.session_state, "st_err", ids)
        st.rerun()
    _run_set(cat, prog, on_change, key="st_err", kind="mc", title=T("Missed items", "Mis errores"))
    for qid in eids:
        q = study.q_by_id(cat, qid)
        rec = (prog.get("errors") or {}).get(qid) or {}
        if not q:
            continue
        src = rec.get("src") or "app"
        src_l = T("from the class error log", "del registro de errores de clase") if src == "log" else T("missed in the app", "fallado en la app")
        st.markdown(f"**{q.get('stem')}**")
        st.caption(f"{src_l} · {T('times missed', 'veces fallado')}: {rec.get('n') or 1}")


def _podcast(cat, _prog, on_change):
    lid = _pick_lesson(cat, "st_pod_l", include_all=False)
    les = study.lesson_map(cat).get(lid)
    if not les:
        return
    parts = [p for p in (les.get("script_parts") or []) if p]
    if not parts:
        st.info(T("No spoken script for this lesson yet.", "Aún no hay guion hablado para esta clase."))
        return
    src = les.get("script_src") or ""
    if src.startswith("generated"):
        st.caption(T("A read-aloud script built from the memorization notes of this lesson. The phone's own voice reads it (no extra service).",
                     "Un guion para leer en voz alta, armado con las claves de esta clase. La voz del teléfono lo lee (sin un servicio extra)."))
    else:
        st.caption(T("The spoken script written for this lesson. The phone's own voice can read it (no extra service).",
                     "El guion hablado escrito para esta clase. La voz del teléfono puede leerlo (sin un servicio extra)."))
    _TTS(key="bz_study_tts", data={
        "parts": parts,
        "lang": "es-US",
        "play": T("Listen", "Escuchar"),
        "stop": T("Stop", "Parar"),
    })
    for i, part in enumerate(parts, 1):
        with st.expander(T(f"Part {i}", f"Parte {i}"), expanded=(i == 1 and len(parts) < 4)):
            st.markdown(part.replace("$", "\\$"))
    if st.button(T("Count this as today's study", "Contar esto como estudio de hoy"), key="stb_pod_act"):
        study.note_activity(_prog)
        on_change()
        st.success(T("Saved.", "Guardado."))


def render(*, progress, on_change, passcode):
    _css()
    cat = study.load(passcode)
    if not cat:
        st.error(T("Study notes could not be opened. Enter the passcode again.",
                   "No se pudieron abrir las notas de estudio. Entre de nuevo con el código."))
        return
    prog = progress
    base = study.empty_progress()
    for k, v in base.items():
        prog.setdefault(k, v)
    if study.ensure_seeded(prog, cat):
        on_change()

    cnt = study.counts(cat)
    hwrite(f"<div class='bz-hello'>{esc(T('Study for the NJ exam', 'Estudiar para el examen de NJ'))}</div>")
    hwrite("<p class='bz-st-meta'>" + esc(T(
        f"{cnt['lessons']} lessons · {cnt['terms']} terms · {cnt['questions']} practice items ({cnt['mc']} multiple choice, {cnt['tf']} true/false). "
        f"{cat.get('note_en') or ''}",
        f"{cnt['lessons']} clases · {cnt['terms']} términos · {cnt['questions']} ítems de práctica ({cnt['mc']} de selección, {cnt['tf']} verdadero/falso). "
        f"{cat.get('note_es') or ''}"
    )) + "</p>")

    labels = {k: (es if _es() else en) for k, en, es in SECTIONS}
    keys = [k for k, _, _ in SECTIONS]
    if st.session_state.get("st_sec") not in keys:
        st.session_state.st_sec = "plan"
    sec = st.pills(T("Section", "Apartado"), keys, key="st_sec", format_func=lambda k: labels[k])
    sec = sec or "plan"
    if sec == "plan":
        _plan(cat, prog, on_change)
    elif sec == "manual":
        _manual(cat, prog, on_change)
    elif sec == "cards":
        _cards(cat, prog, on_change)
    elif sec == "quiz":
        _quiz(cat, prog, on_change)
    elif sec == "tf":
        _tf(cat, prog, on_change)
    elif sec == "exam":
        _exam(cat, prog, on_change)
    elif sec == "tutor":
        _tutor(cat, prog, on_change)
    elif sec == "errors":
        _errors(cat, prog, on_change)
    else:
        _podcast(cat, prog, on_change)
