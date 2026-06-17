"""Local end-to-end test script."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _env(name: str) -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return ""


BASE = "http://localhost:8501"
SITE = _env("SITE_PASSWORD")
KEY = _env("WRITE_API_KEY")
CSV = b"name,score\nAlice,95\nBob,88\nCarol,92\n"


def base_headers(*, write: bool = False) -> dict:
    h = {}
    if SITE:
        h["X-Site-Password"] = SITE
    if write:
        h["X-Write-Key"] = KEY
    return h


def req(method, path, *, data=None, headers=None, expect_fail=False):
    h = {**base_headers(), **(headers or {})}
    if data is not None and "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        if expect_fail:
            return e.code, parsed
        raise RuntimeError(f"{method} {path} -> {e.code}: {parsed}") from e


def main():
    ok = 0
    tests = []

    def check(name, cond, detail=""):
        tests.append((name, cond, detail))
        if cond:
            nonlocal ok
            ok += 1

    # 1. Health check
    status, health = req("GET", "/api/health")
    check("health", status == 200 and health["data"]["write_enabled"] is True)

    # 2. No site password should be rejected
    if SITE:
        r = urllib.request.Request(f"{BASE}/api/health", method="GET")
        try:
            urllib.request.urlopen(r, timeout=15)
            check("no site password blocked", False)
        except urllib.error.HTTPError as e:
            check("no site password blocked", e.code == 401)

    # 3. Write without Write Key should fail
    status, err = req(
        "POST",
        "/api/databases/default/import/e2e_test?mode=create&actor=Tester",
        data=b"dummy",
        headers={**base_headers(), "Content-Type": "application/octet-stream"},
        expect_fail=True,
    )
    check("write without key blocked", status == 403)

    # 4. Import with keys
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode() + CSV + f"\r\n--{boundary}--\r\n".encode()
    status, result = req(
        "POST",
        "/api/databases/default/import/e2e_test?mode=create&actor=Tester&max_rows=1000",
        data=body,
        headers={
            **base_headers(write=True),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    check(
        "import with key",
        status == 201 and result.get("data", {}).get("rows_affected") == 3,
        str(result),
    )

    # 5. Read tables
    status, tables = req("GET", "/api/databases/default/tables")
    names = [t["name"] for t in tables["data"]]
    check("read tables", "e2e_test" in names)

    # 6. Read rows
    status, rows = req("GET", "/api/databases/default/tables/e2e_test/rows")
    check("read rows", rows["data"]["total"] == 3)

    # 7. SELECT
    status, sql = req(
        "POST",
        "/api/databases/default/query",
        data=json.dumps({"sql": "SELECT name, AVG(score) AS avg FROM e2e_test"}).encode(),
    )
    check("select without key", sql["data"]["rows"][0]["avg"] == 91.66666666666667)

    # 8. Insert with Write Key
    status, _ = req(
        "POST",
        "/api/databases/default/tables/e2e_test/rows",
        data=json.dumps({"actor": "Tester", "name": "Dave", "score": 77}).encode(),
        headers=base_headers(write=True),
    )
    check("insert with key", status == 201)

    # 9. Export with site password
    export_req = urllib.request.Request(
        f"{BASE}/api/databases/default/export/e2e_test?format=csv",
        headers=base_headers(),
    )
    export = urllib.request.urlopen(export_req, timeout=15).read()
    check("export", b"Dave" in export and b"Alice" in export)

    # 10. Delete table
    status, _ = req(
        "DELETE",
        "/api/databases/default/tables/e2e_test?confirm=true&actor=Tester",
        data=b"{}",
        headers=base_headers(write=True),
    )
    check("delete table with key", status == 200)

    print(f"\n=== Results: {ok}/{len(tests)} passed ===\n")
    for name, passed, detail in tests:
        mark = "PASS" if passed else "FAIL"
        line = f"  [{mark}] {name}"
        if detail and not passed:
            line += f" — {detail}"
        print(line)

    if ok != len(tests):
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
