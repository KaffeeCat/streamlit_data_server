/**
 * Example 1: Create a table and insert sample rows.
 *
 * Default target: https://dbserver.streamlit.app
 * Prerequisites: SITE_PASSWORD and WRITE_API_KEY in project-root .env
 *
 * Run: node tutorial/js/01_create_table_and_write.mjs
 */
import {
  ACTOR,
  DATABASE,
  apiFetch,
  apiUrl,
  checkResponse,
  writeHeaders,
} from "./config.mjs";

const TABLE = "tutorial_products";

const COLUMNS = [
  { name: "sku", type: "TEXT" },
  { name: "name", type: "TEXT" },
  { name: "price", type: "REAL" },
  { name: "stock", type: "INTEGER" },
];

const SAMPLE_ROWS = [
  { sku: "SKU-001", name: "Wireless Mouse", price: 29.9, stock: 120 },
  { sku: "SKU-002", name: "Mechanical Keyboard", price: 89.0, stock: 45 },
  { sku: "SKU-003", name: "USB-C Hub", price: 45.5, stock: 80 },
];

async function createTable() {
  const resp = await apiFetch(apiUrl(`/api/databases/${DATABASE}/tables`), {
    method: "POST",
    headers: writeHeaders(),
    body: JSON.stringify({
      name: TABLE,
      display_name: "Tutorial Products",
      columns: COLUMNS,
      max_rows: 1000,
      actor: ACTOR,
    }),
  });
  return checkResponse(resp, "create table");
}

async function insertRow(row) {
  const resp = await apiFetch(apiUrl(`/api/databases/${DATABASE}/tables/${TABLE}/rows`), {
    method: "POST",
    headers: writeHeaders(),
    body: JSON.stringify({ actor: ACTOR, ...row }),
  });
  return checkResponse(resp, `insert ${row.sku}`);
}

console.log(`Target: ${DATABASE}/${TABLE}\n`);

const schema = await createTable();
console.log(
  `Table created · max_rows=${schema.max_rows} · columns: ${schema.columns?.map((c) => c.name).join(", ")}`,
);

const inserted = [];
for (const row of SAMPLE_ROWS) {
  const result = await insertRow(row);
  inserted.push(result._rowid);
  console.log(`  inserted _rowid=${result._rowid} · ${row.sku} · ${row.name}`);
}

console.log(`\nDone: wrote ${inserted.length} rows.`);
console.log("Next: node tutorial/js/02_read_insert_and_delete.mjs");
