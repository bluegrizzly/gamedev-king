import io
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from rag import require_project_path, resolve_project_path
from local_settings import load_image_defaults

MAX_FILENAME_LEN = 120
ALLOWED_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
ALLOWED_IMAGE_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
ALLOWED_FORMATS = {"png", "jpg", "jpeg", "webp"}
ALLOWED_DIMENSIONS = {
    672,
    768,
    832,
    864,
    896,
    1024,
    1152,
    1184,
    1248,
    1344,
}
MAX_PROMPT_LEN = 1000
MAX_IMAGES = 4


def _shorten_prompt(prompt: str, max_len: int = MAX_PROMPT_LEN) -> str:
    cleaned = " ".join(prompt.split())
    if len(cleaned) <= max_len:
        return cleaned
    # Try to cut at a sentence boundary near the limit.
    slice_candidate = cleaned[:max_len]
    for separator in (". ", "; ", ", "):
        idx = slice_candidate.rfind(separator)
        if idx > max_len * 0.6:
            return slice_candidate[: idx + 1].strip()
    return slice_candidate.rstrip()


def get_images_dir(project_key: Optional[str] = None) -> Path:
    raw = os.getenv("IMAGES_OUTPUT_DIR")
    if not raw:
        project_dir = require_project_path(project_key) if project_key else resolve_project_path(project_key)
        raw = str(Path(project_dir) / "Images") if project_dir else "./output/images"
    elif not Path(raw).is_absolute():
        project_dir = require_project_path(project_key) if project_key else resolve_project_path(project_key)
        if project_dir:
            raw = str(Path(project_dir) / raw)
    output_dir = Path(os.path.expandvars(raw)).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def sanitize_filename(value: str, default_ext: str = "png") -> str:
    cleaned = value.replace("\\", "_").replace("/", "_").strip()
    cleaned = cleaned.replace("..", "_")
    cleaned = ALLOWED_FILENAME_RE.sub("_", cleaned).strip(" ._")
    if not cleaned:
        cleaned = "image"
    if "." not in cleaned:
        cleaned = f"{cleaned}.{default_ext}"
    if len(cleaned) > MAX_FILENAME_LEN:
        base, ext = cleaned.rsplit(".", 1)
        base = base[: MAX_FILENAME_LEN - (len(ext) + 1)].rstrip(" ._")
        cleaned = f"{base}.{ext}"
    return cleaned


def validate_image_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise ValueError("Filename is required.")
    if "/" in cleaned or "\\" in cleaned or ":" in cleaned:
        raise ValueError("Invalid filename.")
    if ".." in cleaned:
        raise ValueError("Invalid filename.")
    if not ALLOWED_IMAGE_RE.match(cleaned):
        raise ValueError("Filename contains invalid characters.")
    ext = cleaned.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_FORMATS:
        raise ValueError("Unsupported image format.")
    if len(cleaned) > MAX_FILENAME_LEN:
        raise ValueError("Filename is too long.")
    return cleaned


def safe_resolve_path(filename: str, project_key: Optional[str] = None) -> Path:
    output_dir = get_images_dir(project_key).resolve()
    candidate = (output_dir / filename).resolve()
    if output_dir not in candidate.parents and candidate != output_dir:
        raise ValueError("Invalid filename path.")
    return candidate


def build_image_filename(prefix: str = "image", ext: str = "png") -> str:
    safe_prefix = ALLOWED_FILENAME_RE.sub("_", prefix).strip(" ._").lower() or "image"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return sanitize_filename(f"{safe_prefix}_{timestamp}_{suffix}.{ext}", ext)


def save_bytes_to_file(data: bytes, filename: str, project_key: Optional[str] = None) -> Path:
    safe_name = sanitize_filename(filename)
    output_path = safe_resolve_path(safe_name, project_key)
    output_path.write_bytes(data)
    return output_path


def build_image_url(filename: str, project_key: Optional[str] = None) -> str:
    url = f"/images/{filename}"
    if project_key:
        url = f"{url}?project_key={project_key}"
    return url


def _clamp_dimension(value: int) -> int:
    return value if value in ALLOWED_DIMENSIONS else 1024


def _find_first_key(payload: object, keys: set[str], depth: int = 0) -> str | None:
    if depth > 5:
        return None
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                return value
        for value in payload.values():
            found = _find_first_key(value, keys, depth + 1)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_first_key(item, keys, depth + 1)
            if found:
                return found
    return None


def _extract_generation_id(payload: dict) -> str | None:
    return _find_first_key(payload, {"generationId", "generation_id", "id"})


def _collect_image_urls(payload: object, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    urls: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"images", "generated_images"} and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("url"):
                        urls.append(item["url"])
            else:
                urls.extend(_collect_image_urls(value, depth + 1))
    elif isinstance(payload, list):
        for item in payload:
            urls.extend(_collect_image_urls(item, depth + 1))
    return urls


def _extract_image_urls(payload: object) -> list[str]:
    return _collect_image_urls(payload)


def _placeholder_image(width: int, height: int, text: str) -> bytes:
    img = Image.new("RGB", (width, height), color=(30, 41, 59))
    draw = ImageDraw.Draw(img)
    message = text[:80]
    draw.text((20, 20), message, fill=(226, 232, 240), font=ImageFont.load_default())
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def _extract_error_details(payload: object) -> str:
    if isinstance(payload, dict):
        return str(payload.get("error") or payload.get("detail") or payload)
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            extensions = first.get("extensions") or {}
            if isinstance(extensions, dict):
                return str(extensions.get("details") or first.get("message") or payload)
        return str(first)
    return str(payload)


def generate_image(
    prompt: str,
    negative_prompt: str | None = None,
    width: int = 1024,
    height: int = 1024,
    num_images: int = 1,
    seed: int | None = None,
    model: str = "gemini-2.5-flash-image",
    project_key: Optional[str] = None,
) -> dict:
    if not prompt or len(prompt.strip()) == 0:
        raise ValueError("Prompt is required.")
    prompt = _shorten_prompt(prompt, MAX_PROMPT_LEN)

    width = _clamp_dimension(width)
    height = _clamp_dimension(height)
    quantity = max(1, min(num_images, MAX_IMAGES))

    api_key = os.getenv("LEONARDO_API_KEY")
    if not api_key:
        image_bytes = _placeholder_image(width, height, "Leonardo API key missing.")
        filename = build_image_filename("leonardo_stub", "png")
        output_path = save_bytes_to_file(image_bytes, filename, project_key)
        return {
            "images": [
                {
                    "filename": filename,
                    "url": build_image_url(filename, project_key),
                    "path": str(output_path),
                }
            ]
        }

    base_url = os.getenv("LEONARDO_API_BASE", "https://cloud.leonardo.ai/api/rest/v2").rstrip("/")
    base_url_v1 = os.getenv("LEONARDO_API_BASE_V1", "https://cloud.leonardo.ai/api/rest/v1").rstrip("/")
    headers = {
        "accept": "application/json", 
        "content-type": "application/json", 
        "authorization": f"Bearer {api_key}"
        }

    model = "gemini-2.5-flash-image"
    base_payload = {
        "model": model,
        "parameters": {
            "width": width,
            "height": height,
            "prompt": prompt,
            "quantity": quantity,
            "prompt_enhance": "OFF",
            "style_ids": [
                "111dc692-d470-4eec-b791-3475abac4c46"
            ]
        },
        "public": False,
    }
    if negative_prompt:
        base_payload["parameters"]["negative_prompt"] = negative_prompt
    if seed is not None:
        base_payload["parameters"]["seed"] = seed

    payload = base_payload

    response = requests.post(f"{base_url}/generations", json=payload, headers=headers, timeout=120)
    response_text = response.text
    try:
        data = response.json()
    except ValueError:
        data = response_text

    if not response.ok:
        print(f"[leonardo] generate failed: {response.status_code} payload={payload} body={data}")
        raise ValueError(f"Leonardo request failed: {_extract_error_details(data)}")

    if isinstance(data, dict) and any(key in data for key in ("error", "errors", "detail")):
        print(f"[leonardo] generate error payload: {data} payload={payload}")
        raise ValueError(f"Leonardo request failed: {_extract_error_details(data)}")

    if isinstance(data, list):
        print(f"[leonardo] generate error list: {data} payload={payload}")
        raise ValueError(f"Leonardo request failed: {_extract_error_details(data)}")
    urls = _extract_image_urls(data)
    if urls:
        generation_id = None
    else:
        generation_id = None
        if isinstance(data, dict) and isinstance(data.get("generate"), dict):
            generation_id = data["generate"].get("generationId")
        if not generation_id:
            generation_id = _extract_generation_id(data)
            if not generation_id:
                top_keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
                print(f"[leonardo] response body: {data}")
                raise ValueError(f"Leonardo response missing generation id. Keys: {top_keys}")

    if generation_id:
        poll_url = f"{base_url_v1}/generations/{generation_id}"
        urls = []
        start = time.time()
        while time.time() - start < 120:
            poll_response = requests.get(poll_url, headers=headers, timeout=30)
            poll_response.raise_for_status()
            poll_data = poll_response.json()
            urls = _extract_image_urls(poll_data)
            if urls:
                break
            time.sleep(2)

        if not urls:
            raise ValueError("Leonardo generation timed out.")

    images: list[dict] = []
    for idx, url in enumerate(urls[:quantity]):
        image_response = requests.get(url, timeout=60)
        image_response.raise_for_status()
        filename = build_image_filename(f"leonardo_{idx+1}", "png")
        output_path = save_bytes_to_file(image_response.content, filename, project_key)
        images.append(
            {
                "filename": filename,
                "url": build_image_url(filename, project_key),
                "path": str(output_path),
            }
        )

    return {"images": images}


def resize_image(
    input_filename: str,
    width: int,
    height: int,
    mode: str = "contain",
    output_filename: str | None = None,
    project_key: Optional[str] = None,
) -> dict:
    safe_name = validate_image_filename(input_filename)
    input_path = safe_resolve_path(safe_name, project_key)
    if not input_path.exists():
        raise ValueError("Input image not found.")

    width = _clamp_dimension(width)
    height = _clamp_dimension(height)
    mode = mode if mode in {"contain", "cover", "stretch"} else "contain"

    image = Image.open(input_path)
    if mode == "stretch":
        resized = image.resize((width, height))
    elif mode == "cover":
        resized = ImageOps.fit(image, (width, height))
    else:
        resized = ImageOps.contain(image, (width, height))
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        offset = ((width - resized.width) // 2, (height - resized.height) // 2)
        canvas.paste(resized, offset)
        resized = canvas

    output_name = output_filename or build_image_filename("resize", "png")
    output_name = sanitize_filename(output_name, "png")
    output_path = safe_resolve_path(output_name, project_key)
    resized.save(output_path, format="PNG")
    return {
        "filename": output_name,
        "url": build_image_url(output_name, project_key),
        "path": str(output_path),
    }


def crop_image(
    input_filename: str,
    x: int,
    y: int,
    width: int,
    height: int,
    output_filename: str | None = None,
    project_key: Optional[str] = None,
) -> dict:
    safe_name = validate_image_filename(input_filename)
    input_path = safe_resolve_path(safe_name, project_key)
    if not input_path.exists():
        raise ValueError("Input image not found.")

    image = Image.open(input_path)
    x = max(0, x)
    y = max(0, y)
    width = max(1, width)
    height = max(1, height)
    right = min(image.width, x + width)
    lower = min(image.height, y + height)
    if right <= x or lower <= y:
        raise ValueError("Invalid crop area.")

    cropped = image.crop((x, y, right, lower))
    output_name = output_filename or build_image_filename("crop", "png")
    output_name = sanitize_filename(output_name, "png")
    output_path = safe_resolve_path(output_name, project_key)
    cropped.save(output_path, format="PNG")
    return {
        "filename": output_name,
        "url": build_image_url(output_name, project_key),
        "path": str(output_path),
    }


def convert_image(
    input_filename: str,
    format: str,
    quality: int | None = None,
    output_filename: str | None = None,
    project_key: Optional[str] = None,
) -> dict:
    safe_name = validate_image_filename(input_filename)
    input_path = safe_resolve_path(safe_name, project_key)
    if not input_path.exists():
        raise ValueError("Input image not found.")

    target_format = format.lower()
    if target_format not in {"png", "jpg", "jpeg", "webp"}:
        raise ValueError("Unsupported format.")

    image = Image.open(input_path)
    save_kwargs = {}
    if target_format in {"jpg", "jpeg"}:
        image = image.convert("RGB")
        if quality:
            save_kwargs["quality"] = max(1, min(int(quality), 95))

    ext = "jpg" if target_format == "jpeg" else target_format
    output_name = output_filename or build_image_filename("convert", ext)
    output_name = sanitize_filename(output_name, ext)
    output_path = safe_resolve_path(output_name, project_key)
    image.save(output_path, format=target_format.upper(), **save_kwargs)
    return {
        "filename": output_name,
        "url": build_image_url(output_name, project_key),
        "path": str(output_path),
    }


def run_generate_image_tool(args: dict) -> dict:
    defaults = load_image_defaults()
    prompt = str(args.get("prompt", "")).strip()
    style = str(defaults.get("style", "")).strip()
    if style and "style" not in prompt.lower():
        prompt = f"{prompt} Style: {style}."
    return generate_image(
        prompt=prompt,
        negative_prompt=args.get("negative_prompt"),
        width=int(args.get("width", defaults.get("width", 1024))),
        height=int(args.get("height", defaults.get("height", 1024))),
        num_images=int(args.get("num_images", defaults.get("num_images", 1))),
        seed=args.get("seed"),
        model=args.get("model", "gemini-image-2"),
        project_key=str(args.get("project_key", "")).strip() or None,
    )


def run_resize_image_tool(args: dict) -> dict:
    return resize_image(
        input_filename=str(args.get("input_filename", "")).strip(),
        width=int(args.get("width", 1024)),
        height=int(args.get("height", 1024)),
        mode=str(args.get("mode", "contain")).strip(),
        output_filename=args.get("output_filename"),
        project_key=str(args.get("project_key", "")).strip() or None,
    )


def run_crop_image_tool(args: dict) -> dict:
    return crop_image(
        input_filename=str(args.get("input_filename", "")).strip(),
        x=int(args.get("x", 0)),
        y=int(args.get("y", 0)),
        width=int(args.get("width", 1)),
        height=int(args.get("height", 1)),
        output_filename=args.get("output_filename"),
        project_key=str(args.get("project_key", "")).strip() or None,
    )


def run_convert_image_tool(args: dict) -> dict:
    return convert_image(
        input_filename=str(args.get("input_filename", "")).strip(),
        format=str(args.get("format", "")).strip(),
        quality=args.get("quality"),
        output_filename=args.get("output_filename"),
        project_key=str(args.get("project_key", "")).strip() or None,
    )
