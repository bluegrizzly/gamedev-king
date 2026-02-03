"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type SourceItem = {
  id: string;
  title: string;
  created_at: string;
  agent_id?: string | null;
  agent_ids?: string[] | null;
};

type ExportPdfResponse = {
  ok: boolean;
  filename: string;
  path: string;
  download_url?: string;
};

type ToolPathsResponse = {
  GAME_PROJECT_DIR?: string;
  DOC_OUTPUT_DIR?: string;
  IMAGES_OUTPUT_DIR?: string;
};

const API_BASE = "http://localhost:8000";
const AGENTS = [
  { id: "creative_director", name: "Creative Director" },
  { id: "art_director", name: "Art Director" },
];

export default function AdminPage() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [agentIds, setAgentIds] = useState<string[]>(
    AGENTS[0]?.id ? [AGENTS[0].id] : [],
  );
  const fileRef = useRef<HTMLInputElement>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testStatus, setTestStatus] = useState<{
    state: "idle" | "success" | "error";
    message?: string;
    filename?: string;
    downloadUrl?: string;
  }>({ state: "idle" });
  const [pathsStatus, setPathsStatus] = useState<{
    state: "idle" | "success" | "error";
    message?: string;
    data?: ToolPathsResponse;
  }>({ state: "idle" });
  const [showTests, setShowTests] = useState(false);

  const loadSources = async () => {
    setIsLoading(true);
    setStatus(null);
    try {
      const response = await fetch(`${API_BASE}/rag/sources`);
      if (!response.ok) {
        throw new Error(`Load failed: ${response.status}`);
      }
      const data = (await response.json()) as SourceItem[];
      setSources(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadSources();
  }, []);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setStatus("Error: Please select a PDF file.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setStatus("Error: Only PDF files are supported.");
      return;
    }

    setIsUploading(true);
    setStatus("Uploading...");
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (title.trim()) {
        formData.append("title", title.trim());
      }
      if (agentIds.length > 0) {
        agentIds.forEach((agentId) => formData.append("agent_ids", agentId));
      }

      const response = await fetch(`${API_BASE}/rag/upload_pdf`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Upload failed: ${response.status}`);
      }

      setStatus("Upload successful.");
      setTitle("");
      if (fileRef.current) {
        fileRef.current.value = "";
      }
      await loadSources();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (item: SourceItem) => {
    const confirmed = window.confirm(`Delete "${item.title}"? This cannot be undone.`);
    if (!confirmed) return;

    setStatus("Deleting...");
    try {
      const response = await fetch(`${API_BASE}/rag/sources/${item.id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Delete failed: ${response.status}`);
      }
      setStatus("Deleted.");
      await loadSources();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
    }
  };

  const runPdfExportTest = async () => {
    setIsTesting(true);
    setTestStatus({ state: "idle" });
    try {
      const timestamp = new Date()
        .toISOString()
        .replace(/[-:]/g, "")
        .replace(/\..+/, "");
      const payload = {
        title: "PDF Export Test",
        content: "Hello from the PDF export test.",
        filename: `pdf_export_test_${timestamp}.pdf`,
      };

      const response = await fetch(`${API_BASE}/tools/export_pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
      }

      let data: ExportPdfResponse;
      try {
        data = (await response.json()) as ExportPdfResponse;
      } catch {
        throw new Error("Failed to parse server response.");
      }

      const filename = data.filename;
      const downloadUrl =
        data.download_url && data.download_url.startsWith("http")
          ? data.download_url
          : data.download_url
            ? `${API_BASE}${data.download_url.startsWith("/") ? "" : "/"}${data.download_url}`
            : `${API_BASE}/downloads/${filename}`;

      setTestStatus({
        state: "success",
        message: "PDF export test succeeded.",
        filename,
        downloadUrl,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setTestStatus({ state: "error", message });
    } finally {
      setIsTesting(false);
    }
  };

  const runPathsTest = async () => {
    setPathsStatus({ state: "idle" });
    try {
      const response = await fetch(`${API_BASE}/tools/paths`);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
      }
      const data = (await response.json()) as ToolPathsResponse;
      setPathsStatus({ state: "success", data });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setPathsStatus({ state: "error", message });
    }
  };

  return (
    <main>
      <div className="admin-shell">
        <div className="admin-header">
          <div className="admin-header-left">
            <Link className="admin-link" href="/">
              Back
            </Link>
            <div className="admin-title">Admin: RAG Sources</div>
          </div>
          <button className="admin-link" onClick={() => setShowTests((prev) => !prev)}>
            Tests
          </button>
        </div>

        <div className="admin-card">
          <div className="admin-card-title">Upload PDF</div>
          <div className="admin-form">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file && !title.trim()) {
                  setTitle(file.name);
                }
              }}
            />
            <input
              type="text"
              placeholder="Optional title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <div className="admin-agent-select">
              {AGENTS.map((agent) => (
                <label key={agent.id} className="admin-agent-option">
                  <input
                    type="checkbox"
                    value={agent.id}
                    checked={agentIds.includes(agent.id)}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setAgentIds((prev) =>
                        checked ? [...prev, agent.id] : prev.filter((id) => id !== agent.id),
                      );
                    }}
                  />
                  {agent.name}
                </label>
              ))}
            </div>
            <button onClick={() => void handleUpload()} disabled={isUploading}>
              {isUploading ? "Uploading..." : "Upload"}
            </button>
          </div>
          {status && <div className="admin-status">{status}</div>}
        </div>

        <div className="admin-card">
          <div className="admin-card-title">Sources</div>
          {isLoading ? (
            <div className="admin-empty">Loading sources...</div>
          ) : sources.length === 0 ? (
            <div className="admin-empty">No sources yet.</div>
          ) : (
            <div className="admin-list">
              {sources.map((item) => (
                <div className="admin-row" key={item.id}>
                  <div className="admin-row-main">
                    <div className="admin-row-title">{item.title}</div>
                    <div className="admin-row-meta">
                      {new Date(item.created_at).toLocaleString()} · {item.id.slice(0, 8)}
                      {item.agent_ids && item.agent_ids.length > 0
                        ? ` · ${item.agent_ids.join(", ")}`
                        : item.agent_id
                          ? ` · ${item.agent_id}`
                          : ""}
                    </div>
                  </div>
                  <button className="admin-delete" onClick={() => void handleDelete(item)}>
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {showTests && (
          <div className="admin-card admin-test-card">
            <div className="admin-card-title">Tests</div>
            <div className="admin-test-row">
              <button onClick={() => void runPdfExportTest()} disabled={isTesting}>
                {isTesting ? "Running..." : "Run PDF Export Test"}
              </button>
              <button onClick={() => void runPathsTest()}>Show Paths</button>
            </div>
            {testStatus.state === "success" && (
              <div className="admin-test-status success">
                <div>{testStatus.message}</div>
                <div className="admin-test-meta">
                  File: {testStatus.filename}
                  {testStatus.downloadUrl && (
                    <>
                      {" · "}
                      <a className="admin-test-link" href={testStatus.downloadUrl}>
                        Download
                      </a>
                      {" · "}
                      <a
                        className="admin-test-link"
                        href={testStatus.downloadUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open PDF
                      </a>
                    </>
                  )}
                </div>
              </div>
            )}
            {testStatus.state === "error" && (
              <div className="admin-test-status error">Error: {testStatus.message}</div>
            )}
            {pathsStatus.state === "success" && (
              <div className="admin-test-status">
                <div className="admin-test-meta">
                  GAME_PROJECT_DIR: {pathsStatus.data?.GAME_PROJECT_DIR || "-"}
                </div>
                <div className="admin-test-meta">
                  DOC_OUTPUT_DIR: {pathsStatus.data?.DOC_OUTPUT_DIR || "-"}
                </div>
                <div className="admin-test-meta">
                  IMAGES_OUTPUT_DIR: {pathsStatus.data?.IMAGES_OUTPUT_DIR || "-"}
                </div>
              </div>
            )}
            {pathsStatus.state === "error" && (
              <div className="admin-test-status error">Error: {pathsStatus.message}</div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
