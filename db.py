from datetime import datetime, timedelta, timezone

import bcrypt
import streamlit as st
from supabase import Client, create_client

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15
GENERIC_LOGIN_ERROR = "Usuário ou senha inválidos."

# Used to run a bcrypt comparison even when the username doesn't exist, so a
# login attempt against an unknown username takes about as long as one against
# a real (wrong-password) account — otherwise the response-time difference
# would let an attacker enumerate valid usernames.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing-safety", bcrypt.gensalt()).decode()


@st.cache_resource
def get_client() -> Client:
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["service_key"])


def username_exists(username: str) -> bool:
    res = get_client().table("users").select("id").eq("username", username).execute()
    return len(res.data) > 0


def register_user(username: str, display_name: str, password: str) -> None:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    get_client().table("users").insert({
        "username": username,
        "display_name": display_name,
        "password_hash": password_hash,
    }).execute()


def _reset_failed_attempts(username: str) -> None:
    get_client().table("users").update({
        "failed_login_attempts": 0,
        "locked_until": None,
    }).eq("username", username).execute()


def _register_failed_attempt(username: str, current_count: int) -> None:
    new_count = current_count + 1
    update = {"failed_login_attempts": new_count}
    if new_count >= LOCKOUT_THRESHOLD:
        update["failed_login_attempts"] = 0
        update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
    get_client().table("users").update(update).eq("username", username).execute()


def verify_login(username: str, password: str) -> tuple[bool, str, dict | None]:
    """Checks credentials with brute-force lockout. Returns (success, message, user_row)."""
    username = username.strip().lower()

    res = (
        get_client()
        .table("users")
        .select("id, username, display_name, password_hash, failed_login_attempts, locked_until")
        .eq("username", username)
        .execute()
    )
    user = res.data[0] if res.data else None

    if user is None:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH.encode())
        return False, GENERIC_LOGIN_ERROR, None

    locked_until = user.get("locked_until")
    if locked_until:
        locked_dt = datetime.fromisoformat(locked_until.replace("Z", "+00:00"))
        if locked_dt > datetime.now(timezone.utc):
            remaining_min = max(1, int((locked_dt - datetime.now(timezone.utc)).total_seconds() // 60) + 1)
            return False, f"Conta temporariamente bloqueada por excesso de tentativas. Tente novamente em {remaining_min} min.", None

    if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        _reset_failed_attempts(username)
        return True, "ok", user

    _register_failed_attempt(username, user.get("failed_login_attempts", 0))
    return False, GENERIC_LOGIN_ERROR, None


def save_attempt(
    user_id: str,
    username: str,
    mode: str,
    language_version: str,
    topic_filter: str | None,
    total_questions: int,
    correct_count: int,
    score_pct: float,
    topic_scores: dict,
    answers: dict,
) -> None:
    get_client().table("attempts").insert({
        "user_id": user_id,
        "username": username,
        "mode": mode,
        "language_version": language_version,
        "topic_filter": topic_filter,
        "total_questions": total_questions,
        "correct_count": correct_count,
        "score_pct": score_pct,
        "topic_scores": topic_scores,
        "answers": answers,
    }).execute()


def is_admin(username: str) -> bool:
    admin_username = st.secrets.get("admin", {}).get("username", "")
    return bool(admin_username) and username == admin_username


@st.cache_data(ttl=30)
def get_questions_by_version(version: str) -> list[dict]:
    res = (
        get_client()
        .table("questions")
        .select("enunciado, alternativas, resposta_correta, explicacao, tema, referencia")
        .eq("version", version)
        .execute()
    )
    return res.data


def insert_questions(version: str, questions: list[dict], added_by: str) -> int:
    rows = [
        {
            "version": version,
            "enunciado": q["enunciado"],
            "alternativas": q["alternativas"],
            "resposta_correta": q["resposta_correta"],
            "explicacao": q.get("explicacao"),
            "tema": q.get("tema", "General"),
            "referencia": q.get("referencia"),
            "added_by": added_by,
        }
        for q in questions
    ]
    if rows:
        get_client().table("questions").insert(rows).execute()
    get_questions_by_version.clear()
    return len(rows)


def get_user_attempts(username: str) -> list[dict]:
    res = (
        get_client()
        .table("attempts")
        .select("*")
        .eq("username", username)
        .order("created_at")
        .execute()
    )
    return res.data
