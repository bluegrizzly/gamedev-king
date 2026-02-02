import json
import os
from pathlib import Path
from typing import Any, AsyncGenerator, List, Optional
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from llm_tools import get_tools
from pdf_export import run_export_pdf_tool
from pdf_routes import pdf_router
from rag import retrieve_chunks
from rag_routes import rag_router

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
app.include_router(pdf_router)


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
            tool_instruction = (
                "If the user explicitly requests saving or exporting to PDF, produce the full document first, "
                "then call export_pdf with the final content and a sensible title. "
                "If the user did NOT request saving, do NOT call the tool."
            )

            use_history = body.message is not None and body.message.strip() != ""
            if use_history:
                history = AGENT_HISTORIES.setdefault(agent_id, [])
                history.append(ChatMessage(role="user", content=body.message.strip()))
                base_messages = [m.model_dump() for m in history]
            else:
                history = None
                base_messages = [m.model_dump() for m in body.messages]
            system_messages: list[dict] = [
                {"role": "system", "content": rag_system_prompt},
                {"role": "system", "content": tool_instruction},
            ]
            if persona_prompt:
                system_messages.append({"role": "system", "content": persona_prompt})
            if context_block:
                system_messages.append({"role": "system", "content": context_block})
            input_messages: list[dict[str, Any]] = [*system_messages, *base_messages]

            max_tool_iterations = 2
            tool_iterations = 0
            pending_messages = list(input_messages)

            while tool_iterations < max_tool_iterations:
                assistant_chunks: list[str] = []
                tool_calls: list[dict[str, Any]] = []

                stream = client.chat.completions.create(
                    model=body.model or "gpt-5-mini",
                    messages=pending_messages,
                    tools=get_tools(),
                    tool_choice="auto",
                    stream=True,
                )
                tool_call_map: dict[int, dict[str, Any]] = {}
                for chunk in stream:
                    choice = chunk.choices[0]
                    delta = choice.delta
                    delta_text = getattr(delta, "content", None)
                    if delta_text:
                        if history is not None:
                            assistant_chunks.append(delta_text)
                        yield sse_event("token", delta_text)
                    delta_tool_calls = getattr(delta, "tool_calls", None)
                    if delta_tool_calls:
                        for tool_call in delta_tool_calls:
                            index = tool_call.index
                            entry = tool_call_map.setdefault(
                                index,
                                {
                                    "id": tool_call.id,
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                },
                            )
                            if tool_call.id and not entry.get("id"):
                                entry["id"] = tool_call.id
                            if tool_call.function and tool_call.function.name:
                                entry["function"]["name"] = tool_call.function.name
                            if tool_call.function and tool_call.function.arguments:
                                entry["function"]["arguments"] += tool_call.function.arguments
                tool_calls = [tool_call_map[i] for i in sorted(tool_call_map.keys())]

                assistant_text = "".join(assistant_chunks).strip()
                if history is not None and assistant_text:
                    history.append(ChatMessage(role="assistant", content=assistant_text))

                if not tool_calls:
                    break

                tool_iterations += 1
                # Only allow export_pdf tool calls.
                allowed_tool_calls = [call for call in tool_calls if call.get("function", {}).get("name") == "export_pdf"]
                if not allowed_tool_calls:
                    first_call = tool_calls[0]
                    tool_id = first_call.get("id") or "unknown_tool"
                    tool_name = first_call.get("function", {}).get("name", "unknown_tool")
                    error_payload = {"error": f"Tool '{tool_name}' is not allowed."}
                    yield sse_event("error", error_payload["error"])
                    pending_messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_text,
                            "tool_calls": [
                                {
                                    "id": tool_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": first_call.get("function", {}).get("arguments", "{}"),
                                    },
                                }
                            ],
                        }
                    )
                    pending_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": json.dumps(error_payload),
                        }
                    )
                    continue

                for call in allowed_tool_calls[:1]:
                    tool_id = call.get("id") or "export_pdf"
                    raw_args = call.get("function", {}).get("arguments", "{}")
                    try:
                        parsed_args = json.loads(raw_args) if raw_args else {}
                        result = run_export_pdf_tool(parsed_args)
                        yield sse_event("pdf_saved", json.dumps(result))
                        tool_content = json.dumps(result)
                    except Exception as exc:
                        error_payload = {"error": str(exc)}
                        yield sse_event("pdf_saved", json.dumps(error_payload))
                        tool_content = json.dumps(error_payload)

                    pending_messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_text,
                            "tool_calls": [
                                {
                                    "id": tool_id,
                                    "type": "function",
                                    "function": {
                                        "name": "export_pdf",
                                        "arguments": raw_args,
                                    },
                                }
                            ],
                        }
                    )
                    pending_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": "export_pdf",
                            "content": tool_content,
                        }
                    )
                continue

            if sources_payload:
                yield sse_event("sources", json.dumps(sources_payload))
            yield sse_event("done", "")
        except Exception as exc:
            yield sse_event("error", str(exc))
            yield sse_event("done", "")

    return StreamingResponse(generator(), media_type="text/event-stream")

