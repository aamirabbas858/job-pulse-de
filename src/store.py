import json
import os
from datetime import datetime

CACHE_FILE = "data/cache.json"


def save(data: dict):
    os.makedirs("data", exist_ok=True)
    data["fetched_at"] = datetime.now().isoformat()
    # Atomic: a crash mid-write must not leave a truncated cache behind.
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CACHE_FILE)


def load() -> dict | None:
    if not os.path.exists(CACHE_FILE):
        return None
    with open(CACHE_FILE) as f:
        return json.load(f)


def age_hours(data: dict) -> float:
    fetched = data.get("fetched_at", "")
    if not fetched:
        return 999
    delta = datetime.now() - datetime.fromisoformat(fetched)
    return delta.total_seconds() / 3600
