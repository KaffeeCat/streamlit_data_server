"""
示例 3：删除整张表

默认连接线上服务 https://dbserver.streamlit.app
前置条件：目标表已存在（例如运行过 01_create_table_and_write.py）

运行：
  python tutorial/03_delete_table.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import ACTOR, DATABASE, api_request, check_response, site_headers, write_headers

TABLE = "tutorial_products"


def list_tables() -> list[dict]:
    resp = api_request(
        "GET",
        f"/api/databases/{DATABASE}/tables",
        headers=site_headers(),
    )
    return check_response(resp, "list tables")


def delete_table(table_name: str, *, confirm: bool = True) -> dict:
    params = {"confirm": "true" if confirm else "false", "actor": ACTOR}
    resp = api_request(
        "DELETE",
        f"/api/databases/{DATABASE}/tables/{table_name}",
        headers=write_headers(),
        params=params,
        json={"actor": ACTOR},
    )
    return check_response(resp, f"delete table {table_name}")


def main() -> None:
    print(f"Target: {DATABASE}/{TABLE}\n")

    before = list_tables()
    names = [t["name"] for t in before]
    print(f"Tables before delete ({len(names)}): {', '.join(names) or '(none)'}")

    if TABLE not in names:
        print(f"\nTable '{TABLE}' not found. Run 01_create_table_and_write.py first.")
        return

    print(f"\nDeleting table '{TABLE}' (requires Write Key + confirm=true)...")
    result = delete_table(TABLE)
    print(f"Deleted: {result.get('deleted')}")

    after = list_tables()
    remaining = [t["name"] for t in after]
    print(f"\nTables after delete ({len(remaining)}): {', '.join(remaining) or '(none)'}")

    if TABLE in remaining:
        raise RuntimeError(f"Table '{TABLE}' still exists after delete")

    print("\nDone.")


if __name__ == "__main__":
    main()
