import io
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from schema import (
    classify_sql,
    infer_sqlite_type,
    quote_ident,
    validate_actor,
    validate_column_name,
    validate_db_name,
    validate_sqlite_type,
    validate_table_name,
)

BASE_DIR = Path(__file__).resolve().parent
META_DB_PATH = Path(os.environ.get("META_DB_PATH", BASE_DIR / "data" / "meta.sqlite3"))
DATABASES_DIR = Path(os.environ.get("DATABASES_DIR", BASE_DIR / "data" / "databases"))
UPLOADS_DIR = BASE_DIR / "data" / "uploads"

_write_lock = threading.RLock()
_initialized = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    META_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASES_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect(path: Path, *, row_factory: bool = True):
    conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if row_factory:
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _meta_conn():
    with _connect(META_DB_PATH) as conn:
        yield conn


def _user_db_path(db_record: dict) -> Path:
    return BASE_DIR / "data" / db_record["file_path"]


def initialize() -> None:
    global _initialized
    if _initialized:
        return
    _ensure_dirs()
    with _write_lock:
        if _initialized:
            return
        with _meta_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS _meta_databases (
                    db_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    description TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS _meta_tables (
                    db_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    description TEXT DEFAULT '',
                    columns_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    max_rows INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (db_id, name),
                    FOREIGN KEY (db_id) REFERENCES _meta_databases(db_id)
                );
                CREATE TABLE IF NOT EXISTS _upload_log (
                    id TEXT PRIMARY KEY,
                    db_id TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source_filename TEXT DEFAULT '',
                    rows_affected INTEGER NOT NULL DEFAULT 0,
                    uploaded_at TEXT NOT NULL,
                    uploaded_by TEXT NOT NULL
                );
                """
            )
            row = conn.execute(
                "SELECT 1 FROM _meta_databases WHERE name = ?", ("default",)
            ).fetchone()
            if not row:
                _create_database_unlocked(
                    conn,
                    name="default",
                    display_name="Default Database",
                    actor="system",
                    description="Default database",
                )
        _initialized = True


def _create_database_unlocked(
    conn: sqlite3.Connection,
    *,
    name: str,
    display_name: str,
    actor: str,
    description: str = "",
) -> dict:
    name = validate_db_name(name)
    actor = validate_actor(actor)
    db_id = uuid.uuid4().hex[:12]
    file_name = f"{db_id}_{name}.sqlite3"
    rel_path = f"databases/{file_name}"
    abs_path = BASE_DIR / "data" / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    with _connect(abs_path) as user_conn:
        pass

    now = _utc_now()
    conn.execute(
        """
        INSERT INTO _meta_databases (db_id, name, display_name, file_path, created_at, created_by, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (db_id, name, display_name.strip() or name, rel_path, now, actor, description or ""),
    )
    return {
        "db_id": db_id,
        "name": name,
        "display_name": display_name.strip() or name,
        "file_path": rel_path,
        "created_at": now,
        "created_by": actor,
        "description": description or "",
    }


def create_database(
    *,
    name: str,
    display_name: str,
    actor: str,
    description: str = "",
) -> dict:
    initialize()
    with _write_lock:
        with _meta_conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM _meta_databases WHERE name = ?", (validate_db_name(name),)
            ).fetchone()
            if existing:
                raise ValueError(f"Database '{name}' already exists")
            db = _create_database_unlocked(
                conn,
                name=name,
                display_name=display_name,
                actor=actor,
                description=description,
            )
            return db


def get_database_by_name(name: str) -> dict:
    initialize()
    name = validate_db_name(name)
    with _meta_conn() as conn:
        row = conn.execute(
            "SELECT * FROM _meta_databases WHERE name = ?", (name,)
        ).fetchone()
    if not row:
        raise ValueError(f"Database '{name}' not found")
    return dict(row)


def list_databases() -> list[dict]:
    initialize()
    with _meta_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM _meta_databases ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_database(name: str, *, actor: str) -> None:
    validate_actor(actor)
    db = get_database_by_name(name)
    with _write_lock:
        with _meta_conn() as conn:
            conn.execute("DELETE FROM _upload_log WHERE db_id = ?", (db["db_id"],))
            conn.execute("DELETE FROM _meta_tables WHERE db_id = ?", (db["db_id"],))
            conn.execute("DELETE FROM _meta_databases WHERE db_id = ?", (db["db_id"],))
        path = _user_db_path(db)
        if path.is_file():
            path.unlink()


def _table_row(db_id: str, table_name: str) -> sqlite3.Row:
    with _meta_conn() as conn:
        row = conn.execute(
            "SELECT * FROM _meta_tables WHERE db_id = ? AND name = ?",
            (db_id, table_name),
        ).fetchone()
    if not row:
        raise ValueError(f"Table '{table_name}' not found")
    return row


def get_table_meta(db_name: str, table_name: str) -> dict:
    db = get_database_by_name(db_name)
    row = _table_row(db["db_id"], validate_table_name(table_name))
    meta = dict(row)
    meta["db_name"] = db["name"]
    meta["columns"] = json.loads(meta.get("columns_json") or "[]")
    return meta


def list_tables(db_name: str) -> list[dict]:
    db = get_database_by_name(db_name)
    with _meta_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM _meta_tables WHERE db_id = ?
            ORDER BY updated_at DESC
            """,
            (db["db_id"],),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["db_name"] = db["name"]
        item["columns"] = json.loads(item.get("columns_json") or "[]")
        result.append(item)
    return result


def list_all_tables() -> list[dict]:
    initialize()
    result = []
    for db in list_databases():
        result.extend(list_tables(db["name"]))
    result.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    return result


def _infer_columns(df: pd.DataFrame) -> list[dict]:
    columns = []
    for col in df.columns:
        validate_column_name(str(col))
        columns.append(
            {
                "name": str(col),
                "type": infer_sqlite_type(df[col]),
                "nullable": True,
            }
        )
    return columns


def _create_physical_table(conn: sqlite3.Connection, table_name: str, columns: list[dict]) -> None:
    parts = ["_rowid INTEGER PRIMARY KEY AUTOINCREMENT"]
    for col in columns:
        validate_column_name(col["name"])
        col_type = validate_sqlite_type(col["type"])
        parts.append(f"{quote_ident(col['name'])} {col_type}")
    ddl = f"CREATE TABLE {quote_ident(table_name)} ({', '.join(parts)})"
    conn.execute(ddl)


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%dT%H:%M:%S")
        elif pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].astype(int)
    out = out.where(pd.notnull(out), None)
    return out.to_dict(orient="records")


def _insert_records(
    conn: sqlite3.Connection,
    table_name: str,
    columns: list[str],
    records: list[dict],
) -> int:
    if not records:
        return 0
    col_idents = [quote_ident(c) for c in columns]
    placeholders = ", ".join("?" for _ in columns)
    sql = (
        f"INSERT INTO {quote_ident(table_name)} ({', '.join(col_idents)}) "
        f"VALUES ({placeholders})"
    )
    values = [[rec.get(c) for c in columns] for rec in records]
    conn.executemany(sql, values)
    return len(records)


def _refresh_row_count(db_id: str, table_name: str) -> int:
    db = next(d for d in list_databases() if d["db_id"] == db_id)
    with _connect(_user_db_path(db)) as conn:
        count = conn.execute(
            f"SELECT COUNT(*) FROM {quote_ident(table_name)}"
        ).fetchone()[0]
    now = _utc_now()
    with _meta_conn() as meta:
        meta.execute(
            """
            UPDATE _meta_tables SET row_count = ?, updated_at = ?
            WHERE db_id = ? AND name = ?
            """,
            (count, now, db_id, table_name),
        )
    return count


def _check_row_limit(current: int, adding: int, max_rows: int) -> None:
    if max_rows <= 0:
        return
    if current + adding > max_rows:
        raise ValueError(
            f"Row limit exceeded: current {current}, adding {adding}, max {max_rows}"
        )


def _log_action(
    *,
    db_id: str,
    table_name: str,
    action: str,
    actor: str,
    rows_affected: int = 0,
    source_filename: str = "",
) -> dict:
    entry = {
        "id": uuid.uuid4().hex[:12],
        "db_id": db_id,
        "table_name": table_name,
        "action": action,
        "source_filename": source_filename,
        "rows_affected": rows_affected,
        "uploaded_at": _utc_now(),
        "uploaded_by": validate_actor(actor),
    }
    with _meta_conn() as conn:
        conn.execute(
            """
            INSERT INTO _upload_log
            (id, db_id, table_name, action, source_filename, rows_affected, uploaded_at, uploaded_by)
            VALUES (:id, :db_id, :table_name, :action, :source_filename, :rows_affected, :uploaded_at, :uploaded_by)
            """,
            entry,
        )
    db = next(d for d in list_databases() if d["db_id"] == db_id)
    entry["db_name"] = db["name"]
    return entry


def create_table(
    db_name: str,
    *,
    table_name: str,
    columns: list[dict],
    actor: str,
    max_rows: int = 0,
    display_name: str = "",
) -> dict:
    db = get_database_by_name(db_name)
    table_name = validate_table_name(table_name)
    actor = validate_actor(actor)
    if not columns:
        raise ValueError("At least one column is required")

    normalized = []
    seen = set()
    for col in columns:
        name = validate_column_name(col["name"])
        if name in seen:
            raise ValueError(f"Duplicate column name: {name}")
        seen.add(name)
        normalized.append(
            {"name": name, "type": validate_sqlite_type(col.get("type", "TEXT")), "nullable": True}
        )

    with _write_lock:
        with _meta_conn() as meta:
            exists = meta.execute(
                "SELECT 1 FROM _meta_tables WHERE db_id = ? AND name = ?",
                (db["db_id"], table_name),
            ).fetchone()
            if exists:
                raise ValueError(f"Table '{table_name}' already exists")

        with _connect(_user_db_path(db)) as conn:
            _create_physical_table(conn, table_name, normalized)

        now = _utc_now()
        with _meta_conn() as meta:
            meta.execute(
                """
                INSERT INTO _meta_tables
                (db_id, name, display_name, columns_json, created_at, updated_at, created_by, row_count, max_rows)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    db["db_id"],
                    table_name,
                    display_name or table_name,
                    json.dumps(normalized, ensure_ascii=False),
                    now,
                    now,
                    actor,
                    max(0, int(max_rows)),
                ),
            )
        _log_action(
            db_id=db["db_id"],
            table_name=table_name,
            action="create",
            actor=actor,
        )
    return get_table_meta(db_name, table_name)


def import_dataframe(
    db_name: str,
    table_name: str,
    df: pd.DataFrame,
    *,
    mode: str,
    actor: str,
    max_rows: int = 0,
    source_filename: str = "",
) -> dict:
    mode = mode.strip().lower()
    if mode not in {"create", "append", "replace"}:
        raise ValueError("mode must be create, append, or replace")

    actor = validate_actor(actor)
    table_name = validate_table_name(table_name)
    db = get_database_by_name(db_name)
    columns = _infer_columns(df)
    col_names = [c["name"] for c in columns]
    records = _df_to_records(df[col_names])

    with _write_lock:
        if mode == "create":
            create_table(
                db_name,
                table_name=table_name,
                columns=columns,
                actor=actor,
                max_rows=max_rows,
            )
            meta = get_table_meta(db_name, table_name)
            _check_row_limit(0, len(records), meta["max_rows"])
            with _connect(_user_db_path(db)) as conn:
                inserted = _insert_records(conn, table_name, col_names, records)
            action = "create"
        else:
            meta = get_table_meta(db_name, table_name)
            existing_cols = {c["name"] for c in meta["columns"]}
            file_cols = set(col_names)
            if not file_cols.issubset(existing_cols):
                missing = file_cols - existing_cols
                raise ValueError(
                    f"File columns incompatible with table schema, unknown: {', '.join(sorted(missing))}"
                )
            use_cols = [c for c in meta["columns"] if c["name"] in file_cols]
            use_names = [c["name"] for c in use_cols]

            if mode == "replace":
                with _connect(_user_db_path(db)) as conn:
                    conn.execute(f"DELETE FROM {quote_ident(table_name)}")
                current = 0
            else:
                current = meta["row_count"]

            _check_row_limit(current, len(records), meta["max_rows"])
            with _connect(_user_db_path(db)) as conn:
                inserted = _insert_records(conn, table_name, use_names, records)
            action = mode

        count = _refresh_row_count(db["db_id"], table_name)
        log = _log_action(
            db_id=db["db_id"],
            table_name=table_name,
            action=action,
            actor=actor,
            rows_affected=inserted,
            source_filename=source_filename,
        )
    return {
        "table": get_table_meta(db_name, table_name),
        "rows_affected": inserted,
        "log": log,
    }


def query_rows(
    db_name: str,
    table_name: str,
    *,
    limit: int = 100,
    offset: int = 0,
    order: str = "desc",
) -> dict:
    meta = get_table_meta(db_name, table_name)
    db = get_database_by_name(db_name)
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    order_sql = "DESC" if str(order).lower() != "asc" else "ASC"

    with _connect(_user_db_path(db)) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM {quote_ident(table_name)}
            ORDER BY _rowid {order_sql}
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    return {
        "rows": [dict(r) for r in rows],
        "total": meta["row_count"],
        "limit": limit,
        "offset": offset,
    }


def insert_row(db_name: str, table_name: str, data: dict, *, actor: str) -> dict:
    actor = validate_actor(actor)
    meta = get_table_meta(db_name, table_name)
    db = get_database_by_name(db_name)
    col_map = {c["name"]: c for c in meta["columns"]}
    payload = {k: v for k, v in data.items() if k in col_map and k != "_rowid"}
    if not payload:
        raise ValueError("No valid column data")

    with _write_lock:
        _check_row_limit(meta["row_count"], 1, meta["max_rows"])
        cols = list(payload.keys())
        values = [payload[c] for c in cols]
        with _connect(_user_db_path(db)) as conn:
            conn.execute(
                f"""
                INSERT INTO {quote_ident(table_name)}
                ({', '.join(quote_ident(c) for c in cols)})
                VALUES ({', '.join('?' for _ in cols)})
                """,
                values,
            )
            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            row = conn.execute(
                f"SELECT * FROM {quote_ident(table_name)} WHERE _rowid = ?",
                (row_id,),
            ).fetchone()
        _refresh_row_count(db["db_id"], table_name)
        _log_action(db_id=db["db_id"], table_name=table_name, action="insert", actor=actor, rows_affected=1)
    return dict(row) if row else {}


def update_row(db_name: str, table_name: str, row_id: int, data: dict, *, actor: str) -> dict:
    actor = validate_actor(actor)
    meta = get_table_meta(db_name, table_name)
    db = get_database_by_name(db_name)
    col_map = {c["name"]: c for c in meta["columns"]}
    payload = {k: v for k, v in data.items() if k in col_map and k != "_rowid"}
    if not payload:
        raise ValueError("No valid column data")

    sets = ", ".join(f"{quote_ident(k)} = ?" for k in payload)
    values = list(payload.values()) + [row_id]

    with _write_lock:
        with _connect(_user_db_path(db)) as conn:
            cur = conn.execute(
                f"UPDATE {quote_ident(table_name)} SET {sets} WHERE _rowid = ?",
                values,
            )
            if cur.rowcount == 0:
                raise ValueError(f"Row _rowid={row_id} not found")
        _refresh_row_count(db["db_id"], table_name)
        _log_action(db_id=db["db_id"], table_name=table_name, action="update", actor=actor, rows_affected=1)

    rows = query_rows(db_name, table_name, limit=1000)["rows"]
    match = next((r for r in rows if r.get("_rowid") == row_id), None)
    return match or {"_rowid": row_id, **payload}


def delete_row(db_name: str, table_name: str, row_id: int, *, actor: str) -> None:
    actor = validate_actor(actor)
    db = get_database_by_name(db_name)

    with _write_lock:
        with _connect(_user_db_path(db)) as conn:
            cur = conn.execute(
                f"DELETE FROM {quote_ident(table_name)} WHERE _rowid = ?",
                (row_id,),
            )
            if cur.rowcount == 0:
                raise ValueError(f"Row _rowid={row_id} not found")
        _refresh_row_count(db["db_id"], table_name)
        _log_action(
            db_id=db["db_id"],
            table_name=table_name,
            action="delete_rows",
            actor=actor,
            rows_affected=1,
        )


def delete_table(db_name: str, table_name: str, *, actor: str) -> None:
    actor = validate_actor(actor)
    db = get_database_by_name(db_name)
    table_name = validate_table_name(table_name)
    _table_row(db["db_id"], table_name)

    with _write_lock:
        with _connect(_user_db_path(db)) as conn:
            conn.execute(f"DROP TABLE IF EXISTS {quote_ident(table_name)}")
        with _meta_conn() as meta:
            meta.execute(
                "DELETE FROM _meta_tables WHERE db_id = ? AND name = ?",
                (db["db_id"], table_name),
            )
        _log_action(db_id=db["db_id"], table_name=table_name, action="drop", actor=actor)


def export_table(db_name: str, table_name: str, fmt: str) -> tuple[bytes, str, str]:
    meta = get_table_meta(db_name, table_name)
    db = get_database_by_name(db_name)
    fmt = fmt.lower()

    with _connect(_user_db_path(db)) as conn:
        df = pd.read_sql_query(f"SELECT * FROM {quote_ident(table_name)}", conn)

    if fmt == "csv":
        content = df.to_csv(index=False).encode("utf-8-sig")
        return content, "text/csv", f"{table_name}.csv"
    if fmt == "json":
        content = df.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8")
        return content, "application/json", f"{table_name}.json"
    if fmt == "xlsx":
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{table_name}.xlsx"
    raise ValueError("format must be csv, json, or xlsx")


def execute_sql(
    db_name: str,
    sql: str,
    *,
    allow_write: bool,
    actor: Optional[str] = None,
) -> dict:
    db = get_database_by_name(db_name)
    kind = classify_sql(sql)

    if kind == "forbidden":
        raise ValueError("SQL contains a forbidden operation")
    if kind == "write" and not allow_write:
        raise PermissionError("Write SQL requires a valid Write Key")
    if kind == "write":
        validate_actor(actor or "")

    lock = _write_lock if kind == "write" else nullcontext()
    with lock:
        with _connect(_user_db_path(db)) as conn:
            if kind == "read":
                cur = conn.execute(sql)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                    return {"kind": "read", "columns": cols, "rows": rows, "rows_affected": len(rows)}
                return {"kind": "read", "columns": [], "rows": [], "rows_affected": 0}
            cur = conn.execute(sql)
            affected = cur.rowcount if cur.rowcount >= 0 else 0
            _log_action(
                db_id=db["db_id"],
                table_name="*",
                action="sql",
                actor=actor or "unknown",
                rows_affected=affected,
            )
            return {"kind": "write", "rows_affected": affected}


def get_recent_uploads(limit: int = 20) -> list[dict]:
    initialize()
    limit = max(1, min(int(limit), 100))
    with _meta_conn() as conn:
        rows = conn.execute(
            """
            SELECT l.*, d.name AS db_name
            FROM _upload_log l
            JOIN _meta_databases d ON d.db_id = l.db_id
            ORDER BY l.uploaded_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_meta_mtime() -> float:
    initialize()
    return META_DB_PATH.stat().st_mtime if META_DB_PATH.exists() else 0.0
