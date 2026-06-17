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

| Layer | Env var | Scope |
|-------|---------|--------|
| **Site login** | `SITE_PASSWORD` | Required for UI and all API endpoints when set |
| **Write access** | `WRITE_API_KEY` | Required for create / update / delete / upload |

If `SITE_PASSWORD` is not set, the site remains open (development only).

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
| `SITE_PASSWORD` | empty | Site login password; empty = no gate |
| `WRITE_API_KEY` | empty | Write key; empty = read-only writes |
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

See [DESIGN.md](DESIGN.md) for architecture details.
