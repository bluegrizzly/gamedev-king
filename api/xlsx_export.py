"""
Export spreadsheet workbooks to the current project's gen folder.
Uses openpyxl to build .xlsx from structured sheet data (title, sheets with rows).
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

from openpyxl import Workbook

from pdf_export import get_gen_output_dir

MAX_FILENAME_LEN = 120
ALLOWED_FILENAME_RE = re.compile(r"[^a-zA-Z0-9\-_. ]+")


def sanitize_xlsx_filename(value: str) -> str:
    cleaned = value.replace("\\", "_").replace("/", "_").strip()
    cleaned = cleaned.replace("..", "_")
    cleaned = ALLOWED_FILENAME_RE.sub("_", cleaned)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = "workbook"
    if not cleaned.lower().endswith(".xlsx"):
        cleaned = f"{cleaned}.xlsx"
    if len(cleaned) > MAX_FILENAME_LEN:
        base = cleaned[: MAX_FILENAME_LEN - 5].rstrip(" ._")
        cleaned = f"{base}.xlsx"
    return cleaned


def build_xlsx_filename(title: str) -> str:
    base = title.strip() or "workbook"
    base = base.lower().replace(" ", "_")
    base = ALLOWED_FILENAME_RE.sub("_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "workbook"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    return sanitize_xlsx_filename(f"{base}_{timestamp}.xlsx")


def ensure_xlsx_output_path(filename: str, project_key: Optional[str] = None) -> Path:
    output_dir = get_gen_output_dir(project_key).resolve()
    safe = sanitize_xlsx_filename(filename)
    candidate = (output_dir / safe).resolve()
    if output_dir not in candidate.parents and candidate != output_dir:
        raise ValueError("Invalid filename path.")
    return candidate


def get_xlsx_download_path(filename: str, project_key: Optional[str] = None) -> Path:
    """Resolve path to an xlsx file in gen folder (for download)."""
    safe = sanitize_xlsx_filename(filename.strip())
    if not safe.lower().endswith(".xlsx"):
        raise ValueError("Filename must be .xlsx")
    output_dir = get_gen_output_dir(project_key).resolve()
    candidate = (output_dir / safe).resolve()
    if output_dir not in candidate.parents and candidate != output_dir:
        raise ValueError("Invalid filename path.")
    return candidate


def _cell_value(v: Any) -> str | int | float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    return str(v).strip()


def write_xlsx(
    title: str,
    sheets: List[dict],
    filename: str,
    project_key: Optional[str] = None,
) -> Tuple[str, Path]:
    """
    Build and save an .xlsx workbook.
    sheets: list of {"name": str, "rows": [[cell, ...], ...]}. Cell can be str, int, float.
    """
    if not sheets:
        raise ValueError("At least one sheet is required.")
    safe_name = sanitize_xlsx_filename(filename)
    output_path = ensure_xlsx_output_path(safe_name, project_key)

    wb = Workbook()
    for idx, sh in enumerate(sheets):
        sheet_name = str(sh.get("name") or f"Sheet{idx + 1}")[:31]
        rows = sh.get("rows") or []
        if idx == 0:
            ws = wb.active
            ws.title = sheet_name
        else:
            ws = wb.create_sheet(title=sheet_name)
        for row in rows:
            if not isinstance(row, (list, tuple)):
                continue
            ws.append([_cell_value(c) for c in row])
    wb.save(str(output_path))
    return safe_name, output_path


def run_export_xlsx_tool(args: dict) -> dict:
    title = str(args.get("title", "")).strip()
    sheets_arg = args.get("sheets")
    filename = str(args.get("filename", "")).strip() if args.get("filename") else ""
    project_key = str(args.get("project_key", "")).strip() or None

    if not title:
        raise ValueError("Tool arg 'title' is required.")
    if not sheets_arg:
        raise ValueError("Tool arg 'sheets' is required.")
    if not isinstance(sheets_arg, list):
        raise ValueError("Tool arg 'sheets' must be a list of { name, rows }.")
    sheets = []
    for sh in sheets_arg:
        if not isinstance(sh, dict):
            continue
        name = str(sh.get("name") or "").strip() or "Sheet"
        rows = sh.get("rows")
        if not isinstance(rows, list):
            rows = []
        sheets.append({"name": name, "rows": rows})
    if not sheets:
        raise ValueError("At least one sheet with 'name' and 'rows' is required.")

    final_filename = filename or build_xlsx_filename(title)
    saved_name, output_path = write_xlsx(title, sheets, final_filename, project_key)
    download_url = f"/downloads/{saved_name}"
    if project_key:
        download_url = f"{download_url}?project_key={project_key}"
    return {
        "ok": True,
        "filename": saved_name,
        "path": str(output_path),
        "download_url": download_url,
    }
