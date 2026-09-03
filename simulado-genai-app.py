import streamlit as st
import json
import random
import re
import time
import pandas as pd
from streamlit_autorefresh import st_autorefresh

import db

LETTER_PREFIX_RE = re.compile(r'^[A-Za-z]\)\s*')
CITATION_MARKER_RE = re.compile(r'\s*\[\d+(?:,\s*\d+)*\]')
QUESTION_VERSION = "English Version"
SESSION_TIMEOUT_SECONDS = 10 * 60  # 10 minutes of inactivity (paused while an exam is in progress)
MINUTES_PER_QUESTION = 2

# Set Page Config — sidebar starts collapsed once an exam is in progress
st.set_page_config(
    page_title="Google Cloud Gen AI Leader - Practice Exam Simulator",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="collapsed" if st.session_state.get("exam_started") else "expanded",
)

GOOGLE_COLORS = ["#4285F4", "#EA4335", "#FBBC04", "#34A853"]


def topic_color(topic: str) -> str:
    return GOOGLE_COLORS[sum(ord(c) for c in topic) % len(GOOGLE_COLORS)]


SECTION_RE = re.compile(r'^(?:Section|Se[cç][ãa]o)\s*(\d+)', re.IGNORECASE)

# Official exam guide weighting (Generative AI Leader certification).
SECTION_WEIGHTS = {
    "Section 1": 0.30,
    "Section 2": 0.35,
    "Section 3": 0.20,
    "Section 4": 0.15,
}

SECTION_TITLES = {
    "Section 1": "Section 1: Fundamentals of gen AI",
    "Section 2": "Section 2: Google Cloud's gen AI offerings",
    "Section 3": "Section 3: Techniques to improve gen AI model output",
    "Section 4": "Section 4: Business strategies for a successful gen AI solution",
}


def topic_section_label(tema: str) -> str:
    """Rolls a granular tema ("Section 2.3: ...") up to its top-level exam
    section ("Section 2"). Falls back to the raw tema if it doesn't match
    the "Section N[.M]" pattern."""
    match = SECTION_RE.match(tema or "")
    return f"Section {match.group(1)}" if match else (tema or "General")


def select_stratified_by_section(pool: list, n: int) -> list:
    """Samples n questions from pool while keeping each official exam
    section's share close to its real weight (30/35/20/15%). Falls back to
    plain random sampling if the pool doesn't have recognizable sections."""
    by_section = {}
    for q in pool:
        by_section.setdefault(topic_section_label(q.get("tema", "")), []).append(q)

    recognized = {s: qs for s, qs in by_section.items() if s in SECTION_WEIGHTS}
    other = [q for s, qs in by_section.items() if s not in SECTION_WEIGHTS for q in qs]

    if not recognized:
        sample = list(pool)
        random.shuffle(sample)
        return sample[:n]

    targets = {s: n * w for s, w in SECTION_WEIGHTS.items() if s in recognized}
    quota = {s: int(t) for s, t in targets.items()}
    remainder = n - sum(quota.values())
    by_fraction = sorted(targets.items(), key=lambda kv: kv[1] - quota[kv[0]], reverse=True)
    for s, _ in by_fraction[:remainder]:
        quota[s] += 1

    selected = []
    leftover_pool = []
    for s, target in quota.items():
        group = list(recognized.get(s, []))
        random.shuffle(group)
        take = min(target, len(group))
        selected.extend(group[:take])
        leftover_pool.extend(group[take:])

    shortfall = n - len(selected)
    if shortfall > 0:
        fill_pool = leftover_pool + other
        random.shuffle(fill_pool)
        selected.extend(fill_pool[:shortfall])

    random.shuffle(selected)
    return selected[:n]


def draw_varied_exam(pool: list, num_questions: int, stratify: bool = False) -> list:
    """Selects num_questions from pool — proportionally by official exam
    section when stratify=True — then orders them so the same top-level
    section (1-4) never appears twice in a row (when the mix allows it),
    with fully shuffled order within each section run."""
    if stratify:
        sample = select_stratified_by_section(pool, num_questions)
    else:
        sample = list(pool)
        random.shuffle(sample)
        sample = sample[:num_questions]

    groups = {}
    for q in sample:
        groups.setdefault(topic_section_label(q.get("tema", "General")), []).append(q)
    for group in groups.values():
        random.shuffle(group)

    ordered = []
    last_section = None
    while any(groups.values()):
        candidates = sorted(
            (s for s, g in groups.items() if g),
            key=lambda s: len(groups[s]),
            reverse=True,
        )
        pick_section = next((s for s in candidates if s != last_section), candidates[0])
        ordered.append(groups[pick_section].pop())
        last_section = pick_section

    return ordered


def parse_correct_indices(resposta_correta: str) -> set[int]:
    """Parses "A", "A, C", "A,B,C" etc. into a set of 0-based option indices."""
    letters = [part.strip().upper() for part in (resposta_correta or "").split(",")]
    return {ord(letter) - 65 for letter in letters if len(letter) == 1 and letter.isalpha()}


def build_brand_css() -> str:
    """Brand styling only. Deliberately never sets page/widget background or text
    colors — Streamlit's native theme (Light/Dark/Auto, user-selectable from the
    app's "⋮" menu) already handles that consistently across every built-in
    widget, and fighting it with hardcoded colors is what caused mismatched,
    low-contrast controls before.

    An earlier version tried to read Streamlit's theme via CSS custom properties
    (--primary-color, --background-color, --secondary-background-color), but
    those aren't actually exposed as global CSS variables in this Streamlit
    version — every var() silently fell back to its light-mode default, which is
    why cards stayed light even in dark mode. Every custom surface below instead
    uses translucent (rgba) fills with NO explicit text color, so it always
    blends with whatever the real page background is and inherits Streamlit's
    own (already correct) text color — no theme detection needed at all.
    """
    return """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Roboto', 'Segoe UI', sans-serif;
        }

        [data-testid="stAppViewContainer"] .main .block-container,
        [data-testid="stMainBlockContainer"] {
            padding-top: 1.5rem !important;
        }

        .main-header {
            font-size: 34px;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .main-header .accent-blue { color: #4285F4; }
        .main-header .accent-red { color: #EA4335; }
        .main-header .accent-yellow { color: #FBBC04; }
        .main-header .accent-green { color: #34A853; }

        .brand-bar {
            height: 5px;
            width: 130px;
            border-radius: 4px;
            margin-bottom: 10px;
            background: linear-gradient(90deg,
                #4285F4 0%, #4285F4 25%,
                #EA4335 25%, #EA4335 50%,
                #FBBC04 50%, #FBBC04 75%,
                #34A853 75%, #34A853 100%);
        }

        .sub-header {
            font-size: 16px;
            opacity: 0.75;
            margin-bottom: 26px;
        }

        span.question-progress {
            display: inline-block;
            background-color: rgba(66, 133, 244, 0.15);
            color: #4285F4;
            font-weight: 600;
            font-size: 12px;
            letter-spacing: 0.3px;
            padding: 3px 12px;
            border-radius: 999px;
            margin-bottom: 4px;
        }

        .exam-timer {
            display: inline-block;
            font-weight: 700;
            font-size: 20px;
            font-variant-numeric: tabular-nums;
            padding: 5px 16px;
            border-radius: 999px;
            margin-bottom: 0;
        }
        .exam-timer.timer-normal {
            background-color: rgba(66, 133, 244, 0.15);
            color: #4285F4;
        }
        .exam-timer.timer-danger {
            background-color: rgba(234, 67, 53, 0.18);
            color: #EA4335;
        }

        .question-box {
            background-color: rgba(128, 128, 128, 0.08);
            border: 1px solid rgba(128, 128, 128, 0.25);
            padding: 18px 22px;
            border-radius: 16px;
            margin-bottom: 14px;
            border-top: 4px solid var(--topic-color, #4285F4);
            text-align: left;
        }
        .question-box p {
            font-weight: 600;
            font-size: 18px;
            line-height: 1.5;
            text-align: left;
            margin: 0;
        }

        span.topic-tag {
            font-size: 12px;
            font-weight: 600;
            background-color: rgba(128, 128, 128, 0.18);
            color: var(--topic-color, #4285F4);
            padding: 5px 12px;
            border-radius: 999px;
            margin-bottom: 12px;
            display: inline-block;
        }

        .stButton > button {
            border-radius: 24px !important;
            font-weight: 500 !important;
            padding: 0.5rem 1.6rem !important;
            border: none !important;
            background-color: #4285F4 !important;
            color: #ffffff !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.3) !important;
            transition: box-shadow 0.15s ease, background-color 0.15s ease !important;
        }
        .stButton > button p {
            color: #ffffff !important;
        }
        .stButton > button:hover {
            background-color: #3367d6 !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.5) !important;
        }
        .stButton > button:disabled {
            opacity: 0.5 !important;
        }

        .stProgress > div > div > div {
            background-color: #4285F4 !important;
        }
        [data-testid="stProgress"] {
            margin-bottom: 6px;
        }

        .stTabs [data-baseweb="tab"] p {
            font-weight: 500;
            font-size: 15px;
        }
        .stTabs [aria-selected="true"] p {
            color: #4285F4 !important;
        }

        [data-testid="stMetric"] {
            background-color: rgba(128, 128, 128, 0.08);
            border: 1px solid rgba(128, 128, 128, 0.25);
            border-radius: 12px;
            padding: 16px 18px;
        }

        [data-testid="stRadio"] > div {
            gap: 16px;
        }
        [data-testid="stRadio"] label {
            padding: 6px 0;
        }

        /* Let long section titles wrap instead of being truncated */
        [data-testid="stSelectbox"],
        [data-testid="stSelectbox"] * {
            height: auto !important;
            min-height: 38px !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: unset !important;
            line-height: 1.3 !important;
        }
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            align-items: flex-start !important;
            padding-top: 8px !important;
            padding-bottom: 8px !important;
        }
        [data-baseweb="popover"] [role="option"],
        [data-baseweb="menu"] li {
            white-space: normal !important;
            height: auto !important;
            min-height: 38px !important;
            line-height: 1.3 !important;
        }

        /* Answer option buttons — full clickable rectangles, letter-first, left aligned */
        [class*="st-key-options_"] .stButton > button {
            width: 100%;
            border-radius: 10px !important;
            background-color: rgba(128, 128, 128, 0.06) !important;
            border: 1.5px solid rgba(128, 128, 128, 0.3) !important;
            color: inherit !important;
            text-align: left !important;
            justify-content: flex-start !important;
            padding: 14px 18px !important;
            font-weight: 500 !important;
            box-shadow: none !important;
            margin-bottom: 10px !important;
        }
        [class*="st-key-options_"] .stButton > button * {
            justify-content: flex-start !important;
            text-align: left !important;
        }
        [class*="st-key-options_"] .stButton > button p {
            color: inherit !important;
            text-align: left !important;
        }
        [class*="st-key-options_"] .stButton > button:hover {
            background-color: rgba(66, 133, 244, 0.12) !important;
            border-color: #4285F4 !important;
        }
        [class*="st-key-options_"] .stButton > button[kind="primary"] {
            background-color: rgba(66, 133, 244, 0.18) !important;
            border: 1.5px solid #4285F4 !important;
            color: #4285F4 !important;
        }
        [class*="st-key-options_"] .stButton > button[kind="primary"] p {
            color: #4285F4 !important;
        }
        [class*="st-key-options_"] .stButton > button p::first-letter {
            background-color: rgba(128, 128, 128, 0.2);
            font-weight: 700;
            padding: 7px 11px;
            border-radius: 6px;
            margin-right: 12px;
        }
        [class*="st-key-options_"] .stButton > button[kind="primary"] p::first-letter {
            background-color: #4285F4;
            color: #ffffff;
        }

        /* Review table — flat, full-width clickable rows with a dividing line, no pill buttons */
        /* Compact, centered review table — sized to content, no button chrome */
        /* Review table — clickable rows (3 button-cells forming one row), compact */
        [class*="st-key-reviewtable"] .stButton > button {
            width: 100%;
            border-radius: 0 !important;
            background-color: transparent !important;
            border: none !important;
            border-bottom: 1px solid rgba(128, 128, 128, 0.2) !important;
            color: inherit !important;
            font-weight: 500 !important;
            font-size: 14px !important;
            box-shadow: none !important;
            margin-bottom: 0 !important;
            padding: 8px 4px !important;
        }
        [class*="st-key-reviewtable"] .stButton > button p {
            color: inherit !important;
        }
        [class*="st-key-reviewtable"] .stButton > button:hover {
            background-color: rgba(66, 133, 244, 0.08) !important;
        }

        /* Discreet "Encerrar" button */
        [class*="st-key-endbtn"] .stButton > button {
            font-size: 12px !important;
            padding: 4px 10px !important;
            white-space: nowrap !important;
        }

        /* Static, colored option rows shown after "Verificar resposta" */
        .option-row {
            display: flex;
            align-items: center;
            gap: 14px;
            border-radius: 10px;
            padding: 14px 18px;
            margin-bottom: 10px;
            border: 1.5px solid rgba(128, 128, 128, 0.3);
        }
        .option-row .option-letter {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 6px;
            background-color: rgba(128, 128, 128, 0.18);
            font-weight: 700;
            flex-shrink: 0;
        }
        .option-row .option-text {
            flex: 1;
        }
        .option-row .option-icon {
            font-size: 16px;
        }
        .option-row.option-correct {
            background-color: rgba(52, 168, 83, 0.12);
            border-color: #34A853;
        }
        .option-row.option-correct .option-letter {
            background-color: #34A853;
            color: #ffffff;
        }
        .option-row.option-wrong {
            background-color: rgba(234, 67, 53, 0.12);
            border-color: #EA4335;
        }
        .option-row.option-wrong .option-letter {
            background-color: #EA4335;
            color: #ffffff;
        }

        .user-badge {
            display: inline-block;
            background-color: rgba(66, 133, 244, 0.15);
            color: #4285F4;
            font-weight: 600;
            font-size: 13px;
            padding: 6px 14px;
            border-radius: 999px;
            margin-top: 6px;
        }

        /* Bigger labels on sidebar selectors */
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
            font-size: 16px !important;
        }
    </style>
    """


def apply_theme() -> None:
    st.markdown(build_brand_css(), unsafe_allow_html=True)


def render_brand_header(subtitle: str | None = None):
    st.markdown(
        f"""
        <div class="main-header">
            <span class="accent-blue">G</span><span class="accent-red">o</span><span class="accent-yellow">o</span><span class="accent-blue">g</span><span class="accent-green">l</span><span class="accent-red">e</span>
            Gen AI Leader Exam Simulator ☁️
        </div>
        <div class="brand-bar"></div>
        {f'<div class="sub-header">{subtitle}</div>' if subtitle else ''}
        """,
        unsafe_allow_html=True,
    )


def render_user_badge(username: str):
    st.markdown(f'<div class="user-badge">👤 {username}</div>', unsafe_allow_html=True)


def reset_exam_progress():
    for key in (
        "current_exam", "answers", "current_q_idx", "checked", "submitted",
        "attempt_saved", "exam_started", "exam_start_time", "exam_duration_seconds",
        "exam_mode", "exam_topic", "review_flags", "reviewing", "nav_source", "cycle_list",
    ):
        st.session_state.pop(key, None)
    for key in [k for k in list(st.session_state.keys()) if k.startswith("reviewflag_")]:
        del st.session_state[key]


def section_sort_key(label: str):
    parts = label.split()
    if label.startswith("Section ") and parts[-1].isdigit():
        return (0, int(parts[-1]))
    return (1, label)


def render_timer() -> float:
    elapsed = time.time() - st.session_state["exam_start_time"]
    remaining = max(0.0, st.session_state["exam_duration_seconds"] - elapsed)
    minutes, seconds = divmod(int(remaining), 60)
    urgency_class = "timer-danger" if remaining <= 60 else "timer-normal"
    st.markdown(
        f'<div class="exam-timer {urgency_class}">⏱️ {minutes:02d}:{seconds:02d}</div>',
        unsafe_allow_html=True,
    )
    return remaining


def render_question_step(q, idx, total_qs, mode):
    q_color = topic_color(q.get("tema", "General"))
    st.markdown(f'<span class="question-progress">Questão {idx + 1} de {total_qs}</span>', unsafe_allow_html=True)
    st.progress(idx / total_qs)
    st.markdown(f"""
    <div class="question-box" style="--topic-color: {q_color};">
        <span class="topic-tag">{q.get('tema', 'General')}</span>
        <p>{q.get('enunciado')}</p>
    </div>
    """, unsafe_allow_html=True)

    options = q.get("alternativas", [])
    letters = [chr(65 + i) for i in range(len(options))]
    correct_indices = parse_correct_indices(q.get("resposta_correta", ""))
    is_multi = len(correct_indices) > 1

    current_answer = st.session_state["answers"].get(idx) or []
    selected_set = set(current_answer)
    selected_single = current_answer[0] if current_answer else None

    checked = mode == "Study Mode (Instant Feedback)" and st.session_state.get("checked")

    if checked:
        stored_set = selected_set
        for i, opt in enumerate(options):
            if i in correct_indices:
                css_class, icon = "option-correct", "✅"
            elif i in stored_set:
                css_class, icon = "option-wrong", "❌"
            else:
                css_class, icon = "option-neutral", ""
            st.markdown(
                f'<div class="option-row {css_class}">'
                f'<span class="option-letter">{letters[i]}</span>'
                f'<span class="option-text">{opt}</span>'
                f'<span class="option-icon">{icon}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        if is_multi:
            st.caption("⚠️ Esta questão tem mais de uma alternativa correta — marque todas que se aplicam.")
        with st.container(key=f"options_{idx}"):
            for i, opt in enumerate(options):
                selected = (i in selected_set) if is_multi else (selected_single == i)
                if st.button(
                    f"{letters[i]}   {opt}",
                    key=f"optbtn_{idx}_{i}",
                    use_container_width=True,
                    type="primary" if selected else "secondary",
                ):
                    if is_multi:
                        new_set = set(selected_set)
                        if selected:
                            new_set.discard(i)
                        else:
                            new_set.add(i)
                        st.session_state["answers"][idx] = sorted(new_set)
                    else:
                        st.session_state["answers"][idx] = [i]
                    st.rerun()

    selected_indices = st.session_state["answers"].get(idx) or []
    has_selection = len(selected_indices) > 0

    is_last = idx == total_qs - 1

    if mode == "Study Mode (Instant Feedback)":
        next_label = "🏁 Finalizar prova" if is_last else "Próxima questão →"
        if not st.session_state.get("checked"):
            if st.button("Verificar resposta", disabled=not has_selection):
                st.session_state["checked"] = True
                st.rerun()
        else:
            stored_indices = selected_indices
            correct_text = ", ".join(options[i] for i in sorted(correct_indices)) if correct_indices else "—"
            if set(stored_indices) == correct_indices:
                st.success(f"✅ **Correto!** (Resposta: **{correct_text}**)")
            else:
                stored_text = ", ".join(options[i] for i in sorted(stored_indices)) if stored_indices else "—"
                st.error(f"❌ **Incorreto.** (Você marcou: **{stored_text}** | Correta: **{correct_text}**)")
            st.markdown(f"**Explicação:** {q.get('explicacao')}")
            ref = q.get("referencia", {})
            if ref and ref.get("url"):
                st.markdown(f"📖 **Referência:** [{ref.get('titulo')}]({ref.get('url')})")

            if st.button(next_label):
                st.session_state["current_q_idx"] += 1
                st.session_state["checked"] = False
                if st.session_state["current_q_idx"] >= total_qs:
                    st.session_state["submitted"] = True
                st.rerun()
    else:
        # Exam Mode: free forward/back navigation, no answer required to move on.
        nav_source = st.session_state.get("nav_source", "linear")
        review_flags = set(st.session_state.get("review_flags", set()))

        marked = st.checkbox(
            "🔖 Marcar esta questão para revisão",
            value=idx in review_flags,
            key=f"reviewflag_{idx}",
        )
        if marked:
            review_flags.add(idx)
        else:
            review_flags.discard(idx)
        st.session_state["review_flags"] = review_flags

        if nav_source == "jump":
            if st.button("↩ Voltar para a tabela de questões", use_container_width=True):
                st.session_state["reviewing"] = True
                st.rerun()
        elif nav_source == "cycle":
            cycle_list = st.session_state.get("cycle_list", [])
            pos = cycle_list.index(idx) if idx in cycle_list else None
            col_prev, col_next = st.columns(2)
            with col_prev:
                if pos is not None and pos > 0:
                    if st.button("◀ Anterior", use_container_width=True):
                        st.session_state["current_q_idx"] = cycle_list[pos - 1]
                        st.rerun()
                else:
                    st.button("◀ Anterior", disabled=True, use_container_width=True)
            with col_next:
                is_last_in_cycle = pos is None or pos >= len(cycle_list) - 1
                next_cycle_label = "✅ Concluir" if is_last_in_cycle else "Próxima →"
                if st.button(next_cycle_label, use_container_width=True):
                    review_flags.discard(idx)
                    st.session_state["review_flags"] = review_flags
                    st.session_state.pop(f"reviewflag_{idx}", None)
                    if is_last_in_cycle:
                        st.session_state["reviewing"] = True
                    else:
                        st.session_state["current_q_idx"] = cycle_list[pos + 1]
                    st.rerun()
        else:
            next_label = "🏁 Ver revisão e finalizar" if is_last else "Avançar →"
            col_prev, col_next = st.columns(2)
            with col_prev:
                if idx > 0:
                    if st.button("◀ Voltar", use_container_width=True):
                        st.session_state["current_q_idx"] = idx - 1
                        st.rerun()
                else:
                    st.button("◀ Voltar", disabled=True, use_container_width=True)
            with col_next:
                if st.button(next_label, use_container_width=True):
                    if is_last:
                        st.session_state["reviewing"] = True
                    else:
                        st.session_state["current_q_idx"] = idx + 1
                    st.rerun()


def render_review_table(total_qs):
    st.subheader("🗂️ Revisão das Questões")
    st.caption("Clique em qualquer ponto de uma linha para ir até aquela questão.")

    review_flags = st.session_state.get("review_flags", set())
    answers = st.session_state.get("answers", {})

    col_mid, _ = st.columns([2, 1])
    with col_mid:
        with st.container(key="reviewtable"):
            header = st.columns([1, 1.6, 1.6])
            header[0].markdown("<div style='text-align:center;'><b>Questão</b></div>", unsafe_allow_html=True)
            header[1].markdown("<div style='text-align:center;'><b>Preenchida</b></div>", unsafe_allow_html=True)
            header[2].markdown("<div style='text-align:center;'><b>Revisão</b></div>", unsafe_allow_html=True)

            for i in range(total_qs):
                answered = bool(answers.get(i))
                marked = i in review_flags
                status = "✅ Sim" if answered else "⬜ Não"
                review_status = "🔖 Sim" if marked else "—"

                row = st.columns([1, 1.6, 1.6])
                clicked = False
                with row[0]:
                    if st.button(f"{i + 1}", key=f"jumpnum_{i}", use_container_width=True):
                        clicked = True
                with row[1]:
                    if st.button(status, key=f"jumpstatus_{i}", use_container_width=True):
                        clicked = True
                with row[2]:
                    if st.button(review_status, key=f"jumpreview_{i}", use_container_width=True):
                        clicked = True
                if clicked:
                    st.session_state["current_q_idx"] = i
                    st.session_state["nav_source"] = "jump"
                    st.session_state["reviewing"] = False
                    st.rerun()

    st.divider()
    marked_count = len(review_flags)
    unanswered_indices = [i for i in range(total_qs) if not answers.get(i)]
    unanswered_count = len(unanswered_indices)
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            f"📝 Revisar questões marcadas ({marked_count})",
            disabled=marked_count == 0,
            use_container_width=True,
        ):
            st.session_state["cycle_list"] = sorted(review_flags)
            st.session_state["current_q_idx"] = st.session_state["cycle_list"][0]
            st.session_state["nav_source"] = "cycle"
            st.session_state["reviewing"] = False
            st.rerun()
    with col_b:
        if st.button(
            f"📄 Fazer questões não respondidas ({unanswered_count})",
            disabled=unanswered_count == 0,
            use_container_width=True,
        ):
            st.session_state["cycle_list"] = unanswered_indices
            st.session_state["current_q_idx"] = st.session_state["cycle_list"][0]
            st.session_state["nav_source"] = "cycle"
            st.session_state["reviewing"] = False
            st.rerun()

    if st.button("🏁 Finalizar prova", use_container_width=True, type="primary"):
        st.session_state["submitted"] = True
        st.rerun()


def render_results_dashboard(exam_list, total_qs, mode, username, user_id, selected_version, selected_topic):
    st.subheader("🏁 Resultado")
    correct_count = 0
    topic_scores = {}  # granular tema — kept for per-domain history in "Meu Progresso"
    section_scores = {}  # top-level Section 1-4 — used for the breakdown shown here

    for idx, q in enumerate(exam_list):
        tema = q.get("tema", "General")
        if tema not in topic_scores:
            topic_scores[tema] = {"correct": 0, "total": 0}
        topic_scores[tema]["total"] += 1

        section = topic_section_label(tema)
        if section not in section_scores:
            section_scores[section] = {"correct": 0, "total": 0}
        section_scores[section]["total"] += 1

        user_indices = set(st.session_state["answers"].get(idx) or [])
        correct_indices = parse_correct_indices(q.get("resposta_correta", ""))

        if user_indices == correct_indices:
            correct_count += 1
            topic_scores[tema]["correct"] += 1
            section_scores[section]["correct"] += 1

    final_pct = (correct_count / total_qs) * 100

    if not st.session_state.get("attempt_saved"):
        db.save_attempt(
            user_id=user_id,
            username=username,
            mode=mode,
            language_version=selected_version,
            topic_filter=selected_topic,
            total_questions=total_qs,
            correct_count=correct_count,
            score_pct=final_pct,
            topic_scores=topic_scores,
            answers=st.session_state["answers"],
        )
        st.session_state["attempt_saved"] = True

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Nota Final", f"{correct_count} / {total_qs}", f"{final_pct:.1f}%")
    with col2:
        if final_pct >= 70:  # Target pass score for general Google examinations is roughly around 70-80%
            st.balloons()
            st.success("🎉 **Parabéns! Você passou!**")
        else:
            st.warning("✊ **Continue estudando! Tente atingir 70% ou mais.**")
    with col3:
        st.write("")

    st.subheader("📈 Resultado por Seção")
    for section, scores in sorted(section_scores.items(), key=lambda item: section_sort_key(item[0])):
        t_correct = scores["correct"]
        t_total = scores["total"]
        t_pct = (t_correct / t_total) * 100
        st.write(f"**{SECTION_TITLES.get(section, section)}**")
        st.progress(t_pct / 100)
        st.caption(f"{t_correct} de {t_total} corretas ({t_pct:.1f}%)")

    st.divider()
    if st.button("🔄 Fazer novo simulado"):
        reset_exam_progress()
        st.rerun()


def render_exam_tab(username, user_id):
    exam_started = st.session_state.get("exam_started", False)

    if exam_started:
        exam_list = st.session_state["current_exam"]
        total_qs = len(exam_list)
        active_mode = st.session_state.get("exam_mode")
        active_topic = st.session_state.get("exam_topic")

        if st.session_state.get("submitted"):
            render_results_dashboard(exam_list, total_qs, active_mode, username, user_id, QUESTION_VERSION, active_topic)
        else:
            col_timer, col_end = st.columns([5, 1.3])
            with col_timer:
                remaining = render_timer()
            with col_end:
                with st.container(key="endbtn"):
                    if st.button("⏹️ Encerrar", use_container_width=True):
                        st.session_state["submitted"] = True
                        st.rerun()
            if remaining <= 0:
                st.session_state["submitted"] = True
                st.rerun()
            else:
                st_autorefresh(interval=1000, key="exam_timer_refresh")
                if active_mode != "Study Mode (Instant Feedback)" and st.session_state.get("reviewing"):
                    render_review_table(total_qs)
                else:
                    idx = st.session_state["current_q_idx"]
                    render_question_step(exam_list[idx], idx, total_qs, active_mode)
        return

    # Sidebar Options
    st.sidebar.header("⚙️ Configurações do Simulado")

    raw_questions = db.get_questions_by_version(QUESTION_VERSION)
    if not raw_questions:
        st.warning("Nenhuma questão encontrada no banco de dados.")
        return

    # Topic filter operates at the top-level exam section (Section 1-4),
    # not the granular sub-topic each question is individually tagged with.
    all_sections = sorted(
        set(topic_section_label(q.get("tema", "General")) for q in raw_questions),
        key=section_sort_key,
    )

    EXAM_TYPE_FULL = "🎓 Prova Completa (50 questões)"
    EXAM_TYPE_SHORT = "📘 Prova Reduzida (20 questões)"
    EXAM_TYPE_QUICK = "⚡ Teste Rápido (10 questões)"
    EXAM_TYPE_SECTION = "📂 Por Seção (10 questões)"
    PRESET_COUNTS = {EXAM_TYPE_FULL: 50, EXAM_TYPE_SHORT: 20, EXAM_TYPE_QUICK: 10}

    exam_type = st.sidebar.selectbox(
        "**Tipo de Simulado**",
        [EXAM_TYPE_FULL, EXAM_TYPE_SHORT, EXAM_TYPE_QUICK, EXAM_TYPE_SECTION],
        disabled=exam_started,
    )

    if exam_type == EXAM_TYPE_FULL:
        mode = "Exam Mode (Final Score Only)"
        st.sidebar.caption("🎓 Modo Prova fixo para a Prova Completa.")
    else:
        mode = st.sidebar.selectbox(
            "**Modo de Exame**",
            ["Study Mode (Instant Feedback)", "Exam Mode (Final Score Only)"],
            disabled=exam_started,
        )

    if exam_type in PRESET_COUNTS:
        selected_topic = None
        filtered_questions = raw_questions
        num_questions = min(PRESET_COUNTS[exam_type], len(raw_questions))

        distribution = st.sidebar.selectbox(
            "**Distribuição dos temas**",
            ["Proporcional à prova oficial", "Aleatória"],
            disabled=exam_started,
            help="Proporcional respeita os pesos oficiais de cada seção do exame (Seção 1: 30%, 2: 35%, 3: 20%, 4: 15%). Aleatória sorteia sem considerar a seção.",
        )
        stratify_by_section = distribution == "Proporcional à prova oficial"

        exam_duration_seconds = 120 * 60 if exam_type == EXAM_TYPE_FULL else num_questions * MINUTES_PER_QUESTION * 60

    else:  # EXAM_TYPE_SECTION
        selected_topic = st.sidebar.selectbox(
            "**Escolha a seção**",
            all_sections,
            format_func=lambda s: SECTION_TITLES.get(s, s),
            disabled=exam_started,
        )
        filtered_questions = [q for q in raw_questions if topic_section_label(q.get("tema", "General")) == selected_topic]
        if not filtered_questions:
            st.warning("No questions available for this selection.")
            return
        num_questions = min(10, len(filtered_questions))
        stratify_by_section = False
        exam_duration_seconds = num_questions * MINUTES_PER_QUESTION * 60

    st.sidebar.write("")
    st.sidebar.write("")
    _, col_start, _ = st.sidebar.columns([1, 2, 1])
    start_clicked = col_start.button("🚀 Iniciar Simulado", use_container_width=True)
    if start_clicked:
        st.session_state["current_exam"] = draw_varied_exam(filtered_questions, num_questions, stratify=stratify_by_section)
        st.session_state["answers"] = {}
        st.session_state["current_q_idx"] = 0
        st.session_state["checked"] = False
        st.session_state["submitted"] = False
        st.session_state["attempt_saved"] = False
        st.session_state["exam_started"] = True
        st.session_state["exam_start_time"] = time.time()
        st.session_state["exam_duration_seconds"] = exam_duration_seconds
        st.session_state["exam_mode"] = mode
        st.session_state["exam_topic"] = selected_topic
        st.session_state["review_flags"] = set()
        st.session_state["reviewing"] = False
        st.session_state["nav_source"] = "linear"
        st.rerun()
    st.info("Configure o simulado na barra lateral e clique em **🚀 Iniciar Simulado** para começar.")


def render_progress_tab(username):
    attempts = db.get_user_attempts(username)
    if not attempts:
        st.info("Você ainda não completou nenhum simulado. Vá para a aba 'Fazer Simulado' para começar!")
        return

    df = pd.DataFrame(attempts)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df = df.sort_values("created_at")

    col1, col2, col3 = st.columns(3)
    col1.metric("Tentativas", len(df))
    col2.metric("Melhor nota", f"{df['score_pct'].max():.1f}%")
    col3.metric("Média geral", f"{df['score_pct'].mean():.1f}%")

    st.subheader("📈 Evolução da nota")
    st.line_chart(df.set_index("created_at")["score_pct"])

    st.subheader("🎯 Desempenho por Seção")
    domain_totals = {}
    for _, row in df.iterrows():
        for topic, scores in (row["topic_scores"] or {}).items():
            section = topic_section_label(topic)
            totals = domain_totals.setdefault(section, {"correct": 0, "total": 0})
            totals["correct"] += scores.get("correct", 0)
            totals["total"] += scores.get("total", 0)

    if domain_totals:
        sorted_domains = sorted(domain_totals.items(), key=lambda item: section_sort_key(item[0]))
        for section, scores in sorted_domains:
            t_correct = scores["correct"]
            t_total = scores["total"]
            t_pct = (t_correct / t_total * 100) if t_total else 0
            st.write(f"**{SECTION_TITLES.get(section, section)}**")
            st.progress(t_pct / 100)
            st.caption(f"{t_correct} de {t_total} corretas ({t_pct:.1f}%)")

    st.subheader("🗂️ Histórico completo")
    history = df[["created_at", "mode", "total_questions", "correct_count", "score_pct"]].sort_values(
        "created_at", ascending=False
    )
    st.dataframe(history, width='stretch', hide_index=True)


# App Main Function
def main():
    username = st.session_state["username"]
    user_id = st.session_state["user_id"]

    in_active_exam = st.session_state.get("exam_started", False) and not st.session_state.get("submitted", False)

    render_brand_header()

    tab_labels = ["📝 Fazer Simulado"]
    if not in_active_exam:
        tab_labels.append("📈 Meu Progresso")
    if db.is_admin(username):
        tab_labels.append("🛠️ Admin")

    tabs = st.tabs(tab_labels)
    with tabs[0]:
        render_exam_tab(username, user_id)

    next_idx = 1
    if not in_active_exam:
        with tabs[next_idx]:
            render_progress_tab(username)
        next_idx += 1
    if db.is_admin(username):
        with tabs[next_idx]:
            render_admin_tab(username)


def render_admin_tab(username):
    st.subheader("🛠️ Adicionar novas questões")
    st.caption(
        "Envie um arquivo JSON no mesmo formato do banco original: uma lista de objetos "
        "com os campos `enunciado`, `alternativas` (lista), `resposta_correta`, `explicacao`, "
        "`tema` e `referencia`."
    )

    existing_count = len(db.get_questions_by_version(QUESTION_VERSION))
    st.caption(f"Atualmente há {existing_count} questão(ões) no banco de questões.")

    uploaded_file = st.file_uploader("Arquivo JSON", type="json")
    if uploaded_file is None:
        return

    try:
        new_questions = json.load(uploaded_file)
    except json.JSONDecodeError as e:
        st.error(f"JSON inválido: {e}")
        return

    if not isinstance(new_questions, list):
        st.error("O arquivo deve conter uma lista de questões.")
        return

    required_fields = {"enunciado", "alternativas", "resposta_correta"}
    valid_questions = []
    errors = []
    for i, q in enumerate(new_questions):
        if not isinstance(q, dict):
            errors.append(f"Questão {i + 1}: não é um objeto JSON válido")
            continue
        missing = required_fields - q.keys()
        if missing:
            errors.append(f"Questão {i + 1}: campos ausentes {sorted(missing)}")
            continue
        if not isinstance(q["alternativas"], list) or len(q["alternativas"]) < 4:
            errors.append(f"Questão {i + 1}: 'alternativas' deve ter pelo menos 4 opções")
            continue
        q["alternativas"] = [
            CITATION_MARKER_RE.sub('', LETTER_PREFIX_RE.sub('', opt)).strip() for opt in q["alternativas"]
        ]
        for field in ("enunciado", "explicacao"):
            if q.get(field):
                q[field] = CITATION_MARKER_RE.sub('', q[field]).strip()
        correct_indices = parse_correct_indices(q["resposta_correta"])
        if not correct_indices or not all(0 <= i < len(q["alternativas"]) for i in correct_indices):
            errors.append(f"Questão {i + 1}: 'resposta_correta' ('{q['resposta_correta']}') não corresponde a nenhuma alternativa")
            continue
        valid_questions.append(q)

    st.info(f"{len(valid_questions)} questão(ões) válida(s) encontrada(s) de {len(new_questions)} no arquivo.")
    if errors:
        with st.expander(f"⚠️ {len(errors)} questão(ões) com problema (não serão importadas)"):
            for err in errors:
                st.write(f"- {err}")

    if not valid_questions:
        return

    st.write("Pré-visualização (primeiras 3):")
    for q in valid_questions[:3]:
        st.markdown(f"- **{q['enunciado']}** _(tema: {q.get('tema', 'General')})_")

    if st.button(f"✅ Confirmar importação de {len(valid_questions)} questão(ões)"):
        count = db.insert_questions(QUESTION_VERSION, valid_questions, username)
        st.success(f"{count} questão(ões) adicionada(s) com sucesso ao banco de questões!")


MIN_PASSWORD_LENGTH = 8


def render_register_form():
    st.subheader("Criar nova conta")
    with st.form("register_form", clear_on_submit=True):
        new_username = st.text_input("Usuário")
        new_display_name = st.text_input("Nome de exibição")
        new_password = st.text_input("Senha", type="password")
        new_password_repeat = st.text_input("Repita a senha", type="password")
        st.caption(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
        submitted = st.form_submit_button("Criar conta")

        if submitted:
            username_clean = new_username.strip().lower()
            if not username_clean or not new_password:
                st.error("Usuário e senha são obrigatórios.")
            elif len(new_password) < MIN_PASSWORD_LENGTH:
                st.error(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
            elif new_password != new_password_repeat:
                st.error("As senhas não coincidem.")
            elif db.username_exists(username_clean):
                st.error("Esse nome de usuário já existe.")
            else:
                db.register_user(username_clean, new_display_name.strip(), new_password)
                st.success("Conta criada! Vá para a aba 'Entrar' para fazer login.")


def render_login_form():
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

        if submitted:
            ok, message, user = db.verify_login(username, password)
            if ok:
                st.session_state["authentication_status"] = True
                st.session_state["username"] = user["username"]
                st.session_state["name"] = user.get("display_name") or user["username"]
                st.session_state["user_id"] = user["id"]
                st.session_state["last_activity_time"] = time.time()
                st.rerun()
            else:
                st.error(message)


def run():
    apply_theme()

    if st.session_state.get("authentication_status"):
        in_active_exam = st.session_state.get("exam_started", False) and not st.session_state.get("submitted", False)

        if in_active_exam:
            # The exam's own countdown governs this phase — keep pushing the
            # inactivity clock forward so it only starts once the exam ends.
            st.session_state["last_activity_time"] = time.time()
        else:
            last_activity = st.session_state.get("last_activity_time", time.time())
            if time.time() - last_activity > SESSION_TIMEOUT_SECONDS:
                for key in ("authentication_status", "username", "name", "user_id", "last_activity_time"):
                    st.session_state.pop(key, None)
                reset_exam_progress()
                st.session_state["session_expired_notice"] = True
                st.rerun()
            st.session_state["last_activity_time"] = time.time()

        with st.sidebar:
            col_badge, col_logout = st.columns([2, 1])
            with col_badge:
                render_user_badge(st.session_state["username"])
            with col_logout:
                if st.button("Sair"):
                    for key in ("authentication_status", "username", "name", "user_id", "last_activity_time"):
                        st.session_state.pop(key, None)
                    reset_exam_progress()
                    st.rerun()
        main()
        return

    if st.session_state.pop("session_expired_notice", False):
        st.toast("⏰ Sessão Expirada. Efetue novamente o login.", icon="⏰")
        st.warning("**Sessão Expirada. Efetue novamente o login.**")

    render_brand_header("Faça login ou crie uma conta para começar a estudar.")

    login_tab, register_tab = st.tabs(["Entrar", "Criar conta"])
    with login_tab:
        render_login_form()
    with register_tab:
        render_register_form()


if __name__ == "__main__":
    run()
