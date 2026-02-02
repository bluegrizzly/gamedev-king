"use client";

import { useEffect, useRef, useState } from "react";

type Role = "user" | "assistant" | "system";

type ChatMessage = {
  role: Role;
  content: string;
};

type SseEvent = {
  event: string;
  data: string;
};

function parseSseLines(buffer: string): { events: SseEvent[]; rest: string } {
  const lines = buffer.split("\n");
  const rest = lines.pop() ?? "";

  const events: SseEvent[] = [];
  let eventName = "message";
  let dataLines: string[] = [];

  const flush = () => {
    if (dataLines.length === 0) {
      eventName = "message";
      return;
    }
    events.push({ event: eventName, data: dataLines.join("\n") });
    eventName = "message";
    dataLines = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, "");
    if (line === "") {
      flush();
      continue;
    }
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      const value = line.slice(5).replace(/^ /, "");
      dataLines.push(value);
    }
  }

  return { events, rest };
}

export default function HomePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = transcriptRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, isStreaming]);

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    const userMessage: ChatMessage = { role: "user", content: trimmed };
    const assistantMessage: ChatMessage = { role: "assistant", content: "" };
    const outgoing = [...messages, userMessage];

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsStreaming(true);
    setStatus("Streaming...");

    try {
      const response = await fetch("http://localhost:8000/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: outgoing }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let done = false;

      while (!done) {
        const { value, done: streamDone } = await reader.read();
        done = streamDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const parsed = parseSseLines(buffer);
          buffer = parsed.rest;

          for (const evt of parsed.events) {
            if (evt.event === "token") {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last && last.role === "assistant") {
                  next[next.length - 1] = {
                    ...last,
                    content: last.content + evt.data,
                  };
                }
                return next;
              });
            } else if (evt.event === "error") {
              setStatus(`Error: ${evt.data}`);
            } else if (evt.event === "done") {
              done = true;
              break;
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
    } finally {
      setIsStreaming(false);
      setStatus((prev) => (prev?.startsWith("Error") ? prev : null));
    }
  };

  const handleKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void sendMessage();
    }
  };

  return (
    <main>
      <div className="chat-shell">
        <div className="chat-header">Streaming Chat</div>
        <div className="chat-transcript" ref={transcriptRef}>
          {messages.length === 0 && (
            <div className="message">
              <div className="role">system</div>
              <div className="bubble">Start a conversation.</div>
            </div>
          )}
          {messages.map((msg, idx) => (
            <div className="message" key={idx}>
              <div className="role">{msg.role}</div>
              <div className="bubble">{msg.content}</div>
            </div>
          ))}
        </div>
        <div className="input-row">
          <textarea
            placeholder="Type your message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button onClick={() => void sendMessage()} disabled={isStreaming}>
            Send
          </button>
        </div>
        <div className="status">
          {status ? status : isStreaming ? "Assistant is typing..." : ""}
        </div>
      </div>
    </main>
  );
}
