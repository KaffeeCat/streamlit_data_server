/**
 * Shared config for JavaScript tutorials.
 * Loads SITE_PASSWORD and WRITE_API_KEY from environment or project-root .env.
 */
import { readFileSync, existsSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ENV_FILE = join(__dirname, "..", "..", ".env");

export const DEFAULT_BASE_URL = "https://dbserver.streamlit.app";
export const BASE_URL = (process.env.DATA_SERVER_URL || DEFAULT_BASE_URL).replace(/\/$/, "");
export const DATABASE = process.env.DATA_SERVER_DB || "default";
export const ACTOR = process.env.DATA_SERVER_ACTOR || "tutorial";

function readEnvValue(name) {
  const fromEnv = process.env[name]?.trim();
  if (fromEnv) return fromEnv;
  if (!existsSync(ENV_FILE)) return "";
  for (const line of readFileSync(ENV_FILE, "utf-8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (trimmed.startsWith(`${name}=`)) {
      return trimmed.slice(name.length + 1).trim().replace(/^["']|["']$/g, "");
    }
  }
  return "";
}

export const SITE_PASSWORD = readEnvValue("SITE_PASSWORD");
export const WRITE_KEY = readEnvValue("WRITE_API_KEY");

if (!WRITE_KEY) {
  throw new Error("WRITE_API_KEY not found in .env or environment");
}

export function apiUrl(path) {
  return `${BASE_URL}${path}`;
}

export function siteHeaders() {
  const headers = { Accept: "application/json" };
  if (SITE_PASSWORD) headers["X-Site-Password"] = SITE_PASSWORD;
  return headers;
}

export function writeHeaders() {
  return {
    ...siteHeaders(),
    "X-Write-Key": WRITE_KEY,
    "Content-Type": "application/json",
  };
}

export async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    ...options,
    redirect: "manual",
    headers: { Accept: "application/json", ...options.headers },
  });
  if (resp.status >= 300 && resp.status < 400) {
    const location = resp.headers.get("location") || "";
    throw new Error(
      `${options.method || "GET"} ${url} redirected (${resp.status}) — ` +
        `ensure Streamlit Cloud app is Public. Location: ${location.slice(0, 120)}`,
    );
  }
  return resp;
}

export async function checkResponse(resp, action) {
  let body;
  const text = await resp.text();
  try {
    body = JSON.parse(text);
  } catch {
    const hint =
      text.trimStart().startsWith("<!") || text.trimStart().startsWith("<a ")
        ? " (got HTML — API request did not reach the server; retry or check Cloud visibility)"
        : "";
    throw new Error(`${action} failed (${resp.status}): non-JSON response${hint}`);
  }
  if (!resp.ok || !body.ok) {
    const error = body.error || text;
    throw new Error(`${action} failed (${resp.status}): ${error}`);
  }
  return body.data;
}
