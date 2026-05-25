"""
Streamlit app — Delegable Tasks for VA.
Calls the FastAPI backend (backend.py) instead of Quire directly.

Required secrets in .streamlit/secrets.toml:
  BACKEND_URL      — FastAPI backend URL
  BACKEND_API_KEY  — x-api-key required by the backend
  QUIRE_PROJECT_ID — Quire project slug (visible in the URL)
  DELEGABLE_TAG    — default tag (fallback if VA has no specific tag)
  TASK_STATUS      — active | completed | all (default: active)

  Multi-VA users (add as many as needed):
  [va_users.maria]
  password = "pass_maria"
  tag = "delegabile"        # optional — overrides DELEGABLE_TAG for this VA

  [va_users.john]
  password = "pass_john"
  tag = "delegabile-john"   # VA sees only tasks with this tag
"""
import streamlit as st
import requests
from datetime import date, datetime

# ── i18n strings ───────────────────────────────────────────────────────────

STRINGS = {
    "en": {
        "title":           "Delegable Tasks",
        "gate_title":      "Restricted access",
        "gate_pwd":        "Password",
        "gate_btn":        "Enter",
        "gate_err":        "Wrong password.",
        "refresh":         "🔄 Refresh",
        "view_label":      "View",
        "view_grouped":    "By deadline",
        "view_flat":       "List",
        "translate_toggle":"🌐 Translate to English",
        "translating":     "Translating...",
        "loading":         "Loading tasks...",
        "no_tasks":        "No tasks found.",
        "complete_btn":    "Complete",
        "edit_btn":        "✏️",
        "save_btn":        "Save",
        "cancel_btn":      "Cancel",
        "complete_ok":     "Done!",
        "err_empty_name":  "Name cannot be empty.",
        "err_backend":     "Backend error",
        "err_conn":        "Cannot reach backend. Check BACKEND_URL in secrets.",
        "cache_info":      "tasks · 5 min cache",
        "status_lbl":      "Status",
        "prio_lbl":        "Priority",
        "due_lbl":         "Due",
        "group_overdue":   "Overdue",
        "group_today":     "Today",
        "group_week":      "This week",
        "group_later":     "Later",
        "group_nodate":    "No deadline",
        "lang_toggle":     "🇮🇹 Italiano",
        "desc_placeholder":"Add a description...",
        "desc_save":       "Save description",
        "desc_empty":      "No description",
        "login_title":     "Login",
        "login_user":      "Username",
        "login_pwd":       "Password",
        "login_btn":       "Login",
        "login_err":       "Wrong username or password.",
        "logout_btn":      "Logout",
        "logged_as":       "Logged in as",
    },
    "it": {
        "title":           "Task Delegabili",
        "gate_title":      "Accesso riservato",
        "gate_pwd":        "Password",
        "gate_btn":        "Entra",
        "gate_err":        "Password errata.",
        "refresh":         "🔄 Refresh",
        "view_label":      "Vista",
        "view_grouped":    "Per scadenza",
        "view_flat":       "Lista",
        "translate_toggle":"🌐 Traduci in inglese",
        "translating":     "Traduzione in corso...",
        "loading":         "Carico i task...",
        "no_tasks":        "Nessun task trovato.",
        "complete_btn":    "Completa",
        "edit_btn":        "✏️",
        "save_btn":        "Salva",
        "cancel_btn":      "Annulla",
        "complete_ok":     "Fatto!",
        "err_empty_name":  "Il nome non può essere vuoto.",
        "err_backend":     "Errore backend",
        "err_conn":        "Impossibile raggiungere il backend. Verifica BACKEND_URL nei secrets.",
        "cache_info":      "task · cache 5 min",
        "status_lbl":      "Stato",
        "prio_lbl":        "Priorità",
        "due_lbl":         "Scadenza",
        "group_overdue":   "Scaduti",
        "group_today":     "Oggi",
        "group_week":      "Questa settimana",
        "group_later":     "Più avanti",
        "group_nodate":    "Senza scadenza",
        "lang_toggle":     "🇬🇧 English",
        "desc_placeholder":"Aggiungi una descrizione...",
        "desc_save":       "Salva descrizione",
        "desc_empty":      "Nessuna descrizione",
        "login_title":     "Accesso",
        "login_user":      "Username",
        "login_pwd":       "Password",
        "login_btn":       "Entra",
        "login_err":       "Username o password errati.",
        "logout_btn":      "Logout",
        "logged_as":       "Connesso come",
    },
}

def s(key: str) -> str:
    lang = st.session_state.get("lang", "en")
    return STRINGS[lang].get(key, key)


# ── helpers ────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"x-api-key": st.secrets["BACKEND_API_KEY"]}


def _backend(path: str) -> str:
    return st.secrets["BACKEND_URL"].rstrip("/") + path


@st.cache_data(ttl=300)
def fetch_tasks(project_id: str, tag: str, status: str) -> list[dict]:
    r = requests.get(
        _backend("/quire/tasks/by-tag"),
        headers=_headers(),
        params={"tag": tag, "project_id": project_id, "status": status},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["tasks"]


@st.cache_data(ttl=600)
def fetch_translations(texts_key: tuple) -> list[str]:
    """texts_key is a tuple of task names (hashable for cache)."""
    r = requests.post(
        _backend("/quire/tasks/translate"),
        headers=_headers(),
        json={"texts": list(texts_key), "target_lang": "en"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["translations"]


def complete_task(task_oid: str) -> tuple[bool, str]:
    try:
        r = requests.post(_backend(f"/quire/tasks/{task_oid}/complete"),
                          headers=_headers(), timeout=10)
        return (True, "") if r.ok else (False, f"HTTP {r.status_code}: {r.text[:300]}")
    except requests.ConnectionError:
        return False, s("err_conn")
    except requests.Timeout:
        return False, "Timeout"


def rename_task(task_oid: str, new_name: str) -> tuple[bool, str]:
    try:
        r = requests.put(_backend(f"/quire/tasks/{task_oid}/rename"),
                         headers=_headers(), json={"name": new_name}, timeout=10)
        return (True, "") if r.ok else (False, f"HTTP {r.status_code}: {r.text[:300]}")
    except requests.ConnectionError:
        return False, s("err_conn")
    except requests.Timeout:
        return False, "Timeout"


def update_description(task_oid: str, description: str) -> tuple[bool, str]:
    try:
        r = requests.put(_backend(f"/quire/tasks/{task_oid}/description"),
                         headers=_headers(), json={"description": description}, timeout=10)
        return (True, "") if r.ok else (False, f"HTTP {r.status_code}: {r.text[:300]}")
    except requests.ConnectionError:
        return False, s("err_conn")
    except requests.Timeout:
        return False, "Timeout"


def _priority_label(raw) -> str:
    val = raw.get("value", 0) if isinstance(raw, dict) else raw
    return {-1: "Urgent", 0: "", 1: "High", 2: "Medium", 3: "Low"}.get(val, str(val or ""))


def _status_label(raw) -> str:
    if isinstance(raw, dict):
        return raw.get("name", "")
    return str(raw) if raw is not None else ""


def _due_date(t: dict) -> date | None:
    raw = (t.get("due") or "")[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date() if raw else None
    except ValueError:
        return None


def _group_key(t: dict) -> tuple[int, str]:
    d = _due_date(t)
    today = date.today()
    if d is None:      return (4, s("group_nodate"))
    if d < today:      return (0, s("group_overdue"))
    if d == today:     return (1, s("group_today"))
    if (d - today).days <= 7: return (2, s("group_week"))
    return (3, s("group_later"))


# ── multi-VA login ─────────────────────────────────────────────────────────

def _va_users() -> dict:
    """Returns {username: {password, tag}} from secrets."""
    try:
        return dict(st.secrets.get("va_users", {}))
    except Exception:
        return {}


def login_gate() -> bool:
    """Returns True if a VA is logged in. Stores va_name and va_tag in session."""
    if st.session_state.get("va_name"):
        return True

    users = _va_users()
    if not users:
        # No VA users configured — open access
        st.session_state["va_name"] = "guest"
        st.session_state["va_tag"]  = st.secrets.get("DELEGABLE_TAG", "delegabile")
        return True

    st.title(s("login_title"))
    username = st.text_input(s("login_user")).strip().lower()
    password = st.text_input(s("login_pwd"), type="password")

    if st.button(s("login_btn")):
        user_cfg = users.get(username)
        if user_cfg and password == user_cfg.get("password", ""):
            st.session_state["va_name"] = username
            st.session_state["va_tag"]  = (
                user_cfg.get("tag") or st.secrets.get("DELEGABLE_TAG", "delegabile")
            )
            st.rerun()
        else:
            st.error(s("login_err"))
    return False


# ── task card ──────────────────────────────────────────────────────────────

def _task_card(t: dict, translated_name: str | None = None) -> None:
    oid       = t.get("oid", "")
    orig_name = t.get("nameText") or t.get("name", "")
    due_obj   = _due_date(t)
    due_str   = due_obj.strftime("%d/%m/%Y") if due_obj else ""
    prio      = _priority_label(t.get("priority"))
    stat      = _status_label(t.get("status"))
    url       = t.get("url", "")
    editing   = st.session_state.get(f"edit_{oid}", False)

    with st.container(border=True):
        if editing:
            new_val = st.text_input("", value=orig_name, key=f"input_{oid}")
            col_save, col_cancel, _ = st.columns([1, 1, 6])
            with col_save:
                if st.button(s("save_btn"), key=f"save_{oid}"):
                    if not new_val.strip():
                        st.warning(s("err_empty_name"))
                    else:
                        ok, err = rename_task(oid, new_val.strip())
                        if ok:
                            st.session_state[f"edit_{oid}"] = False
                            fetch_tasks.clear()
                            st.rerun()
                        else:
                            st.error(err)
            with col_cancel:
                if st.button(s("cancel_btn"), key=f"cancel_{oid}"):
                    st.session_state[f"edit_{oid}"] = False
                    st.rerun()
        else:
            col_name, col_meta, col_edit, col_done = st.columns([4, 3, 1, 1])
            with col_name:
                display = translated_name if translated_name else orig_name
                st.markdown(f"**[{display}]({url})**" if url else f"**{display}**")
                if translated_name:
                    st.caption(f"_{orig_name}_")
            with col_meta:
                parts = []
                if stat:    parts.append(f"{s('status_lbl')}: {stat}")
                if prio:    parts.append(f"{s('prio_lbl')}: {prio}")
                if due_str: parts.append(f"{s('due_lbl')}: {due_str}")
                st.caption("  ·  ".join(parts))
            with col_edit:
                if st.button(s("edit_btn"), key=f"edit_{oid}_btn"):
                    st.session_state[f"edit_{oid}"] = True
                    st.rerun()
            with col_done:
                if st.button(s("complete_btn"), key=f"complete_{oid}"):
                    ok, err = complete_task(oid)
                    if ok:
                        st.success(s("complete_ok"))
                        fetch_tasks.clear()
                        st.rerun()
                    else:
                        st.error(err)

            # ── description section ──
            current_desc = t.get("descriptionText") or t.get("description") or ""
            desc_key = f"desc_{oid}"
            new_desc = st.text_area(
                "",
                value=st.session_state.get(desc_key, current_desc),
                placeholder=s("desc_placeholder"),
                key=f"textarea_{oid}",
                height=80,
                label_visibility="collapsed",
            )
            if new_desc != current_desc:
                if st.button(s("desc_save"), key=f"desc_save_{oid}"):
                    ok, err = update_description(oid, new_desc)
                    if ok:
                        st.session_state.pop(desc_key, None)
                        fetch_tasks.clear()
                        st.rerun()
                    else:
                        st.error(err)


# ── views ──────────────────────────────────────────────────────────────────

def render_flat(tasks: list[dict], trans_map: dict) -> None:
    if not tasks:
        st.info(s("no_tasks"))
        return
    for t in tasks:
        _task_card(t, trans_map.get(t.get("oid")))


def render_grouped(tasks: list[dict], trans_map: dict) -> None:
    if not tasks:
        st.info(s("no_tasks"))
        return
    groups: dict[str, list] = {}
    order:  dict[str, int]  = {}
    for t in tasks:
        n, label = _group_key(t)
        groups.setdefault(label, []).append(t)
        order[label] = n

    icons = {0: "🔴", 1: "🟠", 2: "🟡", 3: "🟢", 4: "⚪"}
    for label in sorted(groups, key=lambda l: order[l]):
        icon = icons.get(order[label], "•")
        with st.expander(f"{icon} **{label}** ({len(groups[label])})",
                         expanded=(order[label] <= 1)):
            for t in sorted(groups[label], key=lambda x: _due_date(x) or date.max):
                _task_card(t, trans_map.get(t.get("oid")))


# ── main ───────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Tasks", page_icon="📋", layout="wide")

    # language init (default English)
    if "lang" not in st.session_state:
        st.session_state["lang"] = "en"

    if not login_gate():
        return

    project_id = st.secrets["QUIRE_PROJECT_ID"]
    tag_name   = st.session_state.get("va_tag") or st.secrets.get("DELEGABLE_TAG", "delegabile")
    status     = st.secrets.get("TASK_STATUS", "active")
    va_name    = st.session_state.get("va_name", "")

    # ── top bar ──
    col_title, col_spacer, col_va, col_lang, col_logout = st.columns([5, 1, 2, 1, 1])
    with col_title:
        st.title(f"📋 {s('title')}  —  #{tag_name}")
    with col_va:
        st.caption(f"{s('logged_as')}: **{va_name}**")
    with col_lang:
        if st.button(s("lang_toggle")):
            st.session_state["lang"] = "it" if st.session_state["lang"] == "en" else "en"
            st.rerun()
    with col_logout:
        if st.button(s("logout_btn")):
            st.session_state.clear()
            st.rerun()

    col_refresh, col_view, col_translate, col_info = st.columns([1, 2, 2, 5])
    with col_refresh:
        if st.button(s("refresh")):
            fetch_tasks.clear()
            fetch_translations.clear()
            st.rerun()
    with col_view:
        view = st.radio(s("view_label"),
                        [s("view_grouped"), s("view_flat")],
                        horizontal=True, label_visibility="collapsed")
    with col_translate:
        translate_on = st.toggle(s("translate_toggle"), value=False)

    # ── fetch tasks ──
    with st.spinner(s("loading")):
        try:
            tasks = fetch_tasks(project_id, tag_name, status)
        except requests.HTTPError as e:
            st.error(f"{s('err_backend')}: {e.response.status_code} — {e.response.text[:200]}")
            return
        except requests.ConnectionError:
            st.error(s("err_conn"))
            return

    with col_info:
        st.caption(f"{len(tasks)} {s('cache_info')}")

    # ── translations ──
    trans_map: dict = {}
    if translate_on and tasks:
        names = tuple(t.get("nameText") or t.get("name", "") for t in tasks)
        with st.spinner(s("translating")):
            try:
                translations = fetch_translations(names)
                trans_map = {
                    t.get("oid"): tr
                    for t, tr in zip(tasks, translations)
                    if tr and tr != (t.get("nameText") or t.get("name", ""))
                }
            except Exception:
                st.warning("Translation failed — showing original names.")

    # ── render ──
    if view == s("view_grouped"):
        render_grouped(tasks, trans_map)
    else:
        render_flat(tasks, trans_map)


if __name__ == "__main__":
    main()
