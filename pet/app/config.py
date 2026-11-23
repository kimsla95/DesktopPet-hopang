import copy
import json
import os
import sys

APP_NAME = "DesktopPet"
ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]

DEFAULTS = {
    "character": "anpanman",
    "size": 150,
    "pos": None,
    "roam": False,
    "alarms": [
        {"time": "12:00", "message": "밥 먹자!", "enabled": True, "days": ALL_DAYS},
        {"time": "18:00", "message": "퇴근하자!", "enabled": True, "days": ALL_DAYS},
    ],
    "cheer": {"enabled": True, "min_minutes": 30, "max_minutes": 120},
    "quiet": {"enabled": True, "start": "22:00", "end": "08:00"},
    # repo: "owner/name" overrides version.json; empty = use the repo baked into the build
    "update": {"enabled": True, "interval_hours": 6, "last_check": 0, "repo": ""},
}


def app_info():
    """Bundled version.json: {"version": "x.y.z", "repo": "owner/name"}."""
    root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    try:
        with open(os.path.join(root, "version.json"), encoding="utf-8-sig") as f:
            info = json.load(f)
    except (OSError, ValueError):
        info = {}
    return {"version": str(info.get("version", "0.0.0")), "repo": str(info.get("repo", ""))}


def character_dirs():
    """Folders searched for characters/<name>/; a characters/ folder next to the exe wins."""
    if getattr(sys, "frozen", False):
        return [os.path.join(os.path.dirname(sys.executable), "characters"),
                os.path.join(sys._MEIPASS, "characters")]
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return [os.path.join(root, "assets", "characters")]


def settings_path():
    root = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "settings.json")


def load():
    data = copy.deepcopy(DEFAULTS)
    try:
        with open(settings_path(), encoding="utf-8-sig") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return data
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key].update(value)
        else:
            data[key] = value
    return data


def save(data):
    path = settings_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass
