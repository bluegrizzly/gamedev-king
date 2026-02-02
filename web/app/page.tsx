"use client";

import { useEffect, useRef, useState } from "react";

type Role = "user" | "assistant" | "system";

type ChatMessage = {
  role: Role;
  content: string;
};

type AgentInfo = {
  id: string;
  name: string;
  role: string;
  image: string;
};

type SseEvent = {
  event: string;
  data: string;
};

const buildAvatar = (label: string, color: string) => {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">
      <rect width="64" height="64" rx="12" fill="${color}" />
      <text x="50%" y="50%" text-anchor="middle" dy=".32em"
        font-family="Arial, sans-serif" font-size="24" fill="#ffffff">${label}</text>
    </svg>
  `;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

const AGENTS: AgentInfo[] = [
  {
    id: "creative_director",
    name: "Creative Director",
    role: "Vision",
    image: buildAvatar("CD", "#3b82f6"),
  },
  {
    id: "art_director",
    name: "Art Director",
    role: "Visuals",
    image: buildAvatar("AD", "#f97316"),
  },
];

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
  const [agentId, setAgentId] = useState<string>(AGENTS[0]?.id ?? "creative_director");
  const [historyByAgent, setHistoryByAgent] = useState<Record<string, ChatMessage[]>>(
    () => Object.fromEntries(AGENTS.map((agent) => [agent.id, []])),
  );
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const messages = historyByAgent[agentId] ?? [];
  const activeAgent = AGENTS.find((agent) => agent.id === agentId) ?? AGENTS[0];

  useEffect(() => {
    const el = transcriptRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, isStreaming, agentId]);

  const updateHistory = (targetAgent: string, updater: (prev: ChatMessage[]) => ChatMessage[]) => {
    setHistoryByAgent((prev) => ({
      ...prev,
      [targetAgent]: updater(prev[targetAgent] ?? []),
    }));
  };

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    const targetAgent = agentId;
    const userMessage: ChatMessage = { role: "user", content: trimmed };
    const assistantMessage: ChatMessage = { role: "assistant", content: "" };

    updateHistory(targetAgent, (prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsStreaming(true);
    setStatus("Streaming...");

    try {
      const response = await fetch("http://localhost:8000/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: targetAgent, message: trimmed }),
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
              updateHistory(targetAgent, (prev) => {
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

  const getRoleLabel = (role: Role) => {
    if (role === "assistant") {
      return activeAgent?.name ?? "Assistant";
    }
    return role;
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
              <div className="role">{getRoleLabel(msg.role)}</div>
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
        <div className="agent-list">
          {AGENTS.map((agent) => (
            <button
              key={agent.id}
              type="button"
              className={`agent-card ${agentId === agent.id ? "active" : ""}`}
              onClick={() => setAgentId(agent.id)}
              disabled={isStreaming && agentId === agent.id}
            >
              <img className="agent-avatar" src={agent.image} alt={agent.name} />
              <div className="agent-meta">
                <div className="agent-name">{agent.name}</div>
                <div className="agent-role">{agent.role}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
