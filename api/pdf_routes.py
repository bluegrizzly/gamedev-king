import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from image_tool import get_images_dir
from pdf_export import (
    build_filename,
    ensure_output_path,
    get_doc_output_dir,
    validate_download_filename,
    write_pdf,
)

pdf_router = APIRouter()
get_doc_output_dir()


class ExportPdfRequest(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    filename: Optional[str] = None


class ExportPdfResponse(BaseModel):
    ok: bool
    filename: str
    path: str


@pdf_router.post("/tools/export_pdf", response_model=ExportPdfResponse)
def export_pdf(body: ExportPdfRequest) -> ExportPdfResponse:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content must be non-empty.")

    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Content exceeds 2MB limit.")

    title = body.title.strip() or "Document"
    try:
        filename = body.filename.strip() if body.filename else build_filename(title)
        if not filename:
            filename = build_filename(title)
        final_name, output_path = write_pdf(title, content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[export_pdf] failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to write PDF.") from exc

    return ExportPdfResponse(ok=True, filename=final_name, path=str(output_path))


@pdf_router.get("/downloads/{filename}")
def download_pdf(filename: str) -> FileResponse:
    try:
        safe_name = validate_download_filename(filename)
        output_path = ensure_output_path(safe_name)
        if not output_path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename=safe_name,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[download_pdf] failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to read PDF.") from exc


@pdf_router.get("/tools/paths")
def get_tool_paths() -> dict:
    project_dir = os.getenv("GAME_PROJECT_DIR") or ""
    doc_dir = str(get_doc_output_dir().resolve())
    image_dir = str(get_images_dir().resolve())
    return {
        "GAME_PROJECT_DIR": project_dir,
        "DOC_OUTPUT_DIR": doc_dir,
        "IMAGES_OUTPUT_DIR": image_dir,
    }
