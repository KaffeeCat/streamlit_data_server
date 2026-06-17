import html
import os
import textwrap

import pandas as pd
import streamlit as st

import data_service
from auth import (
    get_public_base_url,
    is_site_auth_enabled,
    is_write_enabled,
    reload_config,
    verify_site_password,
    verify_write_key,
)
from import_parsers import parse_upload
from schema import validate_actor
from visit_stats import load_visit_stats, record_session_visit

APP_NAME = "Streamlit Data Server"
APP_TAGLINE = "Online Database"
AUTHOR_NAME = "KaffeeCat"
AUTHOR_URL = os.environ.get("AUTHOR_URL", "https://github.com/KaffeeCat").rstrip("/")
DEFAULT_PORT = os.environ.get("STREAMLIT_SERVER_PORT", "8501")

reload_config()
data_service.initialize()


@st.cache_data(show_spinner=False)
def load_databases_cached(meta_mtime: float) -> list:
    return data_service.list_databases()


@st.cache_data(show_spinner=False)
def load_tables_cached(meta_mtime: float, db_name: str) -> list:
    return data_service.list_tables(db_name)


@st.cache_data(show_spinner=False)
def load_recent_cached(meta_mtime: float, limit: int) -> list:
    return data_service.get_recent_uploads(limit)


def clear_data_caches() -> None:
    load_databases_cached.clear()
    load_tables_cached.clear()
    load_recent_cached.clear()


def get_app_base_url() -> str:
    configured = get_public_base_url()
    if configured:
        return configured.rstrip("/")
    try:
        headers = st.context.headers
        if headers:
            host = headers.get("Host")
            if host:
                if host.endswith(".streamlit.app") or host.endswith(".streamlit.io"):
                    return f"https://{host}"
                proto = headers.get("X-Forwarded-Proto", "https")
                return f"{proto}://{host}"
    except Exception:
        pass
    return f"http://localhost:{DEFAULT_PORT}"


def _render_html(content: str) -> None:
    cleaned = textwrap.dedent(content).strip()
    if hasattr(st, "html"):
        st.html(cleaned)
    else:
        st.markdown(cleaned, unsafe_allow_html=True)


def _card_open(extra_style: str = "") -> str:
    return (
        f'<div style="background:rgba(128,128,128,0.08);border:1px solid rgba(128,128,128,0.22);'
        f'border-radius:12px;padding:1.15rem 1.25rem;margin-bottom:1rem;{extra_style}">'
    )


CARD_CLOSE = "</div>"


def _meta_chip(text: str) -> str:
    safe = html.escape(text)
    return (
        f'<span style="display:inline-block;padding:0.2rem 0.55rem;margin-right:0.4rem;'
        f'border-radius:999px;background:rgba(128,128,128,0.14);font-size:0.78rem;'
        f'font-weight:500;color:inherit;">{safe}</span>'
    )


def inject_app_styles() -> None:
    _render_html(
        """
        <style>
        section.main div[data-testid="stFormSubmitButton"] > button,
        div[data-testid="stDownloadButton"] > button {
            border-radius: 8px !important;
            font-weight: 600 !important;
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
            border: none !important;
            color: white !important;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25) !important;
        }
        </style>
        """
    )


def render_page_header() -> None:
    _render_html(
        f"""
        {_card_open("margin-bottom:1.25rem;")}
        <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                    letter-spacing:0.12em;color:rgba(128,128,128,0.95);margin-bottom:0.35rem;">
            {APP_TAGLINE}
        </div>
        <div style="font-size:1.85rem;font-weight:700;line-height:1.2;margin-bottom:0.45rem;">
            {APP_NAME}
        </div>
        <div style="font-size:0.95rem;line-height:1.55;color:rgba(128,128,128,0.95);max-width:42rem;">
            Upload, query, and share structured data. Site login required.
            Writes also require a Write Key.
        </div>
        {CARD_CLOSE}
        """
    )


def track_visit() -> dict:
    if st.session_state.get("_visit_recorded"):
        return load_visit_stats()
    st.session_state._visit_recorded = True
    host, user_agent = "", ""
    try:
        headers = st.context.headers
        if headers:
            host = headers.get("Host", "")
            user_agent = headers.get("User-Agent", "")
    except Exception:
        pass
    return record_session_visit(host=host, user_agent=user_agent)


def init_session() -> None:
    st.session_state.setdefault("actor", "")
    st.session_state.setdefault("write_key", "")
    st.session_state.setdefault("write_authorized", False)
    st.session_state.setdefault("current_db", "default")
    st.session_state.setdefault("site_authenticated", False)


def render_site_login() -> None:
    if not is_site_auth_enabled():
        return
    if st.session_state.get("site_authenticated"):
        return

    st.markdown("### Login")
    st.caption("Enter the site password to access this application.")
    with st.form("site_login_form"):
        password = st.text_input("Site password", type="password")
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
    if submitted:
        if verify_site_password(password):
            st.session_state.site_authenticated = True
            st.rerun()
        else:
            st.error("Invalid site password")
    st.stop()


def get_actor() -> str:
    actor = st.session_state.get("actor", "").strip()
    if not actor:
        raise ValueError("Please enter your display name in the sidebar first")
    return validate_actor(actor)


def can_write() -> bool:
    return is_write_enabled() and st.session_state.get("write_authorized", False)


def render_sidebar(visit_stats: dict) -> str:
    init_session()
    with st.sidebar:
        st.markdown("### Identity")
        actor = st.text_input("Display name *", key="actor_input", value=st.session_state.actor)
        if actor != st.session_state.actor:
            st.session_state.actor = actor.strip()

        write_key = st.text_input(
            "Write Key",
            type="password",
            key="write_key_input",
            value=st.session_state.write_key,
            disabled=not is_write_enabled(),
        )
        if write_key != st.session_state.write_key:
            st.session_state.write_key = write_key
            st.session_state.write_authorized = verify_write_key(write_key)

        if not is_write_enabled():
            st.warning("Read-only mode: WRITE_API_KEY / WRITE_API_KEY_HASH is not configured")
        elif st.session_state.write_authorized:
            st.success("Write Key verified")
        elif write_key:
            st.error("Invalid Write Key")

        st.divider()
        st.markdown("### Database")

        meta_mtime = data_service.get_meta_mtime()
        dbs = load_databases_cached(meta_mtime)
        db_names = [d["name"] for d in dbs]
        if st.session_state.current_db not in db_names:
            st.session_state.current_db = db_names[0] if db_names else "default"

        current_db = st.selectbox(
            "Current database",
            db_names,
            index=db_names.index(st.session_state.current_db),
        )
        st.session_state.current_db = current_db

        if can_write():
            with st.expander("Create database"):
                with st.form("create_db_form"):
                    new_db_name = st.text_input("Database slug", placeholder="sales_2026")
                    new_db_display = st.text_input("Display name", placeholder="Sales 2026")
                    if st.form_submit_button("Create", use_container_width=True):
                        try:
                            data_service.create_database(
                                name=new_db_name,
                                display_name=new_db_display or new_db_name,
                                actor=get_actor(),
                            )
                            clear_data_caches()
                            st.session_state.current_db = new_db_name.strip().lower()
                            st.success(f"Database created: {new_db_name}")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

        st.divider()
        st.caption(f"Visits · {visit_stats.get('total_sessions', 0)}")
        st.caption(f"API · {get_app_base_url()}/api/health")

        if is_site_auth_enabled() and st.session_state.get("site_authenticated"):
            if st.button("Log out", use_container_width=True):
                st.session_state.site_authenticated = False
                st.session_state.write_authorized = False
                st.rerun()

    return st.session_state.current_db


def render_upload_tab(db_name: str) -> None:
    st.subheader("Upload Data")
    if not can_write():
        st.info("Upload requires a valid Write Key and display name.")
        return

    tables = load_tables_cached(data_service.get_meta_mtime(), db_name)
    table_names = [t["name"] for t in tables]

    mode = st.radio("Import mode", ["create", "append", "replace"], horizontal=True)
    table_name = st.text_input("Table name", placeholder="my_table")

    max_rows = 0
    if mode == "create":
        max_rows = st.number_input("Max rows (0 = unlimited)", min_value=0, value=0, step=1000)

    if mode in {"append", "replace"} and table_names:
        pick = st.selectbox("Or pick existing table", ["— type manually —"] + table_names)
        if pick != "— type manually —":
            table_name = pick

    uploaded = st.file_uploader(
        "Choose file",
        type=["csv", "tsv", "xlsx", "json", "jsonl"],
    )

    if uploaded and table_name.strip():
        try:
            df = parse_upload(uploaded.name, uploaded.getvalue())
            st.caption(f"Preview · {len(df)} rows × {len(df.columns)} columns")
            st.dataframe(df.head(20), use_container_width=True)

            if st.button("Import", type="primary", use_container_width=True):
                result = data_service.import_dataframe(
                    db_name,
                    table_name.strip().lower(),
                    df,
                    mode=mode,
                    actor=get_actor(),
                    max_rows=int(max_rows),
                    source_filename=uploaded.name,
                )
                clear_data_caches()
                st.success(
                    f"Import complete · {result['rows_affected']} rows · "
                    f"table total {result['table']['row_count']} rows"
                )
                st.rerun()
        except Exception as e:
            st.error(str(e))


def render_tables_tab(db_name: str) -> None:
    st.subheader("Tables")
    meta_mtime = data_service.get_meta_mtime()
    tables = load_tables_cached(meta_mtime, db_name)

    if not tables:
        st.info("No tables in this database. Go to Upload to create one.")
        return

    qp_table = st.query_params.get("table")
    if isinstance(qp_table, list):
        qp_table = qp_table[0] if qp_table else None

    table_names = [t["name"] for t in tables]
    default_idx = table_names.index(qp_table) if qp_table in table_names else 0

    col_list, col_detail = st.columns([1, 2], gap="large")

    with col_list:
        selected = st.radio(
            "Table list",
            table_names,
            index=default_idx,
            format_func=lambda n: next(
                f"{t['name']} ({t['row_count']}/{t['max_rows'] or '∞'})" for t in tables if t["name"] == n
            ),
        )

    meta = next(t for t in tables if t["name"] == selected)

    with col_detail:
        _render_html(
            f"""
            {_card_open()}
            <div style="font-size:1.2rem;font-weight:700;margin-bottom:0.5rem;">{html.escape(selected)}</div>
            {_meta_chip(f"{meta['row_count']} rows")}
            {_meta_chip(f"max {meta['max_rows'] or '∞'}")}
            {_meta_chip(f"by {meta['created_by']}")}
            {CARD_CLOSE}
            """
        )

        page = st.number_input("Page", min_value=1, value=1, step=1, key=f"page_{selected}")
        limit = 50
        offset = (page - 1) * limit

        try:
            result = data_service.query_rows(db_name, selected, limit=limit, offset=offset)
            st.dataframe(pd.DataFrame(result["rows"]), use_container_width=True)
            total_pages = max(1, (result["total"] + limit - 1) // limit)
            st.caption(f"Page {page}/{total_pages} · {result['total']} rows total")
        except Exception as e:
            st.error(str(e))

        exp_col1, exp_col2, exp_col3 = st.columns(3)
        for fmt, label in [("csv", "CSV"), ("json", "JSON"), ("xlsx", "Excel")]:
            with {"csv": exp_col1, "json": exp_col2, "xlsx": exp_col3}[fmt]:
                try:
                    content, _, fname = data_service.export_table(db_name, selected, fmt)
                    st.download_button(
                        label=f"Export {label}",
                        data=content,
                        file_name=fname,
                        use_container_width=True,
                        key=f"export_{selected}_{fmt}",
                    )
                except Exception as e:
                    st.caption(str(e))

        if can_write():
            with st.expander("Insert row"):
                with st.form(f"insert_{selected}"):
                    inputs = {}
                    for col in meta["columns"]:
                        inputs[col["name"]] = st.text_input(col["name"], key=f"ins_{selected}_{col['name']}")
                    if st.form_submit_button("Insert"):
                        try:
                            data_service.insert_row(db_name, selected, inputs, actor=get_actor())
                            clear_data_caches()
                            st.success("Row inserted")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

            delete_id = st.number_input("Delete row _rowid", min_value=1, step=1, key=f"del_id_{selected}")
            if st.button("Delete row", key=f"del_btn_{selected}"):
                try:
                    data_service.delete_row(db_name, selected, int(delete_id), actor=get_actor())
                    clear_data_caches()
                    st.success("Row deleted")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

            if st.button("Delete table", type="secondary", key=f"drop_{selected}"):
                st.session_state[f"confirm_drop_{selected}"] = True

            if st.session_state.get(f"confirm_drop_{selected}"):
                st.warning(f"Delete table `{selected}`? This cannot be undone.")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Confirm delete", key=f"confirm_drop_yes_{selected}"):
                        try:
                            data_service.delete_table(db_name, selected, actor=get_actor())
                            clear_data_caches()
                            st.session_state.pop(f"confirm_drop_{selected}", None)
                            st.success("Table deleted")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with c2:
                    if st.button("Cancel", key=f"confirm_drop_no_{selected}"):
                        st.session_state.pop(f"confirm_drop_{selected}", None)
                        st.rerun()


def _default_sql(db_name: str) -> str:
    tables = load_tables_cached(data_service.get_meta_mtime(), db_name)
    if tables:
        return f"SELECT * FROM {tables[0]['name']} LIMIT 10"
    return "SELECT 1 AS ok"


def render_sql_tab(db_name: str) -> None:
    st.subheader("SQL Console")
    sql_key = f"sql_draft_{db_name}"
    legacy_invalid = "SELECT * FROM ... LIMIT 10"

    if sql_key not in st.session_state:
        legacy = st.session_state.get("sql_draft")
        if legacy and legacy != legacy_invalid:
            st.session_state[sql_key] = legacy
        else:
            st.session_state[sql_key] = _default_sql(db_name)

    sql = st.text_area("SQL", height=160, key=sql_key)

    if can_write():
        st.caption("Authorized: write SQL allowed (INSERT / UPDATE / DELETE / CREATE / DROP)")
    else:
        st.caption("Read-only: SELECT and PRAGMA only")

    if st.button("Run", type="primary"):
        try:
            result = data_service.execute_sql(
                db_name,
                sql,
                allow_write=can_write(),
                actor=st.session_state.get("actor") or None,
            )
            if result["kind"] == "read":
                if result["rows"]:
                    st.dataframe(pd.DataFrame(result["rows"]), use_container_width=True)
                else:
                    st.info("No results")
            else:
                clear_data_caches()
                st.success(f"Executed · {result['rows_affected']} rows affected")
        except Exception as e:
            st.error(str(e))


def render_recent_tab() -> None:
    st.subheader("Recent Activity")
    logs = load_recent_cached(data_service.get_meta_mtime(), 30)
    if not logs:
        st.info("No activity yet")
        return

    for entry in logs:
        ts = entry.get("uploaded_at", "")[:19].replace("T", " ")
        label = (
            f"**{entry.get('uploaded_by', '?')}** · "
            f"`{entry.get('db_name')}/{entry.get('table_name')}` · "
            f"{entry.get('action')} · {entry.get('rows_affected', 0)} rows · {ts} UTC"
        )
        st.markdown(label)
        if entry.get("source_filename"):
            st.caption(f"File: {entry['source_filename']}")


st.set_page_config(
    page_title=APP_NAME,
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session()
render_site_login()
inject_app_styles()
visit_stats = track_visit()
current_db = render_sidebar(visit_stats)
render_page_header()

tab_upload, tab_tables, tab_sql, tab_recent = st.tabs(["Upload", "Tables", "SQL", "Recent"])

with tab_upload:
    render_upload_tab(current_db)
with tab_tables:
    render_tables_tab(current_db)
with tab_sql:
    render_sql_tab(current_db)
with tab_recent:
    render_recent_tab()
