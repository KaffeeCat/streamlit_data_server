"""Shared config for tutorial scripts. Loads SITE_PASSWORD and WRITE_API_KEY from .env."""
from __future__ import annotations

import os
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_BASE_URL = "https://dbserver.streamlit.app"
BASE_URL = os.environ.get("DATA_SERVER_URL", DEFAULT_BASE_URL).rstrip("/")
DATABASE = os.environ.get("DATA_SERVER_DB", "default")
ACTOR = os.environ.get("DATA_SERVER_ACTOR", "tutorial")


def _read_env_value(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


SITE_PASSWORD = _read_env_value("SITE_PASSWORD")
WRITE_KEY = _read_env_value("WRITE_API_KEY")

if not WRITE_KEY:
    raise RuntimeError("WRITE_API_KEY not found in .env or environment")


def api_url(path: str) -> str:
    return f"{BASE_URL}{path}"


def site_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if SITE_PASSWORD:
        headers["X-Site-Password"] = SITE_PASSWORD
    return headers


def write_headers() -> dict[str, str]:
    return {
        **site_headers(),
        "X-Write-Key": WRITE_KEY,
        "Content-Type": "application/json",
    }


def check_response(resp: requests.Response, action: str) -> dict:
    if 300 <= resp.status_code < 400:
        location = resp.headers.get("Location", "")
        raise RuntimeError(
            f"{action} failed: HTTP {resp.status_code} redirect "
            f"(ensure Streamlit Cloud app is Public). Location: {location[:120]}"
        )
    try:
        body = resp.json()
    except ValueError:
        hint = ""
        text = resp.text.lstrip()
        if text.startswith("<!") or text.startswith("<a "):
            hint = " (got HTML — API request did not reach the server; retry or check Cloud visibility)"
        raise RuntimeError(f"{action} failed: non-JSON response{hint}") from None

    if not resp.ok or not body.get("ok"):
        error = body.get("error") or resp.text
        raise RuntimeError(f"{action} failed ({resp.status_code}): {error}")
    return body["data"]


def api_request(method: str, path: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", 30)
    return requests.request(
        method,
        api_url(path),
        allow_redirects=False,
        **kwargs,
    )
