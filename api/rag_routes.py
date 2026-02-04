from fastapi import APIRouter, File, Form, UploadFile
from uuid import UUID

from rag import (
    RetrieveRequest,
    RetrieveResponse,
    delete_source,
    list_sources,
    refresh_source,
    retrieve,
    upload_pdf,
)

rag_router = APIRouter()


@rag_router.post("/rag/upload_pdf")
def upload_pdf_route(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    agent_ids: list[str] | None = Form(None),
    scope: str = Form("generic"),
    project_key: str | None = Form(None),
    source_path: str | None = Form(None),
) -> dict:
    return upload_pdf(
        file=file,
        title=title,
        agent_ids=agent_ids,
        scope=scope,
        project_key=project_key,
        source_path=source_path,
    )


@rag_router.post("/rag/retrieve", response_model=RetrieveResponse)
def retrieve_route(body: RetrieveRequest) -> RetrieveResponse:
    return retrieve(body)


@rag_router.get("/rag/sources")
def list_sources_route() -> list[dict]:
    return list_sources()


@rag_router.delete("/rag/sources/{source_id}")
def delete_source_route(source_id: UUID) -> dict:
    return delete_source(source_id)


@rag_router.post("/rag/sources/{source_id}/refresh")
def refresh_source_route(source_id: UUID) -> dict:
    return refresh_source(source_id)
