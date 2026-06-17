#!/usr/bin/env python3
"""Generate SHA-256 hashes for Streamlit Cloud Secrets (SITE_PASSWORD_HASH, etc.)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth import _load_local_env, hash_secret


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hash a secret for SITE_PASSWORD_HASH / WRITE_API_KEY_HASH in Cloud Secrets."
    )
    parser.add_argument("secret", help="Plain-text password or key to hash")
    parser.add_argument(
        "--salt",
        default="",
        help="Optional salt (must match SECRET_HASH_SALT on the server). "
        "Defaults to SECRET_HASH_SALT from .env if present.",
    )
    args = parser.parse_args()

    _load_local_env()
    salt = args.salt or os.environ.get("SECRET_HASH_SALT", "")

    digest = hash_secret(args.secret, salt=salt)
    print(digest)
    if salt:
        print(f"# salt: {salt}", file=sys.stderr)
    print(
        "# Paste into Streamlit Cloud Secrets, e.g. SITE_PASSWORD_HASH = \"...\"",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
