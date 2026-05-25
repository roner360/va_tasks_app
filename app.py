"""
Streamlit app — Delegable Tasks for VA.
Calls the FastAPI backend (backend.py) instead of Quire directly.

Required secrets in .streamlit/secrets.toml:
  BACKEND_URL      — FastAPI backend URL
  BACKEND_API_KEY  — x-api-key required by the backend
  QUIRE_PROJECT_ID — Quire project slug (visible in the URL)
  DELEGABLE_TAG    — tag to show the VA (default: delegabile)
  TASK_STATUS      — active | completed | all (default: active)
  VA_PASSWORD      — VA gate password (empty = no gate)
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


# ── password gate ──────────────────────────────────────────────────────────

def password_gate() -> bool:
    va_password = st.secrets.get("VA_PASSWORD", "")
    if not va_password or st.session_state.get("auth_ok"):
        return True
    st.title(s("gate_title"))
    pwd = st.text_input(s("gate_pwd"), type="password")
    if st.button(s("gate_btn")):
        if pwd == va_password:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error(s("gate_err"))
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

    if not password_gate():
        return

    project_id = st.secrets["QUIRE_PROJECT_ID"]
    tag_name   = st.secrets.get("DELEGABLE_TAG", "delegabile")
    status     = st.secrets.get("TASK_STATUS", "active")

    # ── top bar ──
    col_title, col_spacer, col_lang = st.columns([6, 2, 1])
    with col_title:
        st.title(f"📋 {s('title')}  —  #{tag_name}")
    with col_lang:
        if st.button(s("lang_toggle")):
            st.session_state["lang"] = "it" if st.session_state["lang"] == "en" else "en"
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
