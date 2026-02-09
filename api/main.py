import json
import os
import re
import traceback
from datetime import datetime, timezone
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, List, Literal, Optional
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from llm_tools import get_tools
from image_router import image_router
from image_tool import (
    run_convert_image_tool,
    run_crop_image_tool,
    run_generate_image_tool,
    run_resize_image_tool,
)
from pdf_export import run_export_pdf_tool
from docx_export import run_export_docx_tool
from pdf_routes import pdf_router
from rag import (
    get_default_project_key_value,
    get_supabase_client,
    get_project_display_name,
    retrieve_chunks,
    resolve_scope_and_project_key,
)
from projects import projects_router
from rag_routes import rag_router
from local_settings import DEFAULT_IMAGE_SETTINGS, load_image_defaults, save_image_defaults

_env_file = ".env" if sys.platform == "win32" else "env"
load_dotenv(Path(__file__).parent / _env_file)

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
    scope: Literal["generic", "project", "hybrid"] = "hybrid"
    project_key: Optional[str] = None


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    message: Optional[str] = None
    agent: Optional[str] = "creative_director"
    model: Optional[str] = "gpt-5-mini"
    rag: Optional[RagOptions] = None
    debug_prompts: Optional[bool] = False


AGENT_PERSONA_FILES = {
    "creative_director": Path(__file__).parent / "personas" / "creative_director.json",
    "art_director": Path(__file__).parent / "personas" / "art_director.json",
    "technical_director": Path(__file__).parent / "personas" / "technical_director.json",
}
AGENT_HISTORIES: dict[str, List[ChatMessage]] = {}
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_DATA_DIR = PROJECT_ROOT / ".local_data"
DEBUG_PROMPTS_PATH = LOCAL_DATA_DIR / "debug_prompts.txt"
HISTORY_PREFIX = "feed_"
MAX_HISTORY_ITEMS = 200

# Keywords that suggest the user might want export or image tools (for tool_choice optimization).
_TOOL_TRIGGER_PHRASES = (
    "export", "save to pdf", "save as pdf", "save to docx", "save as docx",
    "export to pdf", "export to docx", "export as pdf", "export as docx",
    "google doc", "google docs",
    "generate image", "generate a image", "create image", "create a image",
    "draw ", "draw a", "picture of", "image of", "generate a picture",
    "resize image", "crop image", "convert image", "resize the image",
    "make a pdf", "make a docx", "write to pdf", "write to docx",
)


def _user_might_need_tools(user_message: str) -> bool:
    """Return True if the user message suggests they may want export or image tools."""
    if not user_message or not user_message.strip():
        return False
    lower = user_message.strip().lower()
    return any(phrase in lower for phrase in _TOOL_TRIGGER_PHRASES)


def _choose_tool_name(user_message: str) -> Optional[str]:
    if not user_message:
        return None
    lower = user_message.strip().lower()
    if "resize" in lower:
        return "resize_image"
    if "crop" in lower:
        return "crop_image"
    if "convert" in lower:
        return "convert_image"
    if "docx" in lower or "word" in lower:
        return "export_docx"
    if "pdf" in lower:
        return "export_pdf"
    if "image" in lower or "draw" in lower or "picture" in lower:
        return "generate_image"
    return None


def _extract_tool_args(text: str, tool_name: str) -> Optional[dict]:
    if not text:
        return None
    pattern = rf"{tool_name}\s*\(\s*(\{{.*\}})\s*\)"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None
    raw = match.group(1)
    try:
        return json.loads(raw)
    except Exception:
        return None


class HistoryMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str


class HistoryPayload(BaseModel):
    messages: List[HistoryMessage] = Field(default_factory=list)


class ImageDefaults(BaseModel):
    num_images: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    style: Optional[str] = None


def normalize_agent_id(agent_id: Optional[str]) -> str:
    if not agent_id:
        return "creative_director"
    cleaned = agent_id.strip().lower().replace("-", "_").replace(" ", "_")
    return cleaned if cleaned in AGENT_PERSONA_FILES else "creative_director"


def get_history_path(agent_id: str) -> Path:
    safe_agent = normalize_agent_id(agent_id)
    filename = f"{HISTORY_PREFIX}{safe_agent}.json"
    return LOCAL_DATA_DIR / "history" / filename


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


def log_debug_error(title: str, details: str) -> None:
    try:
        separator = "=" * 80
        timestamp = datetime.now().isoformat()
        DEBUG_PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_PROMPTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write("\n".join([separator, f"Timestamp: {timestamp}", title, details]) + "\n")
    except Exception:
        pass


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/chat/history/{agent_id}")
def get_chat_history(agent_id: str) -> dict:
    path = get_history_path(agent_id)
    if not path.exists():
        return {"messages": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            return {"messages": []}
        return {"messages": messages[:MAX_HISTORY_ITEMS]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read history: {exc}") from exc


@app.post("/chat/history/{agent_id}")
def save_chat_history(agent_id: str, body: HistoryPayload) -> dict:
    path = get_history_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    messages = body.messages[-MAX_HISTORY_ITEMS:]
    payload = {"messages": [msg.model_dump() for msg in messages]}
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": True, "count": len(messages)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write history: {exc}") from exc


@app.delete("/chat/history/{agent_id}")
def clear_chat_history(agent_id: str) -> dict:
    path = get_history_path(agent_id)
    try:
        if path.exists():
            path.unlink()
        return {"deleted": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete history: {exc}") from exc


@app.get("/settings/image_defaults")
def get_image_defaults() -> dict:
    return load_image_defaults()


@app.put("/settings/image_defaults")
def update_image_defaults(body: ImageDefaults) -> dict:
    payload = body.model_dump(exclude_none=True)
    if "num_images" in payload:
        payload["num_images"] = max(1, min(int(payload["num_images"]), 4))
    if "width" in payload:
        payload["width"] = int(payload["width"])
    if "height" in payload:
        payload["height"] = int(payload["height"])
    if "style" in payload:
        payload["style"] = str(payload["style"]).strip()
    return save_image_defaults(payload)

app.include_router(rag_router)
app.include_router(projects_router)
app.include_router(pdf_router)
app.include_router(image_router)


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

            current_project_name = "Unspecified"
            project_key_for_prompt = ""
            if body.rag and body.rag.project_key:
                supabase = get_supabase_client()
                resolved_name = get_project_display_name(supabase, body.rag.project_key)
                if resolved_name:
                    current_project_name = resolved_name
                project_key_for_prompt = body.rag.project_key
            persona_prompt = (
                persona_prompt
                + "\n*** PROJECT ***\nThe current game project is called "
                + current_project_name
                + ("." if not project_key_for_prompt else f". And the game project key is {project_key_for_prompt}.")
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
                    try:
                        rag_scope, rag_project_key = resolve_scope_and_project_key(
                            rag_options.scope,
                            rag_options.project_key,
                        )
                    except Exception:
                        rag_scope, rag_project_key = "generic", None
                    tool_project_key = rag_project_key or get_default_project_key_value()
                    retrieved = retrieve_chunks(
                        rag_query,
                        rag_options.top_k,
                        rag_options.source_id,
                        agent_filter,
                        rag_scope,
                        rag_project_key or None,
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
                "If the user explicitly requests saving or exporting to PDF or DOCX, "
                "produce the full document first with clear Markdown headings (e.g. '#', '##') and short sections, "
                "then call export_pdf or export_docx with the final content and a sensible title. "
                "If the user did NOT request saving, do NOT call the tool. "
                "If the user asks to generate an image, call generate_image. "
                "If the user asks to resize, crop, or convert an existing image, call the matching tool."
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
            if body.debug_prompts:
                separator = "=" * 80
                timestamp = datetime.now().isoformat()
                user_text = body.message.strip() if body.message else (last_user.content if last_user else "")
                log_lines = [
                    separator,
                    f"Timestamp: {timestamp}",
                    f"User: {user_text}",
                    "Prompt:",
                    *[msg.get("content", "") for msg in system_messages],
                ]
                DEBUG_PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
                with DEBUG_PROMPTS_PATH.open("a", encoding="utf-8") as handle:
                    handle.write("\n".join(log_lines) + "\n")

            max_tool_iterations = 3
            tool_iterations = 0
            pending_messages = list(input_messages)
            user_text_for_tools = body.message.strip() if body.message else (last_user.content.strip() if last_user else "")
            use_tools_this_turn = _user_might_need_tools(user_text_for_tools)
            forced_tool_name = _choose_tool_name(user_text_for_tools)

            while tool_iterations < max_tool_iterations:
                assistant_chunks: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                include_tools = use_tools_this_turn or tool_iterations > 0 or forced_tool_name is not None

                create_kwargs: dict[str, Any] = {
                    "model": body.model or "gpt-5-mini",
                    "messages": pending_messages,
                    "stream": True,
                }
                if include_tools:
                    create_kwargs["tools"] = get_tools()
                    if forced_tool_name:
                        create_kwargs["tool_choice"] = {"type": "function", "function": {"name": forced_tool_name}}
                    else:
                        create_kwargs["tool_choice"] = "required" if use_tools_this_turn else "auto"

                stream = client.chat.completions.create(**create_kwargs)
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
                    if include_tools and forced_tool_name:
                        extracted = _extract_tool_args(assistant_text, forced_tool_name)
                        if extracted:
                            try:
                                if tool_project_key and not extracted.get("project_key"):
                                    extracted["project_key"] = tool_project_key
                                if forced_tool_name == "generate_image":
                                    result = run_generate_image_tool(extracted)
                                    yield sse_event("image_generated", json.dumps(result))
                                elif forced_tool_name == "export_docx":
                                    result = run_export_docx_tool(extracted)
                                    yield sse_event("docx_saved", json.dumps(result))
                                elif forced_tool_name == "export_pdf":
                                    result = run_export_pdf_tool(extracted)
                                    yield sse_event("pdf_saved", json.dumps(result))
                            except Exception as exc:
                                log_debug_error(
                                    f"[tool_error] {forced_tool_name}",
                                    "\n".join(
                                        [
                                            f"Args: {json.dumps(extracted, ensure_ascii=False)}",
                                            f"Error: {exc}",
                                            traceback.format_exc(),
                                        ]
                                    ),
                                )
                                yield sse_event("error", str(exc))
                        break
                    break

                tool_iterations += 1
                allowed_tools = {
                    "export_pdf": "pdf_saved",
                    "export_docx": "docx_saved",
                    "generate_image": "image_generated",
                    "resize_image": "image_updated",
                    "crop_image": "image_updated",
                    "convert_image": "image_updated",
                }
                allowed_tool_calls = [
                    call for call in tool_calls if call.get("function", {}).get("name") in allowed_tools
                ]
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
                    tool_name = call.get("function", {}).get("name", "")
                    tool_id = call.get("id") or tool_name or "tool"
                    raw_args = call.get("function", {}).get("arguments", "{}")
                    try:
                        parsed_args = json.loads(raw_args) if raw_args else {}
                        if tool_project_key and not parsed_args.get("project_key"):
                            parsed_args["project_key"] = tool_project_key
                        if tool_name == "export_pdf":
                            result = run_export_pdf_tool(parsed_args)
                            event_name = "pdf_saved"
                            event_payload = result
                        elif tool_name == "export_docx":
                            result = run_export_docx_tool(parsed_args)
                            event_name = "docx_saved"
                            event_payload = result
                        elif tool_name == "generate_image":
                            result = run_generate_image_tool(parsed_args)
                            event_name = "image_generated"
                            event_payload = result
                        elif tool_name == "resize_image":
                            result = run_resize_image_tool(parsed_args)
                            event_name = "image_updated"
                            event_payload = {"operation": "resize", "result": result}
                        elif tool_name == "crop_image":
                            result = run_crop_image_tool(parsed_args)
                            event_name = "image_updated"
                            event_payload = {"operation": "crop", "result": result}
                        elif tool_name == "convert_image":
                            result = run_convert_image_tool(parsed_args)
                            event_name = "image_updated"
                            event_payload = {"operation": "convert", "result": result}
                        else:
                            raise ValueError("Unsupported tool.")
                        yield sse_event(event_name, json.dumps(event_payload))
                        tool_content = json.dumps(result)
                    except Exception as exc:
                        log_debug_error(
                            f"[tool_error] {tool_name or 'unknown'}",
                            "\n".join(
                                [
                                    f"Args: {raw_args}",
                                    f"Error: {exc}",
                                    traceback.format_exc(),
                                ]
                            ),
                        )
                        error_payload = {"error": str(exc)}
                        event_name = allowed_tools.get(tool_name, "error")
                        if event_name == "image_updated":
                            error_payload = {"operation": tool_name.replace("_image", ""), "error": str(exc)}
                        yield sse_event(event_name, json.dumps(error_payload))
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
                                        "name": tool_name or "tool",
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
                            "name": tool_name or "tool",
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

