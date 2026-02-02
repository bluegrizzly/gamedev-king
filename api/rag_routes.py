from fastapi import APIRouter, File, Form, UploadFile

from rag import RetrieveRequest, RetrieveResponse, list_sources, retrieve, upload_pdf

rag_router = APIRouter()


@rag_router.post("/rag/upload_pdf")
def upload_pdf_route(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    agent_ids: list[str] | None = Form(None),
) -> dict:
    return upload_pdf(file=file, title=title, agent_ids=agent_ids)


@rag_router.post("/rag/retrieve", response_model=RetrieveResponse)
def retrieve_route(body: RetrieveRequest) -> RetrieveResponse:
    return retrieve(body)


@rag_router.get("/rag/sources")
def list_sources_route() -> list[dict]:
    return list_sources()
