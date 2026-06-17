import re
from typing import Literal

import pandas as pd

SQLITE_TYPES = {"TEXT", "INTEGER", "REAL", "BLOB"}

DB_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
TABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
COLUMN_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")

RESERVED_TABLE_NAMES = frozenset(
    {
        "sqlite_master",
        "sqlite_sequence",
        "sqlite_temp_master",
        "_meta_databases",
        "_meta_tables",
        "_upload_log",
    }
)

SQL_BLACKLIST = re.compile(
    r"\b(ATTACH|DETACH|LOAD_EXTENSION|READFILE|WRITEFILE|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)

SqlKind = Literal["read", "write", "forbidden"]


def validate_db_name(name: str) -> str:
    name = name.strip().lower()
    if not DB_NAME_RE.match(name):
        raise ValueError(
            "Database name must start with a lowercase letter and contain only "
            "letters, digits, and underscores (max 63 chars)"
        )
    return name


def validate_table_name(name: str) -> str:
    name = name.strip().lower()
    if not TABLE_NAME_RE.match(name):
        raise ValueError(
            "Table name must start with a lowercase letter and contain only "
            "letters, digits, and underscores (max 63 chars)"
        )
    if name in RESERVED_TABLE_NAMES or name.startswith("sqlite_") or name.startswith("_meta"):
        raise ValueError(f"Table name '{name}' is reserved")
    return name


def validate_column_name(name: str) -> str:
    name = name.strip()
    if name == "_rowid":
        raise ValueError("Column name '_rowid' is reserved")
    if not COLUMN_NAME_RE.match(name):
        raise ValueError(f"Invalid column name: '{name}'")
    return name


def validate_actor(actor: str) -> str:
    actor = (actor or "").strip()
    if not actor:
        raise ValueError("Display name (actor) is required")
    if len(actor) > 64:
        raise ValueError("Display name must be 64 characters or fewer")
    return actor


def validate_sqlite_type(type_name: str) -> str:
    upper = type_name.strip().upper()
    if upper not in SQLITE_TYPES:
        raise ValueError(f"Unsupported column type: {type_name}")
    return upper


def infer_sqlite_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TEXT"
    return "TEXT"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def classify_sql(sql: str) -> SqlKind:
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("SQL must not be empty")
    if ";" in cleaned:
        raise ValueError("Only a single SQL statement is allowed")
    if SQL_BLACKLIST.search(cleaned):
        return "forbidden"

    upper = cleaned.upper()
    if upper.startswith("SELECT") or upper.startswith("PRAGMA") or upper.startswith("EXPLAIN"):
        return "read"
    if upper.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE")):
        return "write"
    raise ValueError("Unsupported SQL statement type")
