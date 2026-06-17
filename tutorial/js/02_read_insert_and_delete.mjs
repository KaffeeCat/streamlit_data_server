/**
 * Example 2: Read rows, insert a new row, delete a row by _rowid.
 *
 * Default target: https://dbserver.streamlit.app
 * Prerequisites: run 01_create_table_and_write.mjs first
 *
 * Run: node tutorial/js/02_read_insert_and_delete.mjs
 */
import {
  ACTOR,
  DATABASE,
  apiFetch,
  apiUrl,
  checkResponse,
  siteHeaders,
  writeHeaders,
} from "./config.mjs";

const TABLE = "tutorial_products";

async function listRows(limit = 20) {
  const url = new URL(apiUrl(`/api/databases/${DATABASE}/tables/${TABLE}/rows`));
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("order", "asc");
  const resp = await apiFetch(url, { headers: siteHeaders() });
  return checkResponse(resp, "list rows");
}

async function insertRow(row) {
  const resp = await apiFetch(apiUrl(`/api/databases/${DATABASE}/tables/${TABLE}/rows`), {
    method: "POST",
    headers: writeHeaders(),
    body: JSON.stringify({ actor: ACTOR, ...row }),
  });
  return checkResponse(resp, "insert row");
}

async function deleteRow(rowId) {
  const resp = await apiFetch(
    apiUrl(`/api/databases/${DATABASE}/tables/${TABLE}/rows/${rowId}`),
    {
      method: "DELETE",
      headers: writeHeaders(),
      body: JSON.stringify({ actor: ACTOR }),
    },
  );
  return checkResponse(resp, `delete _rowid=${rowId}`);
}

function printRows(rows, title) {
  console.log(title);
  if (!rows.length) {
    console.log("  (empty)");
    return;
  }
  for (const r of rows) {
    console.log(
      `  _rowid=${r._rowid} · ${r.sku} · ${r.name} · price=${r.price} · stock=${r.stock}`,
    );
  }
}

console.log(`Target: ${DATABASE}/${TABLE}\n`);

const before = await listRows();
printRows(before.rows, `Current rows (${before.total} total):`);

const newRow = await insertRow({
  sku: "SKU-004",
  name: "Webcam HD",
  price: 199.0,
  stock: 30,
});
console.log(`\nInserted _rowid=${newRow._rowid} · ${newRow.name}`);

const middle = await listRows();
printRows(middle.rows, `\nAfter insert (${middle.total} total):`);

const targetId = before.rows[0]?._rowid ?? newRow._rowid;
await deleteRow(targetId);
console.log(`\nDeleted _rowid=${targetId}`);

const after = await listRows();
printRows(after.rows, `\nAfter delete (${after.total} total):`);
console.log("\nDone.");
console.log("Next: node tutorial/js/03_delete_table.mjs");
