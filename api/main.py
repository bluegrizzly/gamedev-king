import json
import os
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

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


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    message: Optional[str] = None
    agent: Optional[str] = "creative_director"
    model: Optional[str] = "gpt-5-mini"


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


def sse_event(event: str, data: str) -> bytes:
    lines = data.split("\n")
    payload = "".join([f"event: {event}\n"] + [f"data: {line}\n" for line in lines] + ["\n"])
    return payload.encode("utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


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
            persona_prompt = ""
            if persona_text:
                persona_prompt = (
                    "*** PERSONA ***\n"
                    "The agent represent this persona:\n"
                    f"{persona_text}"
                )

            use_history = body.message is not None and body.message.strip() != ""
            if use_history:
                history = AGENT_HISTORIES.setdefault(agent_id, [])
                history.append(ChatMessage(role="user", content=body.message.strip()))
                base_messages = [m.model_dump() for m in history]
            else:
                history = None
                base_messages = [m.model_dump() for m in body.messages]
            if persona_prompt:
                input_messages = [{"role": "system", "content": persona_prompt}, *base_messages]
            else:
                input_messages = base_messages

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

            yield sse_event("done", "")
        except Exception as exc:
            yield sse_event("error", str(exc))
            yield sse_event("done", "")

    return StreamingResponse(generator(), media_type="text/event-stream")

