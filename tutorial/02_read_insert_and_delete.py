"""
示例 2：读取表、插入新行、删除指定行

前置条件：
  - 已运行 01_create_table_and_write.py（表 tutorial_products 存在）
  - 本地服务已启动

运行：
  python tutorial/02_read_insert_and_delete.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from config import ACTOR, DATABASE, api_url, check_response, site_headers, write_headers

TABLE = "tutorial_products"


def list_rows(*, limit: int = 20) -> dict:
    resp = requests.get(
        api_url(f"/api/databases/{DATABASE}/tables/{TABLE}/rows"),
        headers=site_headers(),
        params={"limit": limit, "order": "asc"},
        timeout=30,
    )
    return check_response(resp, "读取表")


def insert_row(row: dict) -> dict:
    resp = requests.post(
        api_url(f"/api/databases/{DATABASE}/tables/{TABLE}/rows"),
        headers=write_headers(),
        json={"actor": ACTOR, **row},
        timeout=30,
    )
    return check_response(resp, "插入新行")


def delete_row(row_id: int) -> dict:
    resp = requests.delete(
        api_url(f"/api/databases/{DATABASE}/tables/{TABLE}/rows/{row_id}"),
        headers=write_headers(),
        json={"actor": ACTOR},
        timeout=30,
    )
    return check_response(resp, f"删除 _rowid={row_id}")


def print_rows(rows: list[dict], title: str) -> None:
    print(title)
    if not rows:
        print("  (空表)")
        return
    for r in rows:
        print(
            f"  _rowid={r.get('_rowid')} · {r.get('sku')} · "
            f"{r.get('name')} · price={r.get('price')} · stock={r.get('stock')}"
        )


def main() -> None:
    print(f"目标: {DATABASE}/{TABLE}\n")

    # 1. 读取（无需 Write Key）
    before = list_rows()
    print_rows(before["rows"], f"当前数据（共 {before['total']} 行）:")

    # 2. 插入一行（需 Write Key）
    new_row = insert_row(
        {"sku": "SKU-004", "name": "Webcam HD", "price": 199.0, "stock": 30}
    )
    print(f"\n已插入新行 _rowid={new_row.get('_rowid')} · {new_row.get('name')}")

    # 3. 再次读取
    middle = list_rows()
    print_rows(middle["rows"], f"\n插入后（共 {middle['total']} 行）:")

    # 4. 删除第一行（按 _rowid）
    target_id = before["rows"][0]["_rowid"] if before["rows"] else new_row["_rowid"]
    delete_row(int(target_id))
    print(f"\n已删除 _rowid={target_id}")

    # 5. 最终状态
    after = list_rows()
    print_rows(after["rows"], f"\n删除后（共 {after['total']} 行）:")
    print("\n完成。")
    print("下一步: python tutorial/03_delete_table.py")


if __name__ == "__main__":
    main()
