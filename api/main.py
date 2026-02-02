import json
import os
from pathlib import Path
from typing import AsyncGenerator, List, Optional
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from rag import rag_router, retrieve_chunks

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str


class RagOptions(BaseModel):
    top_k: int = Field(default=6, ge=1, le=20)
    source_id: Optional[UUID] = None
    agent_id: Optional[str] = None
    agent_ids: Optional[List[str]] = None


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    message: Optional[str] = None
    agent: Optional[str] = "creative_director"
    model: Optional[str] = "gpt-5-mini"
    rag: Optional[RagOptions] = None


AGENT_PERSONA_FILES = {
    "creative_director": Path(__file__).parent / "personas" / "creative_director.json",
    "art_director": Path(__file__).parent / "personas" / "art_director.json",
}
AGENT_HISTORIES: dict[str, List[ChatMessage]] = {}


def normalize_agent_id(agent_id: Optional[str]) -> str:
    if not agent_id:
        return "creative_director"
    cleaned = agent_id.strip().lower().replace("-", "_").replace(" ", "_")
    return cleaned if cleaned in AGENT_PERSONA_FILES else "creative_director"


def load_persona_text(agent_id: str) -> str:
    path = AGENT_PERSONA_FILES.get(agent_id)
    if not path:
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return ""


def load_persona_description_prompt(agent_id: str) -> str:
    path = AGENT_PERSONA_FILES.get(agent_id)
    if not path:
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return str(data.get("description_prompt", "")).strip()
    except Exception:
        return ""


def sse_event(event: str, data: str) -> bytes:
    lines = data.split("\n")
    payload = "".join([f"event: {event}\n"] + [f"data: {line}\n" for line in lines] + ["\n"])
    return payload.encode("utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True}

app.include_router(rag_router)


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        async def missing_key() -> AsyncGenerator[bytes, None]:
            yield sse_event("error", "Missing OPENAI_API_KEY")
            yield sse_event("done", "")
        return StreamingResponse(missing_key(), media_type="text/event-stream")

    client = OpenAI(api_key=api_key)

    async def generator() -> AsyncGenerator[bytes, None]:
        try:
            used_responses = False
            agent_id = normalize_agent_id(body.agent)
            persona_text = load_persona_text(agent_id)
            persona_description = load_persona_description_prompt(agent_id)
            persona_prompt = ""
            if persona_text:
                persona_prompt = (
                    "*** PERSONA ***\n"
                    "The agent represent this persona:\n"
                    f"{persona_text}"
                )

            rag_options = body.rag or RagOptions()
            retrieved = []
            sources_payload = []
            if body.messages:
                last_user = next((m for m in reversed(body.messages) if m.role == "user"), None)
            else:
                last_user = None
            rag_query = body.message.strip() if body.message else (last_user.content if last_user else "")

            if rag_query:
                try:
                    # RAG retrieval: pull top chunks for the latest user query.
                    agent_filter = rag_options.agent_ids
                    if not agent_filter:
                        agent_filter = [rag_options.agent_id or agent_id]
                    retrieved = retrieve_chunks(
                        rag_query,
                        rag_options.top_k,
                        rag_options.source_id,
                        agent_filter,
                    )
                    if retrieved:
                        grouped: dict[str, dict] = {}
                        for item in retrieved:
                            key = str(item.source_id)
                            entry = grouped.setdefault(
                                key,
                                {
                                    "source_id": key,
                                    "title": item.title,
                                    "chunks": [],
                                    "scores": [],
                                },
                            )
                            entry["chunks"].append(item.chunk_index)
                            entry["scores"].append(item.score)
                        sources_payload = list(grouped.values())
                except Exception as exc:
                    print(f"[rag] retrieval failed: {exc}")
                    retrieved = []
                    sources_payload = []

            context_block = ""
            if retrieved:
                formatted_chunks = [
                    f"[Source: {item.title} | chunk {item.chunk_index}] {item.content}"
                    for item in retrieved
                ]
                context_block = "CONTEXT:\n" + "\n\n".join(formatted_chunks)

            persona_prefix = persona_description or "You are a game development expert."
            rag_system_prompt = (
                f"{persona_prefix} "
                "Use provided context. If context is insufficient, say what is missing instead of inventing. "
                "When using context, prefer citing it. If the answer is not supported by context, "
                "say so and propose what to add to the KB."
            )

            use_history = body.message is not None and body.message.strip() != ""
            if use_history:
                history = AGENT_HISTORIES.setdefault(agent_id, [])
                history.append(ChatMessage(role="user", content=body.message.strip()))
                base_messages = [m.model_dump() for m in history]
            else:
                history = None
                base_messages = [m.model_dump() for m in body.messages]
            system_messages: list[dict] = [{"role": "system", "content": rag_system_prompt}]
            if persona_prompt:
                system_messages.append({"role": "system", "content": persona_prompt})
            if context_block:
                system_messages.append({"role": "system", "content": context_block})
            input_messages = [*system_messages, *base_messages]

            assistant_chunks: list[str] = []
            if hasattr(client, "responses"):
                try:
                    stream = client.responses.create(
                        model=body.model or "gpt-5-mini",
                        input=input_messages,
                        stream=True,
                    )
                    used_responses = True
                    for event in stream:
                        event_type = getattr(event, "type", "")
                        if event_type == "response.output_text.delta":
                            delta = getattr(event, "delta", "")
                            if delta:
                                if history is not None:
                                    assistant_chunks.append(delta)
                                yield sse_event("token", delta)
                        elif event_type == "response.completed":
                            break
                except Exception:
                    used_responses = False

            if not used_responses:
                stream = client.chat.completions.create(
                    model=body.model or "gpt-5-mini",
                    messages=input_messages,
                    stream=True,
                )
                for chunk in stream:
                    choice = chunk.choices[0]
                    delta = getattr(choice.delta, "content", None)
                    if delta:
                        if history is not None:
                            assistant_chunks.append(delta)
                        yield sse_event("token", delta)

            if history is not None:
                assistant_text = "".join(assistant_chunks).strip()
                if assistant_text:
                    history.append(ChatMessage(role="assistant", content=assistant_text))

            if sources_payload:
                yield sse_event("sources", json.dumps(sources_payload))
            yield sse_event("done", "")
        except Exception as exc:
            yield sse_event("error", str(exc))
            yield sse_event("done", "")

    return StreamingResponse(generator(), media_type="text/event-stream")

