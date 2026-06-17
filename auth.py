import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

_SECRET_KEYS = (
    "SITE_PASSWORD",
    "SITE_PASSWORD_HASH",
    "WRITE_API_KEY",
    "WRITE_API_KEY_HASH",
    "PUBLIC_BASE_URL",
    "SECRET_HASH_SALT",
)


def _load_local_env() -> None:
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _secrets_toml_paths() -> list[Path]:
    base = Path(__file__).resolve().parent
    cwd = Path.cwd()
    return [
        base / ".streamlit" / "secrets.toml",
        cwd / ".streamlit" / "secrets.toml",
        Path(".streamlit/secrets.toml"),
    ]


def _load_secrets_toml(path: Path) -> bool:
    if not path.is_file():
        return False
    loaded = False
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in _SECRET_KEYS and value:
            os.environ[key] = value
            loaded = True
    return loaded


def _load_streamlit_secrets() -> None:
    for path in _secrets_toml_paths():
        _load_secrets_toml(path)

    try:
        import streamlit as st

        for key in _SECRET_KEYS:
            if os.environ.get(key, "").strip():
                continue
            try:
                value = str(st.secrets[key]).strip()
            except (KeyError, TypeError, AttributeError):
                continue
            if value:
                os.environ[key] = value
    except Exception:
        pass


def reload_config() -> None:
    _load_streamlit_secrets()
    _load_local_env()


def config_status() -> dict:
    reload_config()
    paths = _secrets_toml_paths()
    return {
        "site_auth_enabled": is_site_auth_enabled(),
        "write_enabled": is_write_enabled(),
        "site_hash_configured": bool(get_config("SITE_PASSWORD_HASH")),
        "write_hash_configured": bool(get_config("WRITE_API_KEY_HASH")),
        "secrets_file_found": any(p.is_file() for p in paths),
        "public_base_url": get_config("PUBLIC_BASE_URL"),
    }


def get_config(name: str) -> str:
    reload_config()
    return os.environ.get(name, "").strip()


def is_site_auth_enabled() -> bool:
    reload_config()
    return bool(os.environ.get("SITE_PASSWORD", "").strip() or os.environ.get("SITE_PASSWORD_HASH", "").strip())


def is_write_enabled() -> bool:
    reload_config()
    return bool(os.environ.get("WRITE_API_KEY", "").strip() or os.environ.get("WRITE_API_KEY_HASH", "").strip())


def hash_secret(value: str, *, salt: str = "") -> str:
    """One-way SHA-256 hash. Use the same salt when generating and verifying."""
    payload = f"{salt}{value.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _hash_salt() -> str:
    return get_config("SECRET_HASH_SALT")


def _verify_against_hash(plain: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    computed = hash_secret(plain, salt=_hash_salt())
    return secrets.compare_digest(computed, stored_hash.strip().lower())


def _verify_secret(
    plain: Optional[str],
    *,
    plain_key: str,
    hash_key: str,
) -> bool:
    if not plain:
        return False
    value = plain.strip()
    stored_plain = get_config(plain_key)
    if stored_plain:
        return secrets.compare_digest(value, stored_plain)
    stored_hash = get_config(hash_key)
    if stored_hash:
        return _verify_against_hash(value, stored_hash)
    return False


def verify_site_password(password: Optional[str]) -> bool:
    if not is_site_auth_enabled():
        return True
    return _verify_secret(
        password,
        plain_key="SITE_PASSWORD",
        hash_key="SITE_PASSWORD_HASH",
    )


def verify_write_key(key: Optional[str]) -> bool:
    if not is_write_enabled():
        return False
    return _verify_secret(
        key,
        plain_key="WRITE_API_KEY",
        hash_key="WRITE_API_KEY_HASH",
    )


def extract_site_password_from_headers(headers: dict, query_params: dict) -> Optional[str]:
    pwd = headers.get("x-site-password") or headers.get("X-Site-Password")
    if pwd:
        return pwd.strip()
    q = query_params.get("site_password")
    if isinstance(q, list):
        q = q[0] if q else None
    return q.strip() if q else None


def extract_write_key_from_headers(headers: dict, query_params: dict) -> Optional[str]:
    key = headers.get("x-write-key") or headers.get("X-Write-Key")
    if key:
        return key.strip()
    q = query_params.get("key")
    if isinstance(q, list):
        q = q[0] if q else None
    return q.strip() if q else None


def require_site_password(password: Optional[str]) -> None:
    if not is_site_auth_enabled():
        return
    if not verify_site_password(password):
        raise PermissionError("Site login required: invalid or missing password")


def require_write_key(key: Optional[str]) -> None:
    if not is_write_enabled():
        raise PermissionError("Service is read-only: WRITE_API_KEY is not configured")
    if not verify_write_key(key):
        raise PermissionError("Invalid or missing Write Key")


def get_public_base_url() -> str:
    return get_config("PUBLIC_BASE_URL")
