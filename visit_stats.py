import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VISITS_PATH = BASE_DIR / "data" / "visits.json"
MAX_RECENT = 100


def _default_stats() -> dict:
    return {
        "total_sessions": 0,
        "last_visit_at": None,
        "recent": [],
    }


def load_visit_stats() -> dict:
    if not VISITS_PATH.exists():
        return _default_stats()
    try:
        data = json.loads(VISITS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_stats()

    return {
        "total_sessions": int(data.get("total_sessions", 0)),
        "last_visit_at": data.get("last_visit_at"),
        "recent": data.get("recent", []) if isinstance(data.get("recent"), list) else [],
    }


def save_visit_stats(stats: dict) -> None:
    VISITS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VISITS_PATH.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_session_visit(*, host: str = "", user_agent: str = "") -> dict:
    stats = load_visit_stats()
    now = datetime.now(timezone.utc).isoformat()

    stats["total_sessions"] = stats.get("total_sessions", 0) + 1
    stats["last_visit_at"] = now

    recent = stats.get("recent", [])
    recent.insert(
        0,
        {
            "at": now,
            "host": host or "unknown",
            "user_agent": user_agent[:200] if user_agent else "",
        },
    )
    stats["recent"] = recent[:MAX_RECENT]
    save_visit_stats(stats)
    return stats
