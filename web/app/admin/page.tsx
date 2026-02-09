"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type SourceItem = {
  id: string;
  title: string;
  created_at: string;
  agent_id?: string | null;
  agent_ids?: string[] | null;
  scope?: "generic" | "project";
  project_key?: string | null;
  source_path?: string | null;
};

type ProjectItem = {
  project_key: string;
  display_name: string;
  project_path: string;
  created_at: string;
  updated_at: string;
};

type ExportPdfResponse = {
  ok: boolean;
  filename: string;
  path: string;
  download_url?: string;
};

type ToolPathsResponse = {
  PROJECT_PATH?: string;
  DOC_OUTPUT_DIR?: string;
  IMAGES_OUTPUT_DIR?: string;
};

const API_BASE = "http://localhost:8000";
const AGENTS = [
  { id: "creative_director", name: "Creative Director" },
  { id: "art_director", name: "Art Director" },
  { id: "technical_director", name: "Technical Director" },
];

export default function AdminPage() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isProjectsLoading, setIsProjectsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [agentIds, setAgentIds] = useState<string[]>(
    AGENTS[0]?.id ? [AGENTS[0].id] : [],
  );
  const [scope, setScope] = useState<"generic" | "project">("generic");
  const [projectKey, setProjectKey] = useState("");
  const [activeProjectKey, setActiveProjectKey] = useState("");
  const [projectStatus, setProjectStatus] = useState<string | null>(null);
  const [newProject, setNewProject] = useState({
    project_key: "",
    display_name: "",
    project_path: "",
  });
  const [editProjectKey, setEditProjectKey] = useState<string | null>(null);
  const [editProject, setEditProject] = useState({
    display_name: "",
    project_path: "",
  });
  const projectPathPickerRef = useRef<HTMLInputElement>(null);
  const editPathPickerRef = useRef<HTMLInputElement>(null);
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
  const [debugPrompts, setDebugPrompts] = useState(false);
  const [imageDefaults, setImageDefaults] = useState({
    num_images: 2,
    width: 720,
    height: 1280,
    style: "high resolution cartoon, movie style",
  });
  const [imageDefaultsStatus, setImageDefaultsStatus] = useState<string | null>(null);
  const [ragTestStatus, setRagTestStatus] = useState<{
    state: "idle" | "success" | "error";
    message?: string;
    currentProject?: string;
    currentAgent?: string;
    currentProjectSources?: SourceItem[];
    otherSources?: SourceItem[];
  }>({ state: "idle" });
  const [showTests, setShowTests] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

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

  const loadProjects = async () => {
    setIsProjectsLoading(true);
    setProjectStatus(null);
    try {
      const response = await fetch(`${API_BASE}/projects`);
      if (!response.ok) {
        throw new Error(`Load failed: ${response.status}`);
      }
      const data = (await response.json()) as ProjectItem[];
      setProjects(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setProjectStatus(`Error: ${message}`);
    } finally {
      setIsProjectsLoading(false);
    }
  };

  const loadImageDefaults = async () => {
    setImageDefaultsStatus(null);
    try {
      const response = await fetch(`${API_BASE}/settings/image_defaults`);
      if (!response.ok) {
        throw new Error(`Load failed: ${response.status}`);
      }
      const data = (await response.json()) as {
        num_images?: number;
        width?: number;
        height?: number;
        style?: string;
      };
      setImageDefaults((prev) => ({
        ...prev,
        ...data,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setImageDefaultsStatus(`Error: ${message}`);
    }
  };

  useEffect(() => {
    const stored = window.localStorage.getItem("activeProjectKey");
    if (stored) {
      setActiveProjectKey(stored);
    }
    const debugStored = window.localStorage.getItem("debugPrompts");
    if (debugStored === "true") {
      setDebugPrompts(true);
    }
    void loadSources();
    void loadProjects();
    void loadImageDefaults();
  }, []);

  useEffect(() => {
    if (projects.length === 0) {
      if (activeProjectKey) {
        setActiveProjectKey("");
        window.localStorage.removeItem("activeProjectKey");
      }
      if (scope === "project") {
        setScope("generic");
      }
      return;
    }
    const exists = projects.some((project) => project.project_key === activeProjectKey);
    if (!exists) {
      const nextKey = projects[0].project_key;
      setActiveProjectKey(nextKey);
      window.localStorage.setItem("activeProjectKey", nextKey);
    }
  }, [projects, activeProjectKey, scope]);

  useEffect(() => {
    if (scope === "project") {
      const fallbackKey = activeProjectKey || projects[0]?.project_key || "";
      setProjectKey((prev) => prev || fallbackKey);
    } else {
      setProjectKey("");
    }
  }, [scope, activeProjectKey, projects]);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setStatus("Error: Please select a PDF or DOCX file.");
      return;
    }
    if (!file.name.toLowerCase().match(/\.(pdf|docx)$/)) {
      setStatus("Error: Only PDF or DOCX files are supported.");
      return;
    }
    if (scope === "project" && !projectKey.trim()) {
      setStatus("Error: Project key is required for project scope.");
      return;
    }

    setIsUploading(true);
    setStatus("Uploading...");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("scope", scope);
      if (title.trim()) {
        formData.append("title", title.trim());
      }
      if (sourcePath.trim()) {
        formData.append("source_path", sourcePath.trim());
      }
      if (scope === "project" && projectKey.trim()) {
        formData.append("project_key", projectKey.trim());
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
      setSourcePath("");
      setScope("generic");
      setProjectKey("");
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

  const handleRefresh = async (item: SourceItem) => {
    if (!item.source_path) return;
    setStatus("Updating source...");
    try {
      const response = await fetch(`${API_BASE}/rag/sources/${item.id}/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const text = await response.text();
      if (!response.ok) {
        let msg = text || `Update failed: ${response.status}`;
        try {
          const j = JSON.parse(text) as { detail?: string };
          if (j.detail) msg = j.detail;
        } catch {
          // use msg as-is
        }
        throw new Error(msg);
      }
      setStatus("Source updated.");
      await loadSources();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setStatus(`Error: ${message}`);
    }
  };

  const handleProjectSave = async () => {
    setProjectStatus(null);
    const projectKeyInput = newProject.project_key.trim();
    if (!projectKeyInput || !newProject.display_name.trim() || !newProject.project_path.trim()) {
      setProjectStatus("Error: All project fields are required.");
      return;
    }
    if (projects.some((project) => project.project_key === projectKeyInput)) {
      setProjectStatus("Error: project_key already exists.");
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_key: projectKeyInput,
          display_name: newProject.display_name.trim(),
          project_path: newProject.project_path.trim(),
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Create failed: ${response.status}`);
      }
      setNewProject({ project_key: "", display_name: "", project_path: "" });
      await loadProjects();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setProjectStatus(`Error: ${message}`);
    }
  };

  const handleProjectEdit = (project: ProjectItem) => {
    setEditProjectKey(project.project_key);
    setEditProject({
      display_name: project.display_name,
      project_path: project.project_path,
    });
  };

  const handleProjectUpdate = async () => {
    if (!editProjectKey) return;
    setProjectStatus(null);
    if (!editProject.display_name.trim() || !editProject.project_path.trim()) {
      setProjectStatus("Error: display_name and project_path are required.");
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/projects/${editProjectKey}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: editProject.display_name.trim(),
          project_path: editProject.project_path.trim(),
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Update failed: ${response.status}`);
      }
      setEditProjectKey(null);
      await loadProjects();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setProjectStatus(`Error: ${message}`);
    }
  };

  const handleProjectDelete = async (project: ProjectItem) => {
    const confirmed = window.confirm(`Delete project "${project.display_name}"?`);
    if (!confirmed) return;
    setProjectStatus(null);
    try {
      const response = await fetch(`${API_BASE}/projects/${project.project_key}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const text = await response.text();
        if (response.status === 409) {
          setProjectStatus("Error: project has sources; delete sources first.");
          return;
        }
        throw new Error(text || `Delete failed: ${response.status}`);
      }
      await loadProjects();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setProjectStatus(`Error: ${message}`);
    }
  };

  const handleActiveProjectChange = (value: string) => {
    setActiveProjectKey(value);
    if (value) {
      window.localStorage.setItem("activeProjectKey", value);
    } else {
      window.localStorage.removeItem("activeProjectKey");
    }
    if (scope === "project") {
      setProjectKey(value);
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
        project_key: activeProjectKey || undefined,
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
      const query = activeProjectKey ? `?project_key=${activeProjectKey}` : "";
      const response = await fetch(`${API_BASE}/tools/paths${query}`);
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

  const toggleDebugPrompts = (checked: boolean) => {
    setDebugPrompts(checked);
    window.localStorage.setItem("debugPrompts", checked ? "true" : "false");
  };

  const runRagSourcesTest = async () => {
    setRagTestStatus({ state: "idle" });
    const selectedAgent = agentIds[0] || AGENTS[0]?.id || "";
    const currentProject = activeProjectKey || "";
    if (!selectedAgent) {
      setRagTestStatus({ state: "error", message: "No agent selected." });
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/rag/sources`);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Load failed: ${response.status}`);
      }
      const data = (await response.json()) as SourceItem[];
      const matchesAgent = (item: SourceItem) =>
        (item.agent_ids && item.agent_ids.includes(selectedAgent)) ||
        item.agent_id === selectedAgent;

      const currentProjectSources = data.filter(
        (item) =>
          matchesAgent(item) &&
          item.scope === "project" &&
          !!currentProject &&
          item.project_key === currentProject,
      );
      const otherSources = data.filter((item) => {
        if (!matchesAgent(item)) return false;
        if (item.scope === "project" && currentProject) {
          return item.project_key !== currentProject;
        }
        return item.scope !== "project";
      });

      setRagTestStatus({
        state: "success",
        currentProject,
        currentAgent: selectedAgent,
        currentProjectSources,
        otherSources,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setRagTestStatus({ state: "error", message });
    }
  };

  const saveImageDefaults = async () => {
    setImageDefaultsStatus("Saving...");
    try {
      const response = await fetch(`${API_BASE}/settings/image_defaults`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          num_images: imageDefaults.num_images,
          width: imageDefaults.width,
          height: imageDefaults.height,
          style: imageDefaults.style,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Save failed: ${response.status}`);
      }
      const data = (await response.json()) as {
        num_images?: number;
        width?: number;
        height?: number;
        style?: string;
      };
      setImageDefaults((prev) => ({
        ...prev,
        ...data,
      }));
      setImageDefaultsStatus("Saved.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setImageDefaultsStatus(`Error: ${message}`);
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
          <button className="admin-link" onClick={() => setShowSettings((prev) => !prev)}>
            Settings
          </button>
        </div>

        <div className="admin-card">
          <div className="admin-card-title">Project Config</div>
          <div className="admin-project-active">
            <label>
              Active Project
              <select
                value={activeProjectKey}
                onChange={(e) => handleActiveProjectChange(e.target.value)}
                disabled={projects.length === 0}
              >
                <option value="">None</option>
                {projects.map((project) => (
                  <option key={project.project_key} value={project.project_key}>
                    {project.display_name}
                  </option>
                ))}
              </select>
            </label>
            {activeProjectKey && (
              <span className="admin-active-badge">
                Active: {projects.find((p) => p.project_key === activeProjectKey)?.display_name}
              </span>
            )}
          </div>
          <div className="admin-project-form">
            <label className="admin-field">
              <span>Project name</span>
              <input
                type="text"
                placeholder="Display name"
                value={newProject.display_name}
                onChange={(e) => setNewProject((prev) => ({ ...prev, display_name: e.target.value }))}
              />
            </label>
            <label className="admin-field">
              <span>Project key</span>
              <input
                type="text"
                placeholder="Project key (e.g. mygame)"
                value={newProject.project_key}
                onChange={(e) => setNewProject((prev) => ({ ...prev, project_key: e.target.value }))}
              />
            </label>
            <label className="admin-field admin-field-path">
              <span>Project root path</span>
              <div className="admin-path-input">
                <input
                  type="text"
                  placeholder="Project path"
                  value={newProject.project_path}
                  onChange={(e) =>
                    setNewProject((prev) => ({ ...prev, project_path: e.target.value }))
                  }
                />
                <button
                  type="button"
                  className="admin-link"
                  onClick={async () => {
                    if ("showDirectoryPicker" in window) {
                      try {
                        // @ts-expect-error - showDirectoryPicker not in TS lib yet.
                        const handle = await window.showDirectoryPicker();
                        if (handle?.name) {
                          setNewProject((prev) => ({ ...prev, project_path: handle.name }));
                          return;
                        }
                      } catch {
                        return;
                      }
                    }
                    projectPathPickerRef.current?.click();
                  }}
                >
                  ...
                </button>
              </div>
              <input
                ref={projectPathPickerRef}
                type="file"
                className="admin-hidden-input"
                webkitdirectory="true"
                directory="true"
                onChange={(e) => {
                  const files = e.target.files;
                  if (!files || files.length === 0) return;
                  const first = files[0];
                  const relative = (first as File).webkitRelativePath || first.name;
                  const rootFolder = relative.split("/")[0] || "";
                  if (rootFolder) {
                    setNewProject((prev) => ({ ...prev, project_path: rootFolder }));
                  }
                  e.currentTarget.value = "";
                }}
              />
            </label>
            <button onClick={() => void handleProjectSave()} disabled={isProjectsLoading}>
              Add Project
            </button>
          </div>
          {projectStatus && <div className="admin-status">{projectStatus}</div>}
          {isProjectsLoading ? (
            <div className="admin-empty">Loading projects...</div>
          ) : projects.length === 0 ? (
            <div className="admin-empty">No projects yet.</div>
          ) : (
            <div className="admin-project-table">
              {projects.map((project) => {
                const isEditing = editProjectKey === project.project_key;
                return (
                  <div className="admin-project-row" key={project.project_key}>
                    <div className="admin-project-main">
                      <div className="admin-project-title">{project.display_name}</div>
                      <div className="admin-project-meta">
                        <span className="admin-project-key">{project.project_key}</span> ·{" "}
                        {project.project_path || "Path not set"}
                        {!project.project_path && (
                          <>
                            {" · "}
                            <span className="admin-path-missing">Path not set</span>
                          </>
                        )}
                      </div>
                    </div>
                    {isEditing ? (
                      <div className="admin-project-edit">
                        <label className="admin-field">
                          <span>Project name</span>
                          <input
                            type="text"
                            value={editProject.display_name}
                            onChange={(e) =>
                              setEditProject((prev) => ({ ...prev, display_name: e.target.value }))
                            }
                          />
                        </label>
                        <label className="admin-field admin-field-path">
                          <span>Project root path</span>
                          <div className="admin-path-input">
                            <input
                              type="text"
                              value={editProject.project_path}
                              onChange={(e) =>
                                setEditProject((prev) => ({
                                  ...prev,
                                  project_path: e.target.value,
                                }))
                              }
                            />
                            <button
                              type="button"
                              className="admin-link"
                              onClick={async () => {
                                if ("showDirectoryPicker" in window) {
                                  try {
                                    // @ts-expect-error - showDirectoryPicker not in TS lib yet.
                                    const handle = await window.showDirectoryPicker();
                                    if (handle?.name) {
                                      setEditProject((prev) => ({ ...prev, project_path: handle.name }));
                                      return;
                                    }
                                  } catch {
                                    return;
                                  }
                                }
                                editPathPickerRef.current?.click();
                              }}
                            >
                              ...
                            </button>
                          </div>
                          <input
                            ref={editPathPickerRef}
                            type="file"
                            className="admin-hidden-input"
                            webkitdirectory="true"
                            directory="true"
                            onChange={(e) => {
                              const files = e.target.files;
                              if (!files || files.length === 0) return;
                              const first = files[0];
                              const relative = (first as File).webkitRelativePath || first.name;
                              const rootFolder = relative.split("/")[0] || "";
                              if (rootFolder) {
                                setEditProject((prev) => ({ ...prev, project_path: rootFolder }));
                              }
                              e.currentTarget.value = "";
                            }}
                          />
                        </label>
                        <button onClick={() => void handleProjectUpdate()}>Save</button>
                        <button
                          className="admin-link"
                          onClick={() => setEditProjectKey(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="admin-project-actions">
                        <button onClick={() => handleProjectEdit(project)}>Edit</button>
                        <button
                          className="admin-delete"
                          onClick={() => void handleProjectDelete(project)}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="admin-card">
          <div className="admin-card-title">Upload PDF</div>
          <div className="admin-form">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file && !title.trim()) {
                  setTitle(file.name);
                }
                if (file) {
                  const project = projects.find((p) => p.project_key === projectKey);
                  const basePath = scope === "project" && project?.project_path?.trim();
                  if (basePath) {
                    const sep = basePath.endsWith("/") || basePath.endsWith("\\") ? "" : "/";
                    setSourcePath(`${basePath}${sep}${file.name}`);
                  } else if (!sourcePath.trim()) {
                    setSourcePath("");
                  }
                }
              }}
            />
            <input
              type="text"
              placeholder="Optional title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as "generic" | "project")}
            >
              <option value="generic">Generic</option>
              <option value="project" disabled={projects.length === 0}>
                Project
              </option>
            </select>
            <select
              value={projectKey}
              onChange={(e) => setProjectKey(e.target.value)}
              disabled={scope !== "project" || projects.length === 0}
            >
              <option value="">Select project</option>
              {projects.map((project) => (
                <option key={project.project_key} value={project.project_key}>
                  {project.display_name}
                </option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Full path on server for Update (e.g. C:\Projects\doc.pdf)"
              value={sourcePath}
              onChange={(e) => setSourcePath(e.target.value)}
              title="Store the full filesystem path so Update can re-index this file. Required for Update button."
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
          {scope === "project" && projects.length === 0 && (
            <div className="admin-status">Add a project first to upload in project scope.</div>
          )}
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
              {(() => {
                const genericSources = sources.filter((item) => item.scope !== "project");
                const projectGroups = sources.reduce<Record<string, SourceItem[]>>(
                  (acc, item) => {
                    if (item.scope === "project") {
                      const key = item.project_key || "unspecified";
                      acc[key] = acc[key] ? [...acc[key], item] : [item];
                    }
                    return acc;
                  },
                  {},
                );

                return (
                  <>
                    {genericSources.length > 0 && (
                      <div className="admin-group">
                        <div className="admin-group-title">Generic</div>
                        {genericSources.map((item) => (
                          <div className="admin-row" key={item.id}>
                            <div className="admin-row-main">
                              <div className="admin-row-title">
                                {item.title}
                                <span className="scope-badge generic">Generic</span>
                              </div>
                              <div className="admin-row-meta">
                                {new Date(item.created_at).toLocaleString()} ·{" "}
                                {item.id.slice(0, 8)}
                                {item.agent_ids && item.agent_ids.length > 0
                                  ? ` · ${item.agent_ids.join(", ")}`
                                  : item.agent_id
                                    ? ` · ${item.agent_id}`
                                    : ""}
                              </div>
                              <div className="admin-row-path">
                                {item.source_path ? (
                                  <span className="admin-source-path" title={item.source_path}>
                                    {item.source_path}
                                  </span>
                                ) : (
                                  <span className="admin-path-missing">Path not set</span>
                                )}
                              </div>
                            </div>
                            <div className="admin-row-actions">
                              <button
                                className="admin-link"
                                onClick={() => void handleRefresh(item)}
                                disabled={!item.source_path}
                                title={
                                  item.source_path
                                    ? "Refresh from source_path"
                                    : "Add source_path to enable update"
                                }
                              >
                                Update
                              </button>
                              <button className="admin-delete" onClick={() => void handleDelete(item)}>
                                Delete
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {Object.keys(projectGroups).map((project) => (
                      <div className="admin-group" key={project}>
                        <div className="admin-group-title">
                          Project · <span className="admin-project-key">{project}</span>
                        </div>
                        {projectGroups[project].map((item) => (
                          <div className="admin-row" key={item.id}>
                            <div className="admin-row-main">
                              <div className="admin-row-title">
                                {item.title}
                                <span className="scope-badge project">Project</span>
                              </div>
                              <div className="admin-row-meta">
                                {new Date(item.created_at).toLocaleString()} ·{" "}
                                {item.id.slice(0, 8)}
                                {item.agent_ids && item.agent_ids.length > 0
                                  ? ` · ${item.agent_ids.join(", ")}`
                                  : item.agent_id
                                    ? ` · ${item.agent_id}`
                                    : ""}
                              </div>
                              <div className="admin-row-path">
                                {item.source_path ? (
                                  <span className="admin-source-path" title={item.source_path}>
                                    {item.source_path}
                                  </span>
                                ) : (
                                  <span className="admin-path-missing">Path not set</span>
                                )}
                              </div>
                            </div>
                            <div className="admin-row-actions">
                              <button
                                className="admin-link"
                                onClick={() => void handleRefresh(item)}
                                disabled={!item.source_path}
                                title={
                                  item.source_path
                                    ? "Refresh from source_path"
                                    : "Add source_path to enable update"
                                }
                              >
                                Update
                              </button>
                              <button className="admin-delete" onClick={() => void handleDelete(item)}>
                                Delete
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ))}
                  </>
                );
              })()}
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
              <button onClick={() => void runRagSourcesTest()}>Run RAG Sources Test</button>
            </div>
            <label className="admin-test-toggle">
              <input
                type="checkbox"
                checked={debugPrompts}
                onChange={(e) => toggleDebugPrompts(e.target.checked)}
              />
              Debug Prompts
            </label>
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
                  PROJECT_PATH: {pathsStatus.data?.PROJECT_PATH || "-"}
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
            {ragTestStatus.state === "success" && (
              <div className="admin-test-status">
                <div className="admin-test-meta">
                  Agent: {ragTestStatus.currentAgent || "-"}
                </div>
                <div className="admin-test-meta">
                  Project: {ragTestStatus.currentProject || "(none)"}
                </div>
                <div className="admin-test-meta">
                  Current project docs:{" "}
                  {ragTestStatus.currentProjectSources?.length ?? 0}
                </div>
                {(ragTestStatus.currentProjectSources ?? []).map((item) => (
                  <div key={item.id} className="admin-test-meta">
                    - {item.title}
                  </div>
                ))}
                <div className="admin-test-meta">
                  Other docs for agent: {ragTestStatus.otherSources?.length ?? 0}
                </div>
                {(ragTestStatus.otherSources ?? []).map((item) => (
                  <div key={item.id} className="admin-test-meta">
                    - {item.title}
                  </div>
                ))}
              </div>
            )}
            {ragTestStatus.state === "error" && (
              <div className="admin-test-status error">Error: {ragTestStatus.message}</div>
            )}
          </div>
        )}

        {showSettings && (
          <div className="admin-card admin-test-card">
            <div className="admin-card-title">Settings</div>
            <div className="admin-test-block">
              <div className="admin-test-title">Image Defaults</div>
              <div className="admin-test-grid">
                <label className="admin-field">
                  <span>Variations</span>
                  <input
                    type="number"
                    min={1}
                    max={4}
                    value={imageDefaults.num_images}
                    onChange={(e) =>
                      setImageDefaults((prev) => ({
                        ...prev,
                        num_images: Number(e.target.value),
                      }))
                    }
                  />
                </label>
                <label className="admin-field">
                  <span>Width</span>
                  <input
                    type="number"
                    value={imageDefaults.width}
                    onChange={(e) =>
                      setImageDefaults((prev) => ({
                        ...prev,
                        width: Number(e.target.value),
                      }))
                    }
                  />
                </label>
                <label className="admin-field">
                  <span>Height</span>
                  <input
                    type="number"
                    value={imageDefaults.height}
                    onChange={(e) =>
                      setImageDefaults((prev) => ({
                        ...prev,
                        height: Number(e.target.value),
                      }))
                    }
                  />
                </label>
                <label className="admin-field admin-field-path">
                  <span>Style</span>
                  <input
                    type="text"
                    value={imageDefaults.style}
                    onChange={(e) =>
                      setImageDefaults((prev) => ({
                        ...prev,
                        style: e.target.value,
                      }))
                    }
                  />
                </label>
                <button onClick={() => void saveImageDefaults()}>Save Defaults</button>
              </div>
              {imageDefaultsStatus && <div className="admin-status">{imageDefaultsStatus}</div>}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
