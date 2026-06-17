"""Collect server hardware info and resource usage for the UI."""
from __future__ import annotations

import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
except ImportError:
    psutil = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATABASES_DIR", BASE_DIR / "data" / "databases")).parent


def format_bytes(num: Optional[int | float]) -> str:
    if num is None:
        return "—"
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _disk_stats(path: Path) -> dict[str, Any]:
    try:
        usage = psutil.disk_usage(str(path))
    except Exception:
        return {"path": str(path), "available": False}
    return {
        "path": str(path),
        "available": True,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "percent": usage.percent,
    }


def collect_system_stats(*, sample_interval: float = 0.1) -> dict[str, Any]:
    hardware: dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or "—",
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "cpu_count_logical": os.cpu_count() or 0,
        "cpu_count_physical": 0,
        "memory_total_bytes": None,
    }
    usage: dict[str, Any] = {
        "cpu_percent": None,
        "memory_used_bytes": None,
        "memory_total_bytes": None,
        "memory_available_bytes": None,
        "memory_percent": None,
        "process_memory_bytes": None,
        "process_cpu_percent": None,
        "boot_time_utc": None,
        "uptime_seconds": None,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    disks: list[dict[str, Any]] = []

    if psutil is None:
        return {
            "psutil_available": False,
            "hardware": hardware,
            "usage": usage,
            "disks": disks,
            "data_dir": str(DATA_DIR),
        }

    hardware["cpu_count_physical"] = psutil.cpu_count(logical=False) or hardware["cpu_count_logical"]
    vm = psutil.virtual_memory()
    hardware["memory_total_bytes"] = vm.total
    usage["memory_used_bytes"] = vm.used
    usage["memory_total_bytes"] = vm.total
    usage["memory_available_bytes"] = vm.available
    usage["memory_percent"] = vm.percent
    usage["cpu_percent"] = psutil.cpu_percent(interval=sample_interval)

    try:
        boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        usage["boot_time_utc"] = boot.isoformat()
        usage["uptime_seconds"] = int(time.time() - psutil.boot_time())
    except Exception:
        pass

    proc = psutil.Process()
    with proc.oneshot():
        usage["process_memory_bytes"] = proc.memory_info().rss
        try:
            usage["process_cpu_percent"] = proc.cpu_percent(interval=None)
        except Exception:
            usage["process_cpu_percent"] = None

    for path in (DATA_DIR, BASE_DIR):
        stat = _disk_stats(path)
        if stat.get("available"):
            disks.append(stat)

    seen_paths = set()
    unique_disks = []
    for item in disks:
        if item["path"] in seen_paths:
            continue
        seen_paths.add(item["path"])
        unique_disks.append(item)

    return {
        "psutil_available": True,
        "hardware": hardware,
        "usage": usage,
        "disks": unique_disks,
        "data_dir": str(DATA_DIR),
    }


def format_uptime(seconds: Optional[int]) -> str:
    if seconds is None:
        return "—"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)
