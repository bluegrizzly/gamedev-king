import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

MAX_FILENAME_LEN = 120
ALLOWED_FILENAME_RE = re.compile(r"[^a-zA-Z0-9\-_. ]+")
ALLOWED_DOWNLOAD_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def get_doc_output_dir() -> Path:
    raw = os.getenv("DOC_OUTPUT_DIR")
    if not raw:
        project_dir = os.getenv("GAME_PROJECT_DIR")
        raw = str(Path(project_dir) / "Images") if project_dir else "./output"
    output_dir = Path(os.path.expandvars(raw)).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def sanitize_filename(value: str) -> str:
    cleaned = value.replace("\\", "_").replace("/", "_").strip()
    cleaned = cleaned.replace("..", "_")
    cleaned = ALLOWED_FILENAME_RE.sub("_", cleaned)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = "document"
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    if len(cleaned) > MAX_FILENAME_LEN:
        base = cleaned[: MAX_FILENAME_LEN - 4].rstrip(" ._")
        cleaned = f"{base}.pdf"
    return cleaned


def build_filename(title: str) -> str:
    base = title.strip() or "document"
    base = base.lower().replace(" ", "_")
    base = ALLOWED_FILENAME_RE.sub("_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "document"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    return sanitize_filename(f"{base}_{timestamp}.pdf")


def ensure_output_path(filename: str) -> Path:
    output_dir = get_doc_output_dir().resolve()
    candidate = (output_dir / filename).resolve()
    if output_dir not in candidate.parents and candidate != output_dir:
        raise ValueError("Invalid filename path.")
    return candidate


def validate_download_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise ValueError("Filename is required.")
    if "/" in cleaned or "\\" in cleaned or ":" in cleaned:
        raise ValueError("Invalid filename.")
    if ".." in cleaned:
        raise ValueError("Invalid filename.")
    if not cleaned.lower().endswith(".pdf"):
        raise ValueError("Only .pdf files are allowed.")
    if not ALLOWED_DOWNLOAD_RE.match(cleaned):
        raise ValueError("Filename contains invalid characters.")
    if len(cleaned) > MAX_FILENAME_LEN:
        raise ValueError("Filename is too long.")
    return cleaned


def _wrap_line(line: str, font_name: str, font_size: int, max_width: float) -> Iterable[str]:
    if not line:
        return [""]
    words = line.split()
    current = []
    for word in words:
        test = " ".join([*current, word]) if current else word
        if stringWidth(test, font_name, font_size) <= max_width:
            current.append(word)
            continue
        if current:
            yield " ".join(current)
        current = [word]
    if current:
        yield " ".join(current)


def _wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> Iterable[str]:
    for line in text.splitlines():
        for wrapped in _wrap_line(line, font_name, font_size, max_width):
            yield wrapped


def write_pdf(title: str, content: str, filename: str) -> Tuple[str, Path]:
    safe_name = sanitize_filename(filename)
    output_path = ensure_output_path(safe_name)

    page_width, page_height = LETTER
    margin = 54
    title_font = ("Helvetica-Bold", 16)
    body_font = ("Helvetica", 10)
    line_height = 14

    pdf = canvas.Canvas(str(output_path), pagesize=LETTER)
    y = page_height - margin

    pdf.setFont(*title_font)
    pdf.drawString(margin, y, title)
    y -= line_height * 2

    pdf.setFont(*body_font)
    max_width = page_width - (margin * 2)
    for line in _wrap_text(content, body_font[0], body_font[1], max_width):
        if y <= margin:
            pdf.showPage()
            pdf.setFont(*body_font)
            y = page_height - margin
        pdf.drawString(margin, y, line)
        y -= line_height

    pdf.save()
    return safe_name, output_path


def run_export_pdf_tool(args: dict) -> dict:
    title = str(args.get("title", "")).strip()
    content = str(args.get("content", "")).strip()
    filename = str(args.get("filename", "")).strip() if args.get("filename") else ""

    if not title:
        raise ValueError("Tool arg 'title' is required.")
    if not content:
        raise ValueError("Tool arg 'content' is required.")
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Tool arg 'content' exceeds 2MB limit.")

    final_filename = filename or build_filename(title)
    saved_name, output_path = write_pdf(title, content, final_filename)
    return {
        "ok": True,
        "filename": saved_name,
        "path": str(output_path),
        "download_url": f"/downloads/{saved_name}",
    }
