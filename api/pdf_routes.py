from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from image_tool import get_images_dir
from docx_export import build_docx_filename, write_docx
from pdf_export import (
    build_filename,
    ensure_output_path,
    get_doc_output_dir,
    validate_download_filename,
    write_pdf,
)
from rag import resolve_project_path

pdf_router = APIRouter()


class ExportPdfRequest(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    filename: Optional[str] = None
    project_key: Optional[str] = None


class ExportPdfResponse(BaseModel):
    ok: bool
    filename: str
    path: str
    download_url: Optional[str] = None


class ExportDocxRequest(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    filename: Optional[str] = None
    project_key: Optional[str] = None


class ExportDocxResponse(BaseModel):
    ok: bool
    filename: str
    path: str
    download_url: Optional[str] = None


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
        final_name, output_path = write_pdf(title, content, filename, body.project_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[export_pdf] failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to write PDF.") from exc

    download_url = f"/downloads/{final_name}"
    if body.project_key:
        download_url = f"{download_url}?project_key={body.project_key}"
    return ExportPdfResponse(ok=True, filename=final_name, path=str(output_path), download_url=download_url)


@pdf_router.post("/tools/export_docx", response_model=ExportDocxResponse)
def export_docx(body: ExportDocxRequest) -> ExportDocxResponse:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content must be non-empty.")

    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Content exceeds 2MB limit.")

    title = body.title.strip() or "Document"
    try:
        filename = body.filename.strip() if body.filename else build_docx_filename(title)
        if not filename:
            filename = build_docx_filename(title)
        final_name, output_path = write_docx(title, content, filename, body.project_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[export_docx] failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to write DOCX.") from exc

    download_url = f"/downloads/{final_name}"
    if body.project_key:
        download_url = f"{download_url}?project_key={body.project_key}"
    return ExportDocxResponse(ok=True, filename=final_name, path=str(output_path), download_url=download_url)


@pdf_router.get("/downloads/{filename}")
def download_pdf(filename: str, project_key: Optional[str] = None) -> FileResponse:
    try:
        safe_name = validate_download_filename(filename)
        output_path = ensure_output_path(safe_name, project_key)
        if not output_path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        media_type = "application/pdf"
        if safe_name.lower().endswith(".docx"):
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(
            output_path,
            media_type=media_type,
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
def get_tool_paths(project_key: Optional[str] = None) -> dict:
    project_path = resolve_project_path(project_key) or ""
    doc_dir = str(get_doc_output_dir(project_key).resolve())
    image_dir = str(get_images_dir(project_key).resolve())
    return {
        "PROJECT_PATH": project_path,
        "DOC_OUTPUT_DIR": doc_dir,
        "IMAGES_OUTPUT_DIR": image_dir,
    }
