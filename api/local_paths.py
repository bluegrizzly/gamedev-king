import json
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_DIR = PROJECT_ROOT / ".local_data"
PATHS_FILE = LOCAL_DATA_DIR / "project_paths.json"


def load_project_paths() -> dict[str, str]:
    if not PATHS_FILE.exists():
        return {}
    try:
        data = json.loads(PATHS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
    except Exception:
        return {}
    return {}


def save_project_paths(data: dict[str, str]) -> None:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PATHS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_local_project_path(project_key: str) -> Optional[str]:
    if not project_key:
        return None
    return load_project_paths().get(project_key)


def set_local_project_path(project_key: str, path: str) -> None:
    if not project_key:
        return
    cleaned = path.strip()
    if not cleaned:
        return
    data = load_project_paths()
    data[project_key] = cleaned
    save_project_paths(data)


def delete_local_project_path(project_key: str) -> None:
    if not project_key:
        return
    data = load_project_paths()
    if project_key in data:
        data.pop(project_key, None)
        save_project_paths(data)


def require_local_project_path(project_key: Optional[str]) -> str:
    if not project_key:
        raise ValueError("Project key is required to resolve a local project path.")
    path = get_local_project_path(project_key)
    if not path:
        raise ValueError(
            f"Local project path is not set for '{project_key}'. "
            "Set it in Admin > Project Config."
        )
    return path
