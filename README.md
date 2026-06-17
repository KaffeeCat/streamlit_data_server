# streamlit_data_server

Lightweight online database service with site login, multi SQLite databases, file upload, and REST API.

## Quick start

```bash
pip install -r requirements.txt
```

Create `.env` in the project root:

```env
SITE_PASSWORD=your-site-password
WRITE_API_KEY=your-write-key
```

```bash
python -m streamlit run app.py
```

Open http://localhost:8501 and sign in with `SITE_PASSWORD`.

## Access control

| Layer | Config | Scope |
|-------|--------|--------|
| **Site login** | `SITE_PASSWORD` (local) or `SITE_PASSWORD_HASH` (Cloud) | UI + all API |
| **Write access** | `WRITE_API_KEY` (local) or `WRITE_API_KEY_HASH` (Cloud) | Upload / CRUD / write SQL |

Plain values in `.env` for local dev. On Streamlit Cloud, store **SHA-256 hashes only** (irreversible).

### Generate hashes for Cloud

```bash
python scripts/hash_secret.py "your-site-password"
python scripts/hash_secret.py "your-write-key"
```

Paste the hex output into Cloud Secrets as `SITE_PASSWORD_HASH` and `WRITE_API_KEY_HASH`.

Optional pepper (must match when hashing and on server):

```bash
python scripts/hash_secret.py "your-password" --salt "my-pepper"
# Set SECRET_HASH_SALT = "my-pepper" in Secrets too
```

If `SITE_PASSWORD` is not set and no hash is configured, the site remains open (development only).

## API example

```bash
# All requests need site password when SITE_PASSWORD is configured
curl http://localhost:8501/api/databases/default/tables \
  -H "X-Site-Password: your-site-password"

# Writes also need Write Key
curl -X POST "http://localhost:8501/api/databases/default/import/my_table?mode=create&actor=Alice" \
  -H "X-Site-Password: your-site-password" \
  -H "X-Write-Key: your-write-key" \
  -F "file=@data.csv"
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SITE_PASSWORD` | empty | Plain site password (local `.env` only) |
| `SITE_PASSWORD_HASH` | empty | SHA-256 hash for Cloud Secrets |
| `WRITE_API_KEY` | empty | Plain write key (local `.env` only) |
| `WRITE_API_KEY_HASH` | empty | SHA-256 hash for Cloud Secrets |
| `SECRET_HASH_SALT` | empty | Optional pepper for hashing |
| `PUBLIC_BASE_URL` | empty | Public base URL |
| `META_DB_PATH` | `data/meta.sqlite3` | Meta database path |
| `DATABASES_DIR` | `data/databases` | User database directory |

## Data directory

```
data/
├── meta.sqlite3
├── databases/
└── visits.json
```

> On Streamlit Cloud, `data/` is lost on redeploy unless you mount persistent storage.

## Deploy on Streamlit Cloud

### 1. App visibility

Set **Sharing → Public** in the Streamlit Cloud dashboard.

Private apps redirect all traffic (including `/api/*`) to Streamlit login, so external scripts and curl cannot reach your API.

Use `SITE_PASSWORD` in Secrets for access control instead.

### 2. Secrets

App dashboard → **Settings → Secrets**. Paste (use your own strong values):

```toml
SITE_PASSWORD_HASH = "sha256-hex-from-hash_secret.py"
WRITE_API_KEY_HASH = "sha256-hex-from-hash_secret.py"
PUBLIC_BASE_URL = "https://dbserver.streamlit.app"
```

Generate hashes locally with `python scripts/hash_secret.py "your-secret"`. Plain keys are never uploaded to Git or Cloud.

### 3. Redeploy

Save Secrets to trigger redeploy. You should see:

- A **Login** page before the app
- Sidebar no longer shows `WRITE_API_KEY is not configured`
- API base URL uses `https://`

### 4. Verify

```bash
curl -s https://dbserver.streamlit.app/api/health \
  -H "X-Site-Password: your-site-password"
```

Expected: JSON with `"site_auth_enabled": true`, not HTTP 303.

See [DESIGN.md](DESIGN.md) for architecture details.
