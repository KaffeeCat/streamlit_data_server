/**
 * Example 3: Delete an entire table.
 *
 * Default target: https://dbserver.streamlit.app
 * Prerequisites: table exists (run 01_create_table_and_write.mjs first)
 *
 * Run: node tutorial/js/03_delete_table.mjs
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

async function listTables() {
  const resp = await apiFetch(apiUrl(`/api/databases/${DATABASE}/tables`), {
    headers: siteHeaders(),
  });
  return checkResponse(resp, "list tables");
}

async function deleteTable(tableName, confirm = true) {
  const url = new URL(apiUrl(`/api/databases/${DATABASE}/tables/${tableName}`));
  url.searchParams.set("confirm", confirm ? "true" : "false");
  url.searchParams.set("actor", ACTOR);
  const resp = await apiFetch(url, {
    method: "DELETE",
    headers: writeHeaders(),
    body: JSON.stringify({ actor: ACTOR }),
  });
  return checkResponse(resp, `delete table ${tableName}`);
}

console.log(`Target: ${DATABASE}/${TABLE}\n`);

const before = await listTables();
const names = before.map((t) => t.name);
console.log(`Tables before delete (${names.length}): ${names.join(", ") || "(none)"}`);

if (!names.includes(TABLE)) {
  console.log(`\nTable '${TABLE}' not found. Run 01_create_table_and_write.mjs first.`);
  process.exit(0);
}

console.log(`\nDeleting table '${TABLE}' (requires Write Key + confirm=true)...`);
const result = await deleteTable(TABLE);
console.log(`Deleted: ${result.deleted}`);

const after = await listTables();
const remaining = after.map((t) => t.name);
console.log(`\nTables after delete (${remaining.length}): ${remaining.join(", ") || "(none)"}`);

if (remaining.includes(TABLE)) {
  throw new Error(`Table '${TABLE}' still exists after delete`);
}

console.log("\nDone.");
