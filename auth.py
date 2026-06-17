import os
from pathlib import Path
from typing import Optional


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


_load_local_env()
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "").strip()
WRITE_API_KEY = os.environ.get("WRITE_API_KEY", "").strip()


def is_site_auth_enabled() -> bool:
    return bool(SITE_PASSWORD)


def is_write_enabled() -> bool:
    return bool(WRITE_API_KEY)


def verify_site_password(password: Optional[str]) -> bool:
    if not is_site_auth_enabled():
        return True
    if not password:
        return False
    return password.strip() == SITE_PASSWORD


def verify_write_key(key: Optional[str]) -> bool:
    if not is_write_enabled():
        return False
    if not key:
        return False
    return key.strip() == WRITE_API_KEY


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
