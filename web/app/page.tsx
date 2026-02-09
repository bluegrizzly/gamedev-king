"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type Role = "user" | "assistant" | "system";

type ChatMessage = {
  role: Role;
  content: string;
  sourcesUsed?: SourceUsed[];
  images?: MessageImage[];
  imageError?: string;
  pdf?: {
    status: "saving" | "saved" | "error";
    filename?: string;
    downloadUrl?: string;
    path?: string;
    error?: string;
  };
  docx?: {
    status: "saving" | "saved" | "error";
    filename?: string;
    downloadUrl?: string;
    path?: string;
    error?: string;
  };
};

type MessageImage = {
  filename: string;
  url: string;
  path?: string;
};

type SourceUsed = {
  source_id: string;
  title: string;
  chunks?: number[];
  scores?: number[];
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
  {
    id: "technical_director",
    name: "Technical Director",
    role: "Tech & Architecture",
    image: buildAvatar("TD", "#10b981"),
  },
];
const API_BASE = "http://localhost:8000";

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
  const abortRef = useRef<AbortController | null>(null);
  const historySaveTimers = useRef<Record<string, number>>({});
  const [autoScroll, setAutoScroll] = useState(true);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const messages = historyByAgent[agentId] ?? [];
  const activeAgent = AGENTS.find((agent) => agent.id === agentId) ?? AGENTS[0];

  useEffect(() => {
    const el = transcriptRef.current;
    if (el && autoScroll) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, isStreaming, agentId, autoScroll]);

  useEffect(() => {
    setAutoScroll(true);
  }, [agentId]);

  const updateHistory = (targetAgent: string, updater: (prev: ChatMessage[]) => ChatMessage[]) => {
    setHistoryByAgent((prev) => ({
      ...prev,
      [targetAgent]: updater(prev[targetAgent] ?? []),
    }));
  };

  const loadHistory = async (targetAgent: string) => {
    try {
      const response = await fetch(`${API_BASE}/chat/history/${targetAgent}`);
      if (!response.ok) {
        throw new Error(`History load failed: ${response.status}`);
      }
      const data = (await response.json()) as { messages?: ChatMessage[] };
      const messages = Array.isArray(data.messages) ? data.messages : [];
      updateHistory(targetAgent, () =>
        messages.map((msg) => ({
          role: msg.role,
          content: msg.content,
        })),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
    }
  };

  const saveHistory = async (targetAgent: string, nextMessages: ChatMessage[]) => {
    const payload = {
      messages: nextMessages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      })),
    };
    try {
      const response = await fetch(`${API_BASE}/chat/history/${targetAgent}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(`History save failed: ${response.status}`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
    }
  };

  const scheduleSave = (targetAgent: string, nextMessages: ChatMessage[]) => {
    const existing = historySaveTimers.current[targetAgent];
    if (existing) {
      window.clearTimeout(existing);
    }
    historySaveTimers.current[targetAgent] = window.setTimeout(() => {
      void saveHistory(targetAgent, nextMessages);
    }, 600);
  };

  useEffect(() => {
    void loadHistory(agentId);
  }, [agentId]);

  useEffect(() => {
    if (messages.length > 0) {
      scheduleSave(agentId, messages);
    }
  }, [messages, agentId]);

  const sendMessage = async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    const targetAgent = agentId;
    const userMessage: ChatMessage = { role: "user", content: trimmed };
    const wantsPdf = /\b(pdf)\b/i.test(trimmed) || (/save/i.test(trimmed) && /pdf/i.test(trimmed));
    const wantsDocx =
      /\b(docx|word|google doc|google docs)\b/i.test(trimmed) ||
      (/save/i.test(trimmed) && /(docx|word)/i.test(trimmed));
    const assistantMessage: ChatMessage = {
      role: "assistant",
      content: "",
      pdf: wantsPdf ? { status: "saving" } : undefined,
      docx: wantsDocx ? { status: "saving" } : undefined,
    };

    updateHistory(targetAgent, (prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsStreaming(true);
    setStatus("Thinking...");

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const storedProjectKey = window.localStorage.getItem("activeProjectKey");
      const debugPrompts = window.localStorage.getItem("debugPrompts") === "true";
      const payload: Record<string, unknown> = {
        agent: targetAgent,
        message: trimmed,
        rag: {
          scope: "hybrid",
          project_key: storedProjectKey || undefined,
        },
        debug_prompts: debugPrompts || undefined,
      };
      const response = await fetch("http://localhost:8000/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
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
            } else if (evt.event === "image_generated") {
              try {
                const payload = JSON.parse(evt.data) as {
                  images?: MessageImage[];
                  error?: string;
                };
                updateHistory(targetAgent, (prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  if (last && last.role === "assistant") {
                    if (payload.error) {
                      next[next.length - 1] = { ...last, imageError: payload.error };
                    } else if (payload.images && payload.images.length > 0) {
                      const existing = last.images ?? [];
                      const merged = [
                        ...existing,
                        ...payload.images.filter(
                          (img) => !existing.some((existingImg) => existingImg.filename === img.filename),
                        ),
                      ];
                      next[next.length - 1] = { ...last, images: merged };
                    }
                  }
                  return next;
                });
              } catch {
                // Ignore malformed payloads.
              }
            } else if (evt.event === "image_updated") {
              try {
                const payload = JSON.parse(evt.data) as {
                  result?: MessageImage;
                  error?: string;
                };
                updateHistory(targetAgent, (prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  if (last && last.role === "assistant") {
                    if (payload.error) {
                      next[next.length - 1] = { ...last, imageError: payload.error };
                    } else if (payload.result) {
                      const existing = last.images ?? [];
                      const merged = existing.some((img) => img.filename === payload.result?.filename)
                        ? existing
                        : [...existing, payload.result];
                      next[next.length - 1] = { ...last, images: merged };
                    }
                  }
                  return next;
                });
              } catch {
                // Ignore malformed payloads.
              }
            } else if (evt.event === "pdf_saved") {
              try {
                const payload = JSON.parse(evt.data) as {
                  filename?: string;
                  download_url?: string;
                  path?: string;
                  error?: string;
                };
                updateHistory(targetAgent, (prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  if (last && last.role === "assistant" && last.pdf) {
                    if (payload.error && last.pdf.status === "saving") {
                      next[next.length - 1] = {
                        ...last,
                        pdf: {
                          status: "error",
                          error: payload.error,
                        },
                      };
                    } else if (payload.filename && last.pdf.status !== "saved") {
                      const rawUrl = payload.download_url;
                      const downloadUrl = rawUrl
                        ? rawUrl.startsWith("http")
                          ? rawUrl
                          : `${API_BASE}${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`
                        : `${API_BASE}/downloads/${payload.filename}`;
                      next[next.length - 1] = {
                        ...last,
                        pdf: {
                          status: "saved",
                          filename: payload.filename,
                          downloadUrl,
                          path: payload.path,
                        },
                      };
                    }
                  }
                  return next;
                });
              } catch {
                // Ignore malformed payloads.
              }
            } else if (evt.event === "sources") {
              try {
                const parsed = JSON.parse(evt.data) as SourceUsed[];
                if (Array.isArray(parsed)) {
                  updateHistory(targetAgent, (prev) => {
                    const next = [...prev];
                    const last = next[next.length - 1];
                    if (last && last.role === "assistant") {
                      next[next.length - 1] = {
                        ...last,
                        sourcesUsed: parsed,
                      };
                    }
                    return next;
                  });
                }
              } catch {
                // Ignore malformed sources payload.
              }
            } else if (evt.event === "error") {
              setStatus(`Error: ${evt.data}`);
            } else if (evt.event === "docx_saved") {
              try {
                const payload = JSON.parse(evt.data) as {
                  filename?: string;
                  download_url?: string;
                  path?: string;
                  error?: string;
                };
                updateHistory(targetAgent, (prev) => {
                  const next = [...prev];
                  const last = next[next.length - 1];
                  if (last && last.role === "assistant" && last.docx) {
                    if (payload.error && last.docx.status === "saving") {
                      next[next.length - 1] = {
                        ...last,
                        docx: {
                          status: "error",
                          error: payload.error,
                        },
                      };
                    } else if (payload.filename && last.docx.status !== "saved") {
                      const rawUrl = payload.download_url;
                      const downloadUrl = rawUrl
                        ? rawUrl.startsWith("http")
                          ? rawUrl
                          : `${API_BASE}${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`
                        : `${API_BASE}/downloads/${payload.filename}`;
                      next[next.length - 1] = {
                        ...last,
                        docx: {
                          status: "saved",
                          filename: payload.filename,
                          downloadUrl,
                          path: payload.path,
                        },
                      };
                    }
                  }
                  return next;
                });
              } catch {
                // Ignore malformed payloads.
              }
            } else if (evt.event === "done") {
              done = true;
              break;
            }
          }
        }
      }
      updateHistory(targetAgent, (prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant" && last.pdf?.status === "saving") {
          next[next.length - 1] = {
            ...last,
            pdf: {
              status: "error",
              error: "PDF export did not complete.",
            },
          };
        }
        if (last && last.role === "assistant" && last.docx?.status === "saving") {
          next[next.length - 1] = {
            ...last,
            docx: {
              status: "error",
              error: "DOCX export did not complete.",
            },
          };
        }
        return next;
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      if (message !== "The user aborted a request.") {
        setStatus(`Error: ${message}`);
      }
    } finally {
      setIsStreaming(false);
      setStatus((prev) => (prev?.startsWith("Error") ? prev : null));
      abortRef.current = null;
    }
  };

  const sendMessageWithText = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    setInput(trimmed);
    await sendMessage();
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setStatus(null);
  };

  const startEdit = (idx: number, text: string) => {
    if (isStreaming) {
      stopStreaming();
    }
    setEditingIndex(idx);
    setEditingText(text);
  };

  const cancelEdit = () => {
    setEditingIndex(null);
    setEditingText("");
  };

  const resubmitEdit = async () => {
    if (editingIndex === null) return;
    const trimmed = editingText.trim();
    if (!trimmed) {
      setStatus("Error: Message cannot be empty.");
      return;
    }
    const targetAgent = agentId;
    updateHistory(targetAgent, (prev) => {
      const next = prev.slice(0, editingIndex + 1);
      const updated = next[editingIndex];
      next[editingIndex] = { ...updated, content: trimmed };
      next.push({ role: "assistant", content: "" });
      return next;
    });
    cancelEdit();
    await sendMessageWithText(trimmed);
  };

  const clearContext = async () => {
    setStatus("Clearing context...");
    try {
      const response = await fetch(`${API_BASE}/chat/history/${agentId}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`Clear failed: ${response.status}`);
      }
      updateHistory(agentId, () => []);
      setStatus("Context cleared.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
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
        <div className="chat-top">
          <div className="chat-header">Streaming Chat</div>
          <Link className="admin-link" href="/admin">
            Admin
          </Link>
        </div>
        <div className="chat-main">
          <div className="chat-left">
            <div
              className="chat-transcript"
              ref={transcriptRef}
              onScroll={() => {
                const el = transcriptRef.current;
                if (!el) return;
                const threshold = 32;
                const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - threshold;
                setAutoScroll(atBottom);
              }}
            >
              {messages.length === 0 && (
                <div className="message">
                  <div className="role">system</div>
                  <div className="bubble">Start a conversation.</div>
                </div>
              )}
              {messages.map((msg, idx) => (
                <div className="message" key={idx}>
                  <div className="role">{getRoleLabel(msg.role)}</div>
                  <div className="bubble">
                    {editingIndex === idx && msg.role === "user" ? (
                      <div className="edit-block">
                        <textarea
                          value={editingText}
                          onChange={(e) => setEditingText(e.target.value)}
                        />
                        <div className="edit-actions">
                          <button type="button" onClick={() => void resubmitEdit()}>
                            Resubmit
                          </button>
                          <button type="button" className="admin-link" onClick={cancelEdit}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="message-content">
                        <div>{msg.content}</div>
                        {msg.role === "user" && (
                          <button
                            type="button"
                            className="admin-link message-edit"
                            onClick={() => startEdit(idx, msg.content)}
                            disabled={isStreaming}
                          >
                            Edit
                          </button>
                        )}
                      </div>
                    )}
                    {msg.role === "assistant" && msg.sourcesUsed && msg.sourcesUsed.length > 0 && (
                      <div className="sources-used">
                        <div className="sources-title">Sources used</div>
                        <div className="sources-list">
                          {msg.sourcesUsed.map((source) => (
                            <div className="sources-item" key={source.source_id}>
                              <div className="sources-name">{source.title}</div>
                              {source.chunks && source.chunks.length > 0 && (
                                <div className="sources-meta">
                                  chunks: {source.chunks.join(", ")}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {msg.role === "assistant" && msg.images && msg.images.length > 0 && (
                      <div className="image-block">
                        <div className="image-title">Images</div>
                        <div className="image-grid">
                          {msg.images.map((img) => {
                            const src = img.url.startsWith("http")
                              ? img.url
                              : `${API_BASE}${img.url.startsWith("/") ? "" : "/"}${img.url}`;
                            return (
                              <div className="image-item" key={img.filename}>
                                <img className="image-preview" src={src} alt={img.filename} />
                                <div className="image-name">{img.filename}</div>
                                {img.path && <div className="image-name">{img.path}</div>}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {msg.role === "assistant" && msg.imageError && (
                      <div className="pdf-status error">Image error: {msg.imageError}</div>
                    )}
                    {msg.role === "assistant" && msg.pdf?.status === "saving" && (
                      <div className="pdf-status saving">Saving PDF...</div>
                    )}
                    {msg.role === "assistant" && msg.pdf?.status === "saved" && (
                      <div className="pdf-status saved">
                        <div>PDF saved: {msg.pdf.filename}</div>
                        {msg.pdf.path && <div>Path: {msg.pdf.path}</div>}
                        <div className="pdf-actions">
                          {msg.pdf.downloadUrl && (
                            <>
                              <a className="pdf-link" href={msg.pdf.downloadUrl}>
                                Download
                              </a>
                              <a
                                className="pdf-link"
                                href={msg.pdf.downloadUrl}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Open
                              </a>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                    {msg.role === "assistant" && msg.pdf?.status === "error" && (
                      <div className="pdf-status error">PDF export failed: {msg.pdf.error}</div>
                    )}
                    {msg.role === "assistant" && msg.docx?.status === "saving" && (
                      <div className="pdf-status saving">Saving DOCX...</div>
                    )}
                    {msg.role === "assistant" && msg.docx?.status === "saved" && (
                      <div className="pdf-status saved">
                        <div>DOCX saved: {msg.docx.filename}</div>
                        {msg.docx.path && <div>Path: {msg.docx.path}</div>}
                        <div className="pdf-actions">
                          {msg.docx.downloadUrl && (
                            <>
                              <a className="pdf-link" href={msg.docx.downloadUrl}>
                                Download
                              </a>
                              <a
                                className="pdf-link"
                                href={msg.docx.downloadUrl}
                                target="_blank"
                                rel="noreferrer"
                              >
                                Open
                              </a>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                    {msg.role === "assistant" && msg.docx?.status === "error" && (
                      <div className="pdf-status error">DOCX export failed: {msg.docx.error}</div>
                    )}
                  </div>
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
              <button className="stop-button" onClick={stopStreaming} disabled={!isStreaming}>
                Stop
              </button>
            </div>
        <div className="status">
          {isStreaming ? (
            <span className="thinking">
              {status || "Thinking"}
              <span className="dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </span>
          ) : (
            status || ""
          )}
        </div>
            <div className="input-row">
              <button type="button" onClick={() => void clearContext()} disabled={isStreaming}>
                Clear Context
              </button>
            </div>
          </div>
          <div className="chat-right">
            <div className="agent-list-title">Agents</div>
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
        </div>
      </div>
    </main>
  );
}
