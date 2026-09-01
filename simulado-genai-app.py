import streamlit as st
import json
import os
import random
import re
import time
import pandas as pd
from streamlit_autorefresh import st_autorefresh

import db

LETTER_PREFIX_RE = re.compile(r'^[A-Za-z]\)\s*')
CITATION_MARKER_RE = re.compile(r'\s*\[\d+(?:,\s*\d+)*\]')

# Set Page Config
st.set_page_config(
    page_title="Google Cloud Gen AI Leader - Practice Exam Simulator",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

GOOGLE_COLORS = ["#4285F4", "#EA4335", "#FBBC04", "#34A853"]


def topic_color(topic: str) -> str:
    return GOOGLE_COLORS[sum(ord(c) for c in topic) % len(GOOGLE_COLORS)]


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
            margin-bottom: 18px;
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
            font-size: 13px;
            letter-spacing: 0.3px;
            padding: 6px 16px;
            border-radius: 999px;
            margin-bottom: 14px;
        }

        .exam-timer {
            display: inline-block;
            font-weight: 700;
            font-size: 20px;
            font-variant-numeric: tabular-nums;
            padding: 6px 18px;
            border-radius: 999px;
            margin-bottom: 14px;
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
            padding: 28px;
            border-radius: 16px;
            margin-bottom: 22px;
            border-top: 4px solid var(--topic-color, #4285F4);
        }
        .question-box p {
            font-weight: 600;
            font-size: 18px;
            line-height: 1.5;
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

        .user-badge {
            display: inline-block;
            background-color: rgba(66, 133, 244, 0.15);
            color: #4285F4;
            font-weight: 600;
            font-size: 13px;
            padding: 6px 14px;
            border-radius: 999px;
            margin-top: 8px;
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
    st.sidebar.markdown(f'<div class="user-badge">👤 Logado como: {username}</div>', unsafe_allow_html=True)


# Helper function to load JSON questions
@st.cache_data
def load_questions(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def reset_exam_progress():
    for key in (
        "current_exam", "answers", "current_q_idx", "checked", "submitted", "last_settings",
        "attempt_saved", "exam_started", "exam_start_time", "exam_duration_seconds",
    ):
        st.session_state.pop(key, None)


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
    correct_indices = parse_correct_indices(q.get("resposta_correta", ""))
    is_multi = len(correct_indices) > 1

    if is_multi:
        st.caption("⚠️ Esta questão tem mais de uma alternativa correta — marque todas que se aplicam.")
        selected_indices = st.multiselect(
            "Selecione todas as alternativas corretas:",
            options=range(len(options)),
            format_func=lambda i: options[i],
            key=f"q_{idx}",
        )
        has_selection = len(selected_indices) > 0
    else:
        selected_index = st.radio(
            "Selecione a alternativa correta:",
            range(len(options)),
            format_func=lambda i: options[i],
            key=f"q_{idx}",
            index=None,
        )
        selected_indices = [selected_index] if selected_index is not None else []
        has_selection = selected_index is not None

    is_last = idx == total_qs - 1
    next_label = "🏁 Finalizar prova" if is_last else "Próxima questão →"

    if mode == "Study Mode (Instant Feedback)":
        if not st.session_state.get("checked"):
            if st.button("Verificar resposta", disabled=not has_selection):
                st.session_state["answers"][idx] = selected_indices
                st.session_state["checked"] = True
                st.rerun()
        else:
            stored_indices = st.session_state["answers"].get(idx) or []
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
        if st.button(next_label, disabled=not has_selection):
            st.session_state["answers"][idx] = selected_indices
            st.session_state["current_q_idx"] += 1
            if st.session_state["current_q_idx"] >= total_qs:
                st.session_state["submitted"] = True
            st.rerun()


def render_results_dashboard(exam_list, total_qs, mode, username, user_id, selected_version, selected_topic):
    st.subheader("📊 Painel de Desempenho")
    correct_count = 0
    topic_scores = {}  # Track performance by exam section

    for idx, q in enumerate(exam_list):
        tema = q.get("tema", "General")
        if tema not in topic_scores:
            topic_scores[tema] = {"correct": 0, "total": 0}

        topic_scores[tema]["total"] += 1

        user_indices = set(st.session_state["answers"].get(idx) or [])
        correct_indices = parse_correct_indices(q.get("resposta_correta", ""))

        if user_indices == correct_indices:
            correct_count += 1
            topic_scores[tema]["correct"] += 1

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

    st.subheader("📈 Desempenho por Seção / Domínio")
    for topic, scores in topic_scores.items():
        t_correct = scores["correct"]
        t_total = scores["total"]
        t_pct = (t_correct / t_total) * 100
        st.write(f"**{topic}**")
        st.progress(t_pct / 100)
        st.caption(f"{t_correct} de {t_total} corretas ({t_pct:.1f}%)")

    st.divider()
    if st.button("🔄 Fazer novo simulado"):
        reset_exam_progress()
        st.rerun()


def render_exam_tab(username, user_id):
    # Sidebar Options
    st.sidebar.header("⚙️ Configurações do Simulado")

    # Check for available JSON files
    json_options = {}
    if os.path.exists("simulado-genai-127-english.json"):
        json_options["English Version"] = "simulado-genai-127-english.json"
    if os.path.exists("simulado-genai-127.json"):
        json_options["Bilingual (PT/EN) Version"] = "simulado-genai-127.json"

    if not json_options:
        st.error("❌ No question files found! Please make sure 'simulado-genai-127-english.json' or 'simulado-genai-127.json' are present in the app folder.")
        return

    selected_version = next(iter(json_options))
    questions_file = json_options[selected_version]

    raw_questions = load_questions(questions_file) + db.get_questions_by_version(selected_version)
    if not raw_questions:
        st.warning("No questions loaded. Please check the JSON format.")
        return

    # Extract Unique Topics for Filtering
    all_topics = sorted(list(set(q.get("tema", "General") for q in raw_questions)))

    exam_started = st.session_state.get("exam_started", False)

    st.sidebar.subheader("🎯 Filtros e Modo")
    mode = st.sidebar.radio(
        "Modo de Exame",
        ["Study Mode (Instant Feedback)", "Exam Mode (Final Score Only)"],
        disabled=exam_started,
    )

    filter_by_topic = st.sidebar.checkbox("Filtrar por tópico", disabled=exam_started)
    selected_topic = None
    if filter_by_topic:
        selected_topic = st.sidebar.selectbox("Escolha a seção / tópico", all_topics, disabled=exam_started)
        filtered_questions = [q for q in raw_questions if q.get("tema") == selected_topic]
    else:
        filtered_questions = raw_questions

    total_available = len(filtered_questions)
    max_questions = min(50, total_available)
    if total_available == 0:
        st.warning("No questions available for this selection.")
        return
    elif max_questions == 1:
        num_questions = 1
    else:
        min_q = min(5, max_questions - 1)
        num_questions = st.sidebar.slider(
            "Número de questões",
            min_value=min_q,
            max_value=max_questions,
            value=min(20, max_questions),
            disabled=exam_started,
        )

    minutes_per_question = st.sidebar.slider(
        "Minutos por questão",
        min_value=1,
        max_value=5,
        value=3,
        disabled=exam_started,
    )

    if not exam_started:
        exam_minutes = num_questions * minutes_per_question
        st.sidebar.caption(f"⏱️ Tempo do simulado: {exam_minutes} minutos ({num_questions} questões × {minutes_per_question} min)")
        if st.sidebar.button("🚀 Iniciar Simulado"):
            pool = list(filtered_questions)
            random.shuffle(pool)
            st.session_state["current_exam"] = pool[:num_questions]
            st.session_state["answers"] = {}
            st.session_state["current_q_idx"] = 0
            st.session_state["checked"] = False
            st.session_state["submitted"] = False
            st.session_state["attempt_saved"] = False
            st.session_state["exam_started"] = True
            st.session_state["exam_start_time"] = time.time()
            st.session_state["exam_duration_seconds"] = num_questions * minutes_per_question * 60
            st.rerun()
        st.info("Configure o simulado na barra lateral e clique em **🚀 Iniciar Simulado** para começar.")
        return

    exam_list = st.session_state["current_exam"]
    total_qs = len(exam_list)

    if st.session_state.get("submitted"):
        render_results_dashboard(exam_list, total_qs, mode, username, user_id, selected_version, selected_topic)
    else:
        col_timer, col_end = st.columns([4, 1])
        with col_timer:
            remaining = render_timer()
        with col_end:
            if st.button("⏹️ Encerrar"):
                st.session_state["submitted"] = True
                st.rerun()
        if remaining <= 0:
            st.session_state["submitted"] = True
            st.rerun()
        else:
            st_autorefresh(interval=1000, key="exam_timer_refresh")
            idx = st.session_state["current_q_idx"]
            render_question_step(exam_list[idx], idx, total_qs, mode)


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

    st.subheader("🎯 Desempenho médio por tópico")
    topic_rows = []
    for _, row in df.iterrows():
        for topic, scores in (row["topic_scores"] or {}).items():
            if scores.get("total"):
                topic_rows.append({
                    "topic": topic,
                    "pct": scores["correct"] / scores["total"] * 100,
                })
    if topic_rows:
        topic_df = pd.DataFrame(topic_rows)
        topic_avg = topic_df.groupby("topic")["pct"].mean().sort_values(ascending=False)
        st.bar_chart(topic_avg)

    st.subheader("🗂️ Histórico completo")
    history = df[["created_at", "mode", "total_questions", "correct_count", "score_pct"]].sort_values(
        "created_at", ascending=False
    )
    st.dataframe(history, width='stretch', hide_index=True)


# App Main Function
def main():
    render_brand_header()

    username = st.session_state["username"]
    user_id = st.session_state["user_id"]

    tab_labels = ["📝 Fazer Simulado", "📈 Meu Progresso"]
    if db.is_admin(username):
        tab_labels.append("🛠️ Admin")

    tabs = st.tabs(tab_labels)
    with tabs[0]:
        render_exam_tab(username, user_id)
    with tabs[1]:
        render_progress_tab(username)
    if db.is_admin(username):
        with tabs[2]:
            render_admin_tab(username)

    render_user_badge(username)


def render_admin_tab(username):
    st.subheader("🛠️ Adicionar novas questões")
    st.caption(
        "Envie um arquivo JSON no mesmo formato do banco original: uma lista de objetos "
        "com os campos `enunciado`, `alternativas` (lista), `resposta_correta`, `explicacao`, "
        "`tema` e `referencia`."
    )

    version_options = []
    if os.path.exists("simulado-genai-127-english.json"):
        version_options.append("English Version")
    if os.path.exists("simulado-genai-127.json"):
        version_options.append("Bilingual (PT/EN) Version")
    if not version_options:
        version_options = ["English Version"]

    target_version = st.selectbox("A quais questões estas novas perguntas devem se juntar?", version_options)

    existing_count = len(db.get_questions_by_version(target_version))
    st.caption(f"Atualmente há {existing_count} questão(ões) adicionada(s) manualmente para '{target_version}'.")

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
        if not isinstance(q["alternativas"], list) or not q["alternativas"]:
            errors.append(f"Questão {i + 1}: 'alternativas' deve ser uma lista não vazia")
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
        count = db.insert_questions(target_version, valid_questions, username)
        st.success(f"{count} questão(ões) adicionada(s) com sucesso a '{target_version}'!")


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
                st.rerun()
            else:
                st.error(message)


def run():
    apply_theme()

    if st.session_state.get("authentication_status"):
        with st.sidebar:
            if st.button("Sair"):
                for key in ("authentication_status", "username", "name", "user_id"):
                    st.session_state.pop(key, None)
                reset_exam_progress()
                st.rerun()
        main()
        return

    render_brand_header("Faça login ou crie uma conta para começar a estudar.")

    login_tab, register_tab = st.tabs(["Entrar", "Criar conta"])
    with login_tab:
        render_login_form()
    with register_tab:
        render_register_form()


if __name__ == "__main__":
    run()
