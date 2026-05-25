"""
Streamlit app — Task delegabili per VA.
Chiama il backend FastAPI (backend.py) invece di Quire direttamente:
  GET {BACKEND_URL}/quire/tasks/by-tag?tag=<DELEGABLE_TAG>&project_id=<PROJECT_ID>

Segreti attesi in .streamlit/secrets.toml:
  BACKEND_URL   — URL del tuo backend FastAPI (es. https://mio-backend.railway.app)
  BACKEND_API_KEY — x-api-key richiesta dal backend
  QUIRE_PROJECT_ID — slug del progetto Quire (visibile nell'URL)
  DELEGABLE_TAG    — tag da mostrare al VA (default: delegabile)
  VA_PASSWORD      — password per il gate VA (vuoto = nessun gate)
"""
import streamlit as st
import requests
import pandas as pd


# ── helpers ────────────────────────────────────────────────────────────────

def _backend_headers() -> dict:
    return {"x-api-key": st.secrets["BACKEND_API_KEY"]}


@st.cache_data(ttl=300)
def fetch_delegable_tasks(project_id: str, tag: str, status: str) -> list[dict]:
    backend_url = st.secrets["BACKEND_URL"].rstrip("/")
    params = {"tag": tag, "project_id": project_id, "status": status}
    r = requests.get(
        f"{backend_url}/quire/tasks/by-tag",
        headers=_backend_headers(),
        params=params,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["tasks"]


def render_table(tasks: list[dict]) -> None:
    if not tasks:
        st.info("Nessun task trovato con questo tag.")
        return

    rows = []
    for t in tasks:
        status_raw = t.get("status")
        if isinstance(status_raw, dict):
            status_label = status_raw.get("name", "")
        else:
            status_label = str(status_raw) if status_raw is not None else ""

        priority_raw = t.get("priority")
        try:
            priority_label = {-1: "Urgente", 0: "", 1: "Alta", 2: "Media", 3: "Bassa"}.get(
                int(priority_raw), str(priority_raw or ""))
        except (TypeError, ValueError):
            priority_label = str(priority_raw or "")

        rows.append({
            "Task":     t.get("nameText") or t.get("name", ""),
            "Stato":    status_label,
            "Priorità": priority_label,
            "Scadenza": (t.get("due") or "")[:10],
            "Link":     t.get("url", ""),
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        column_config={"Link": st.column_config.LinkColumn("Link", display_text="Apri →")},
        hide_index=True,
    )


def password_gate() -> bool:
    va_password = st.secrets.get("VA_PASSWORD", "")
    if not va_password:
        return True
    if st.session_state.get("auth_ok"):
        return True

    st.title("🔐 Accesso riservato")
    pwd = st.text_input("Password", type="password")
    if st.button("Entra"):
        if pwd == va_password:
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False


# ── main ───────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Task Delegabili", page_icon="📋", layout="wide")

    if not password_gate():
        return

    project_id = st.secrets["QUIRE_PROJECT_ID"]
    tag_name   = st.secrets.get("DELEGABLE_TAG", "delegabile")
    status     = st.secrets.get("TASK_STATUS", "active")

    st.title(f"📋 Task delegabili  —  #{tag_name}")
    st.caption("Cache 5 min. Usa Refresh per aggiornare subito.")

    col_btn, col_info = st.columns([1, 9])
    with col_btn:
        if st.button("🔄 Refresh"):
            fetch_delegable_tasks.clear()
            st.rerun()

    with st.spinner("Carico i task..."):
        try:
            tasks = fetch_delegable_tasks(project_id, tag_name, status)
        except requests.HTTPError as e:
            st.error(f"Errore backend: {e.response.status_code} — {e.response.text[:200]}")
            return
        except requests.ConnectionError:
            st.error("Impossibile connettersi al backend. Verifica BACKEND_URL nei secrets.")
            return

    with col_info:
        st.caption(f"{len(tasks)} task trovati")

    render_table(tasks)


if __name__ == "__main__":
    main()
