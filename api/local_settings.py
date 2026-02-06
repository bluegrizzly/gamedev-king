import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_DIR = PROJECT_ROOT / ".local_data"
IMAGE_DEFAULTS_FILE = LOCAL_DATA_DIR / "image_defaults.json"

DEFAULT_IMAGE_SETTINGS = {
    "num_images": 2,
    "width": 720,
    "height": 1280,
    "style": "high resolution cartoon, movie style",
}


def load_image_defaults() -> dict:
    if not IMAGE_DEFAULTS_FILE.exists():
        return DEFAULT_IMAGE_SETTINGS.copy()
    try:
        data = json.loads(IMAGE_DEFAULTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return DEFAULT_IMAGE_SETTINGS.copy()
        merged = DEFAULT_IMAGE_SETTINGS.copy()
        merged.update({k: v for k, v in data.items() if v is not None})
        return merged
    except Exception:
        return DEFAULT_IMAGE_SETTINGS.copy()


def save_image_defaults(payload: dict) -> dict:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = DEFAULT_IMAGE_SETTINGS.copy()
    data.update({k: v for k, v in payload.items() if v is not None})
    IMAGE_DEFAULTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
