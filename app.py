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
        "audit_tab":       "Activity log",
        "audit_filter":    "Filter by VA",
        "audit_all":       "All",
        "audit_empty":     "No activity recorded yet.",
        "audit_action_complete":    "completed",
        "audit_action_rename":      "renamed",
        "audit_action_description": "updated description of",
        "audit_action_field":       "updated field on",
        "field_save":               "Save",
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
        "audit_tab":       "Registro attività",
        "audit_filter":    "Filtra per VA",
        "audit_all":       "Tutti",
        "audit_empty":     "Nessuna attività registrata.",
        "audit_action_complete":    "Ha completato",
        "audit_action_rename":      "Ha rinominato",
        "audit_action_description": "Ha modificato la descrizione di",
        "audit_action_field":       "Ha aggiornato un campo di",
        "field_save":               "Salva",
    },
}

AUDIT_ACTION_KEYS = {
    "complete":    ("audit_action_complete",    "✅"),
    "uncomplete":  ("audit_action_complete",    "↩️"),
    "rename":      ("audit_action_rename",      "✏️"),
    "description": ("audit_action_description", "📝"),
    "field":       ("audit_action_field",       "🔧"),
}


def _va_custom_fields() -> list[dict]:
    """Returns list of {key, label, type, options} from secrets."""
    try:
        raw = st.secrets.get("va_custom_fields", [])
        return [dict(f) for f in raw]
    except Exception:
        return []

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


def _audit_log(action: str, task: dict, old_value: str = None, new_value: str = None):
    """Fire-and-forget audit log call — never blocks the UI."""
    try:
        requests.post(
            _backend("/quire/audit/log"),
            headers=_headers(),
            json={
                "va_name":   st.session_state.get("va_name", "unknown"),
                "action":    action,
                "task_id":   task.get("id"),
                "task_name": task.get("nameText") or task.get("name", ""),
                "task_url":  task.get("url", ""),
                "old_value": old_value,
                "new_value": new_value,
            },
            timeout=5,
        )
    except Exception:
        pass  # audit failure must never break the main action


def complete_task(task: dict) -> tuple[bool, str]:
    oid = task.get("oid", "")
    try:
        r = requests.post(_backend(f"/quire/tasks/{oid}/complete"),
                          headers=_headers(), timeout=10)
        if r.ok:
            _audit_log("complete", task)
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.ConnectionError:
        return False, s("err_conn")
    except requests.Timeout:
        return False, "Timeout"


def uncomplete_task(task: dict) -> tuple[bool, str]:
    oid = task.get("oid", "")
    try:
        r = requests.post(_backend(f"/quire/tasks/{oid}/uncomplete"),
                          headers=_headers(), timeout=10)
        if r.ok:
            _audit_log("uncomplete", task)
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.ConnectionError:
        return False, s("err_conn")
    except requests.Timeout:
        return False, "Timeout"


def rename_task(task: dict, new_name: str) -> tuple[bool, str]:
    oid = task.get("oid", "")
    old_name = task.get("nameText") or task.get("name", "")
    try:
        r = requests.put(_backend(f"/quire/tasks/{oid}/rename"),
                         headers=_headers(), json={"name": new_name}, timeout=10)
        if r.ok:
            _audit_log("rename", task, old_value=old_name, new_value=new_name)
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.ConnectionError:
        return False, s("err_conn")
    except requests.Timeout:
        return False, "Timeout"


def update_field(task: dict, field_name: str, value: str | None) -> tuple[bool, str]:
    oid = task.get("oid", "")
    old_value = str(task.get(field_name) or "")
    try:
        r = requests.put(_backend(f"/quire/tasks/{oid}/field"),
                         headers=_headers(),
                         json={"field_name": field_name, "value": value},
                         timeout=10)
        if r.ok:
            _audit_log("field", task, old_value=f"{field_name}={old_value}", new_value=f"{field_name}={value}")
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.ConnectionError:
        return False, s("err_conn")
    except requests.Timeout:
        return False, "Timeout"


def update_description(task: dict, description: str) -> tuple[bool, str]:
    oid = task.get("oid", "")
    old_desc = task.get("descriptionText") or task.get("description") or ""
    try:
        r = requests.put(_backend(f"/quire/tasks/{oid}/description"),
                         headers=_headers(), json={"description": description}, timeout=10)
        if r.ok:
            _audit_log("description", task, old_value=old_desc, new_value=description)
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
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

def _is_completed(t: dict) -> bool:
    raw = t.get("status")
    val = raw.get("value", 0) if isinstance(raw, dict) else (raw or 0)
    return int(val) >= 100


def _task_card(t: dict, translated_name: str | None = None) -> None:
    oid       = t.get("oid", "")
    orig_name = t.get("nameText") or t.get("name", "")
    due_obj   = _due_date(t)
    due_str   = due_obj.strftime("%d/%m/%Y") if due_obj else ""
    prio      = _priority_label(t.get("priority"))
    stat      = _status_label(t.get("status"))
    url       = t.get("url", "")
    completed = _is_completed(t)
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
                        ok, err = rename_task(t, new_val.strip())
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
                if completed:
                    st.markdown(f"~~[{display}]({url})~~" if url else f"~~{display}~~")
                else:
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
                if completed:
                    if st.button("↩️", key=f"uncomplete_{oid}", help="Mark as active"):
                        ok, err = uncomplete_task(t)
                        if ok:
                            fetch_tasks.clear()
                            st.rerun()
                        else:
                            st.error(err)
                else:
                    if st.button(s("complete_btn"), key=f"complete_{oid}"):
                        ok, err = complete_task(t)
                        if ok:
                            st.success(s("complete_ok"))
                            fetch_tasks.clear()
                            st.rerun()
                        else:
                            st.error(err)

            # ── description section (collapsible) ──
            current_desc = t.get("descriptionText") or t.get("description") or ""
            desc_label = f"📝 {current_desc[:60]}{'…' if len(current_desc) > 60 else ''}" if current_desc else f"📝 {s('desc_placeholder')}"
            with st.expander(desc_label, expanded=False):
                new_desc = st.text_area(
                    "",
                    value=current_desc,
                    placeholder=s("desc_placeholder"),
                    key=f"textarea_{oid}",
                    height=100,
                    label_visibility="collapsed",
                )
                if new_desc != current_desc:
                    if st.button(s("desc_save"), key=f"desc_save_{oid}"):
                        ok, err = update_description(t, new_desc)
                        if ok:
                            fetch_tasks.clear()
                            st.rerun()
                        else:
                            st.error(err)

            # ── custom fields ──
            custom_fields = _va_custom_fields()
            if custom_fields:
                st.divider()
                for field_cfg in custom_fields:
                    fkey      = field_cfg.get("key", "")
                    flabel    = field_cfg.get("label", fkey)
                    ftype     = field_cfg.get("type", "text")
                    readwrite = field_cfg.get("readwrite", False)
                    options   = [o.strip() for o in str(field_cfg.get("options", "")).split(",") if o.strip()]
                    current   = str(t.get(fkey) or "")

                    is_url = ftype in ("hyperlink", "url") or "url" in fkey.lower() or "link" in fkey.lower()

                    if not readwrite:
                        # ── READ-ONLY display ──
                        if is_url and current:
                            st.markdown(f"**{flabel}:** [{current}]({current})")
                        elif ftype == "checkbox":
                            checked = "☑" if current.lower() == "true" else "☐"
                            st.caption(f"**{flabel}:** {checked}")
                        else:
                            st.caption(f"**{flabel}:** {current or '—'}")
                    else:
                        # ── EDITABLE ──
                        input_key = f"field_{oid}_{fkey}"

                        if ftype == "checkbox":
                            new_val = st.checkbox(flabel, value=(current.lower() == "true"), key=input_key)
                            new_val_str = "true" if new_val else "false"
                            if new_val_str != current:
                                ok, err = update_field(t, fkey, new_val_str)
                                if not ok:
                                    st.error(err)
                        elif ftype == "select" and options:
                            idx = options.index(current) if current in options else 0
                            new_val = st.selectbox(flabel, options, index=idx, key=input_key)
                            if new_val != current:
                                if st.button(s("field_save"), key=f"fs_{oid}_{fkey}"):
                                    ok, err = update_field(t, fkey, new_val)
                                    if ok:
                                        fetch_tasks.clear()
                                        st.rerun()
                                    else:
                                        st.error(err)
                        else:
                            col_in, col_btn = st.columns([5, 1])
                            with col_in:
                                new_val = st.text_input(flabel, value=current,
                                                        placeholder="https://..." if is_url else "",
                                                        key=input_key)
                            with col_btn:
                                if is_url and new_val:
                                    st.link_button("↗", new_val)
                            if new_val != current:
                                if st.button(s("field_save"), key=f"fs_{oid}_{fkey}"):
                                    ok, err = update_field(t, fkey, new_val or None)
                                    if ok:
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
            for key in ["va_name", "va_tag", "auth_ok"]:
                st.session_state.pop(key, None)
            st.rerun()

    _hf_raw = st.secrets.get("HIDE_FUTURE_TASKS", True)
    hide_future = str(_hf_raw).lower() not in ("false", "0", "no")

    _ht_raw = st.secrets.get("HIDE_WITHOUT_TUTORIAL", False)
    hide_no_tutorial_default = str(_ht_raw).lower() not in ("false", "0", "no")

    col_refresh, col_view, col_sort, col_tutorial, col_completed, col_translate = st.columns([1, 2, 2, 2, 2, 2])
    with col_refresh:
        if st.button(s("refresh")):
            fetch_tasks.clear()
            fetch_translations.clear()
            st.rerun()
    with col_view:
        view = st.radio(s("view_label"),
                        [s("view_grouped"), s("view_flat")],
                        horizontal=True, label_visibility="collapsed")
    with col_sort:
        sort_by = st.selectbox("Sort", ["Due date", "Priority", "Name", "Last edited"],
                               label_visibility="collapsed")
    with col_tutorial:
        hide_no_tutorial = st.toggle("🎬 Tutorial only", value=hide_no_tutorial_default)
    with col_completed:
        show_completed = st.toggle("✅ Show completed", value=False)
    with col_translate:
        translate_on = st.toggle(s("translate_toggle"), value=False)

    # ── fetch tasks ──
    fetch_status = "all" if show_completed else status
    with st.spinner(s("loading")):
        try:
            tasks = fetch_tasks(project_id, tag_name, fetch_status)
        except requests.HTTPError as e:
            st.error(f"{s('err_backend')}: {e.response.status_code} — {e.response.text[:200]}")
            return
        except requests.ConnectionError:
            st.error(s("err_conn"))
            return

    # ── filters ──
    if not show_completed:
        tasks = [t for t in tasks if not _is_completed(t)]
    if hide_future:
        today = date.today()
        tasks = [t for t in tasks if _due_date(t) is not None and _due_date(t) <= today]
    if hide_no_tutorial:
        tasks = [t for t in tasks if t.get("youtube_tutorial")]

    # ── sort ──
    def _prio_val(t):
        raw = t.get("priority")
        return raw.get("value", 0) if isinstance(raw, dict) else (raw or 0)

    if sort_by == "Priority":
        tasks = sorted(tasks, key=lambda t: -_prio_val(t))
    elif sort_by == "Name":
        tasks = sorted(tasks, key=lambda t: (t.get("nameText") or t.get("name", "")).lower())
    elif sort_by == "Last edited":
        tasks = sorted(tasks, key=lambda t: t.get("editedAt") or "", reverse=True)
    else:
        tasks = sorted(tasks, key=lambda t: (_due_date(t) or date.max))

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

    # ── tabs ──
    tab_tasks, tab_audit = st.tabs([f"📋 {s('title')}", f"🕵️ {s('audit_tab')}"])

    with tab_tasks:
        if view == s("view_grouped"):
            render_grouped(tasks, trans_map)
        else:
            render_flat(tasks, trans_map)

    with tab_audit:
        _render_audit()


def _render_audit():
    try:
        r = requests.get(_backend("/quire/audit/log"),
                         headers=_headers(), params={"limit": 200}, timeout=10)
        entries = r.json().get("entries", []) if r.ok else []
    except Exception:
        st.error(s("err_conn"))
        return

    if not entries:
        st.info(s("audit_empty"))
        return

    # filter by VA
    va_names = sorted({e["va_name"] for e in entries})
    col_f, _ = st.columns([2, 8])
    with col_f:
        chosen = st.selectbox(s("audit_filter"),
                              [s("audit_all")] + va_names, label_visibility="collapsed")

    if chosen != s("audit_all"):
        entries = [e for e in entries if e["va_name"] == chosen]

    for e in entries:
        action_key, icon = AUDIT_ACTION_KEYS.get(e["action"], ("", "•"))
        verb  = s(action_key) if action_key else e["action"]
        name  = e.get("task_name") or ""
        url   = e.get("task_url") or ""
        task_link = f"[{name}]({url})" if url else name
        ts    = (e.get("created_at") or "")[:16].replace("T", " ")
        va    = e.get("va_name", "")

        line = f"{icon} **{va}** {verb} {task_link}"
        if e["action"] == "rename" and e.get("new_value"):
            line += f" → *{e['new_value']}*"
        st.markdown(line)
        st.caption(ts)
        st.divider()


if __name__ == "__main__":
    main()
