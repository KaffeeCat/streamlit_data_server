"""
示例 1：创建表并写入示例数据

默认连接线上服务 https://dbserver.streamlit.app
前置条件：项目根目录 .env 中已配置 SITE_PASSWORD 和 WRITE_API_KEY

运行：
  python tutorial/01_create_table_and_write.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import ACTOR, DATABASE, api_request, check_response, write_headers

TABLE = "tutorial_products"

COLUMNS = [
    {"name": "sku", "type": "TEXT"},
    {"name": "name", "type": "TEXT"},
    {"name": "price", "type": "REAL"},
    {"name": "stock", "type": "INTEGER"},
]

SAMPLE_ROWS = [
    {"sku": "SKU-001", "name": "Wireless Mouse", "price": 29.9, "stock": 120},
    {"sku": "SKU-002", "name": "Mechanical Keyboard", "price": 89.0, "stock": 45},
    {"sku": "SKU-003", "name": "USB-C Hub", "price": 45.5, "stock": 80},
]


def create_table() -> dict:
    resp = api_request(
        "POST",
        f"/api/databases/{DATABASE}/tables",
        headers=write_headers(),
        json={
            "name": TABLE,
            "display_name": "Tutorial Products",
            "columns": COLUMNS,
            "max_rows": 1000,
            "actor": ACTOR,
        },
    )
    return check_response(resp, "建表")


def insert_row(row: dict) -> dict:
    resp = api_request(
        "POST",
        f"/api/databases/{DATABASE}/tables/{TABLE}/rows",
        headers=write_headers(),
        json={"actor": ACTOR, **row},
    )
    return check_response(resp, f"插入 {row.get('sku')}")


def main() -> None:
    print(f"目标: {DATABASE}/{TABLE}\n")

    schema = create_table()
    print(f"已建表 · max_rows={schema.get('max_rows')} · 列: {[c['name'] for c in schema.get('columns', [])]}")

    inserted = []
    for row in SAMPLE_ROWS:
        result = insert_row(row)
        inserted.append(result.get("_rowid"))
        print(f"  插入 _rowid={result.get('_rowid')} · {row['sku']} · {row['name']}")

    print(f"\n完成：共写入 {len(inserted)} 行。")
    print("下一步: python tutorial/02_read_insert_and_delete.py")


if __name__ == "__main__":
    main()
