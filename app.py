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


def complete_task(task_oid: str) -> bool:
    r = requests.post(
        _backend(f"/quire/tasks/{task_oid}/complete"),
        headers=_headers(),
        timeout=10,
    )
    return r.ok


def _priority_label(raw) -> str:
    try:
        return {-1: "Urgente", 0: "", 1: "Alta", 2: "Media", 3: "Bassa"}.get(
            int(raw), str(raw or ""))
    except (TypeError, ValueError):
        return str(raw or "")


def _status_label(raw) -> str:
    if isinstance(raw, dict):
        return raw.get("name", "")
    return str(raw) if raw is not None else ""


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


# ── task list ──────────────────────────────────────────────────────────────

def render_tasks(tasks: list[dict]) -> None:
    if not tasks:
        st.info("Nessun task trovato con questo tag.")
        return

    for t in tasks:
        oid  = t.get("oid", "")
        name = t.get("nameText") or t.get("name", "(senza nome)")
        due  = (t.get("due") or "")[:10]
        prio = _priority_label(t.get("priority"))
        stat = _status_label(t.get("status"))
        url  = t.get("url", "")

        with st.container(border=True):
            col_name, col_meta, col_btn = st.columns([5, 3, 1])

            with col_name:
                st.markdown(f"**[{name}]({url})**" if url else f"**{name}**")

            with col_meta:
                parts = []
                if stat:   parts.append(f"Stato: {stat}")
                if prio:   parts.append(f"Priorità: {prio}")
                if due:    parts.append(f"Scadenza: {due}")
                st.caption("  ·  ".join(parts))

            with col_btn:
                if st.button("Completa", key=f"complete_{oid}"):
                    if complete_task(oid):
                        st.success("Fatto!")
                        fetch_tasks.clear()
                        st.rerun()
                    else:
                        st.error("Errore")


# ── main ───────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Task Delegabili", page_icon="📋", layout="wide")

    if not password_gate():
        return

    project_id = st.secrets["QUIRE_PROJECT_ID"]
    tag_name   = st.secrets.get("DELEGABLE_TAG", "delegabile")
    status     = st.secrets.get("TASK_STATUS", "active")

    st.title(f"📋 Task delegabili  —  #{tag_name}")

    col_btn, col_info = st.columns([1, 9])
    with col_btn:
        if st.button("🔄 Refresh"):
            fetch_tasks.clear()
            st.rerun()

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
        st.caption(f"{len(tasks)} task trovati · cache 5 min")

    render_tasks(tasks)


if __name__ == "__main__":
    main()
