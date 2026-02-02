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
    messages: List[ChatMessage]
    model: Optional[str] = "gpt-5-mini"

PERSONA_PATH = Path(__file__).parent / "personas" / "creative_director.json"


def load_persona_text() -> str:
    try:
        raw = PERSONA_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return ""


PERSONA_TEXT = load_persona_text()


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
            persona_prompt = ""
            if PERSONA_TEXT:
                persona_prompt = (
                    "*** PERSONA ***\n"
                    "The agent represent this persona:\n"
                    f"{PERSONA_TEXT}"
                )

            base_messages = [m.model_dump() for m in body.messages]
            if persona_prompt:
                input_messages = [{"role": "system", "content": persona_prompt}, *base_messages]
            else:
                input_messages = base_messages

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
                        yield sse_event("token", delta)

            yield sse_event("done", "")
        except Exception as exc:
            yield sse_event("error", str(exc))
            yield sse_event("done", "")

    return StreamingResponse(generator(), media_type="text/event-stream")

