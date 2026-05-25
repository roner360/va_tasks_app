"""
Streamlit app — Task delegabili per VA.
Chiama il backend FastAPI (backend.py) invece di Quire direttamente.

Segreti attesi in .streamlit/secrets.toml:
  BACKEND_URL      — URL del backend FastAPI
  BACKEND_API_KEY  — x-api-key richiesta dal backend
  QUIRE_PROJECT_ID — slug del progetto Quire (visibile nell'URL)
  DELEGABLE_TAG    — tag da mostrare al VA (default: delegabile)
  TASK_STATUS      — active | completed | all (default: active)
  VA_PASSWORD      — password per il gate VA (vuoto = nessun gate)
"""
import streamlit as st
import requests
from datetime import date, datetime


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


def complete_task(task_oid: str) -> tuple[bool, str]:
    try:
        r = requests.post(
            _backend(f"/quire/tasks/{task_oid}/complete"),
            headers=_headers(),
            timeout=10,
        )
        if r.ok:
            return True, ""
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    except requests.ConnectionError:
        return False, "Impossibile raggiungere il backend"
    except requests.Timeout:
        return False, "Timeout backend"


def _priority_label(raw) -> str:
    val = raw.get("value", 0) if isinstance(raw, dict) else raw
    return {-1: "Urgente", 0: "", 1: "Alta", 2: "Media", 3: "Bassa"}.get(val, str(val or ""))


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
    """Returns (sort_order, label) for grouping by due date."""
    d = _due_date(t)
    today = date.today()
    if d is None:
        return (3, "Senza scadenza")
    if d < today:
        return (0, "Scaduti")
    if d == today:
        return (1, "Oggi")
    if (d - today).days <= 7:
        return (2, f"Questa settimana")
    return (3, f"Più avanti")


# ── password gate ──────────────────────────────────────────────────────────

def password_gate() -> bool:
    va_password = st.secrets.get("VA_PASSWORD", "")
    if not va_password or st.session_state.get("auth_ok"):
        return True

    st.title("Accesso riservato")
    pwd = st.text_input("Password", type="password")
    if st.button("Entra"):
        if pwd == va_password:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False


# ── single task card ───────────────────────────────────────────────────────

def _task_card(t: dict) -> None:
    oid  = t.get("oid", "")
    name = t.get("nameText") or t.get("name", "(senza nome)")
    due  = (_due_date(t).strftime("%d/%m/%Y") if _due_date(t) else "")
    prio = _priority_label(t.get("priority"))
    stat = _status_label(t.get("status"))
    url  = t.get("url", "")

    with st.container(border=True):
        col_name, col_meta, col_btn = st.columns([5, 3, 1])

        with col_name:
            st.markdown(f"**[{name}]({url})**" if url else f"**{name}**")

        with col_meta:
            parts = []
            if stat: parts.append(f"Stato: {stat}")
            if prio: parts.append(f"Priorità: {prio}")
            if due:  parts.append(f"Scadenza: {due}")
            st.caption("  ·  ".join(parts))

        with col_btn:
            if st.button("Completa", key=f"complete_{oid}"):
                ok, err = complete_task(oid)
                if ok:
                    st.success("Fatto!")
                    fetch_tasks.clear()
                    st.rerun()
                else:
                    st.error(err)


# ── views ──────────────────────────────────────────────────────────────────

def render_flat(tasks: list[dict]) -> None:
    if not tasks:
        st.info("Nessun task trovato.")
        return
    for t in tasks:
        _task_card(t)


def render_grouped(tasks: list[dict]) -> None:
    if not tasks:
        st.info("Nessun task trovato.")
        return

    groups: dict[str, list] = {}
    order:  dict[str, int]  = {}
    for t in tasks:
        sort_n, label = _group_key(t)
        groups.setdefault(label, []).append(t)
        order[label] = sort_n

    group_colors = {
        "Scaduti":          "🔴",
        "Oggi":             "🟠",
        "Questa settimana": "🟡",
        "Più avanti":       "🟢",
        "Senza scadenza":   "⚪",
    }

    for label in sorted(groups, key=lambda l: order[l]):
        icon  = group_colors.get(label, "•")
        count = len(groups[label])
        with st.expander(f"{icon} **{label}** ({count})", expanded=(order[label] <= 1)):
            for t in sorted(groups[label], key=lambda x: _due_date(x) or date.max):
                _task_card(t)


# ── main ───────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Task Delegabili", page_icon="📋", layout="wide")

    if not password_gate():
        return

    project_id = st.secrets["QUIRE_PROJECT_ID"]
    tag_name   = st.secrets.get("DELEGABLE_TAG", "delegabile")
    status     = st.secrets.get("TASK_STATUS", "active")

    st.title(f"📋 Task delegabili  —  #{tag_name}")

    col_refresh, col_view, col_info = st.columns([1, 3, 6])
    with col_refresh:
        if st.button("🔄 Refresh"):
            fetch_tasks.clear()
            st.rerun()
    with col_view:
        view = st.radio("Vista", ["Per scadenza", "Lista"], horizontal=True, label_visibility="collapsed")

    with st.spinner("Carico i task..."):
        try:
            tasks = fetch_tasks(project_id, tag_name, status)
        except requests.HTTPError as e:
            st.error(f"Errore backend: {e.response.status_code} — {e.response.text[:200]}")
            return
        except requests.ConnectionError:
            st.error("Impossibile connettersi al backend. Verifica BACKEND_URL nei secrets.")
            return

    with col_info:
        st.caption(f"{len(tasks)} task · cache 5 min")

    if view == "Per scadenza":
        render_grouped(tasks)
    else:
        render_flat(tasks)


if __name__ == "__main__":
    main()
