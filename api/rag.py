import io
import os
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from openai import OpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader
from supabase import Client, create_client

rag_router = APIRouter()

EMBEDDING_MODEL = "text-embedding-3-small"
MAX_TOP_K = 20
DEFAULT_TOP_K = 6


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K)
    source_id: Optional[UUID] = None
    agent_id: Optional[str] = None
    agent_ids: Optional[List[str]] = None


class RetrieveResult(BaseModel):
    source_id: UUID
    chunk_index: int
    content: str
    score: float
    title: str


class RetrieveResponse(BaseModel):
    query: str
    results: List[RetrieveResult]


def retrieve_chunks(
    query: str,
    top_k: int,
    source_id: Optional[UUID],
    agent_ids: Optional[List[str]],
) -> List[RetrieveResult]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY.")

    openai_client = OpenAI(api_key=api_key)
    embedding_response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[query],
    )
    query_embedding = embedding_response.data[0].embedding

    supabase = get_supabase_client()
    rpc_payload = {
        "query_embedding": query_embedding,
        "match_count": top_k,
        "source_filter": str(source_id) if source_id else None,
        "agent_filter": agent_ids,
    }
    result = supabase.rpc("match_chunks", rpc_payload).execute()
    rows = result.data or []
    return [
        RetrieveResult(
            source_id=UUID(row["source_id"]),
            chunk_index=row["chunk_index"],
            content=row["content"],
            score=float(row["distance"]),
            title=row["title"],
        )
        for row in rows
    ]


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    cleaned = text.replace("\x00", " ").strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    step = chunk_size - overlap
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        extracted = page.extract_text() or ""
        if extracted.strip():
            pages.append(extracted)
    return "\n".join(pages).strip()


def get_supabase_client() -> Client:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(supabase_url, supabase_key)


@rag_router.post("/rag/upload_pdf")
def upload_pdf(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    agent_ids: Optional[List[str]] = Form(None),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    if file.content_type not in (None, "", "application/pdf"):
        raise HTTPException(status_code=400, detail="Invalid content type.")

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty upload.")

    text = extract_pdf_text(file_bytes)
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text extracted from PDF.")

    chunks = chunk_text(text, chunk_size=1200, overlap=200)
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks produced.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY.")

    openai_client = OpenAI(api_key=api_key)
    try:
        embedding_response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=chunks,
        )
        embeddings = [item.embedding for item in embedding_response.data]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}") from exc

    if len(embeddings) != len(chunks):
        raise HTTPException(status_code=502, detail="Embedding count mismatch.")

    source_title = title.strip() if title and title.strip() else file.filename
    cleaned_agents = [agent.strip() for agent in (agent_ids or []) if agent.strip()]
    source_agents = cleaned_agents if cleaned_agents else None

    try:
        supabase = get_supabase_client()
        source_payload = {"title": source_title, "agent_ids": source_agents}
        source_result = supabase.table("sources").insert(source_payload).execute()
        if not source_result.data:
            raise RuntimeError("No source row returned.")
        source_id = source_result.data[0]["id"]

        chunk_rows = [
            {
                "source_id": source_id,
                "chunk_index": idx,
                "content": chunk,
                "embedding": embeddings[idx],
            }
            for idx, chunk in enumerate(chunks)
        ]
        supabase.table("chunks").insert(chunk_rows).execute()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Supabase insert failed: {exc}") from exc

    return {"source_id": source_id, "chunks_indexed": len(chunks)}


@rag_router.post("/rag/retrieve", response_model=RetrieveResponse)
def retrieve(body: RetrieveRequest) -> RetrieveResponse:
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must be non-empty.")

    try:
        agent_filter = body.agent_ids
        if not agent_filter and body.agent_id:
            agent_filter = [body.agent_id]
        results = retrieve_chunks(query, body.top_k, body.source_id, agent_filter)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {exc}") from exc
    return RetrieveResponse(query=query, results=results)


@rag_router.get("/rag/sources")
def list_sources() -> list[dict]:
    try:
        supabase = get_supabase_client()
        result = (
            supabase.table("sources")
            .select("id,title,created_at,agent_id,agent_ids")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load sources: {exc}") from exc
