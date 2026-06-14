import type { Label, Project, ProjectExportResponse, ProjectPayload } from "../types/project";
import type { Scan } from "../types/scan";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, token: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options?.headers,
    },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function listProjects(token: string): Promise<Project[]> {
  return request<Project[]>("/projects", token);
}

export async function createProject(token: string, payload: ProjectPayload): Promise<Project> {
  return request<Project>("/projects", token, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProject(projectId: string, token: string, payload: Partial<ProjectPayload>): Promise<Project> {
  return request<Project>(`/projects/${projectId}`, token, { method: "PUT", body: JSON.stringify(payload) });
}

export async function listProjectScans(projectId: string, token: string): Promise<Scan[]> {
  return request<Scan[]>(`/projects/${projectId}/scans`, token);
}

export async function listProjectLabels(projectId: string, token: string): Promise<Label[]> {
  return request<Label[]>(`/projects/${projectId}/labels`, token);
}

export async function exportProjectForMl(projectId: string, token: string): Promise<ProjectExportResponse> {
  return request<ProjectExportResponse>(`/projects/${projectId}/export`, token);
}

export async function createProjectLabel(projectId: string, token: string, payload: Pick<Label, "name" | "color" | "description">): Promise<Label> {
  return request<Label>(`/projects/${projectId}/labels`, token, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProjectLabel(labelId: string, token: string, payload: Partial<Pick<Label, "name" | "color" | "description">>): Promise<Label> {
  return request<Label>(`/labels/${labelId}`, token, { method: "PUT", body: JSON.stringify(payload) });
}

export async function deleteProjectLabel(labelId: string, token: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/labels/${labelId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
}
