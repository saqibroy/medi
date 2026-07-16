import type { Label, Project, ProjectExportResponse, ProjectPayload } from "../types/project";
import type { ProjectReviewStats, Scan } from "../types/scan";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, csrfToken: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
      ...options?.headers,
    },
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function listProjects(csrfToken: string): Promise<Project[]> {
  return request<Project[]>("/projects", csrfToken);
}

export async function createProject(csrfToken: string, payload: ProjectPayload): Promise<Project> {
  return request<Project>("/projects", csrfToken, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProject(projectId: string, csrfToken: string, payload: Partial<ProjectPayload>): Promise<Project> {
  return request<Project>(`/projects/${projectId}`, csrfToken, { method: "PUT", body: JSON.stringify(payload) });
}

export async function listProjectScans(projectId: string, csrfToken: string): Promise<Scan[]> {
  return request<Scan[]>(`/projects/${projectId}/scans`, csrfToken);
}

export async function listProjectLabels(projectId: string, csrfToken: string): Promise<Label[]> {
  return request<Label[]>(`/projects/${projectId}/labels`, csrfToken);
}

export async function exportProjectForMl(projectId: string, csrfToken: string): Promise<ProjectExportResponse> {
  return request<ProjectExportResponse>(`/projects/${projectId}/export`, csrfToken);
}

export async function getProjectStats(projectId: string, csrfToken: string): Promise<ProjectReviewStats> {
  return request<ProjectReviewStats>(`/projects/${projectId}/stats`, csrfToken);
}

export async function exportProjectAsCoco(projectId: string, csrfToken: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/projects/${projectId}/export/coco`, csrfToken);
}

export async function exportProjectAsCsv(projectId: string, csrfToken: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/projects/${projectId}/export/csv`, csrfToken);
}

export async function exportProjectAsYolo(projectId: string, csrfToken: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/projects/${projectId}/export/yolo`, csrfToken);
}

export async function exportProjectAsSegmentation(projectId: string, csrfToken: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/projects/${projectId}/export/segmentation`, csrfToken);
}

export async function createProjectLabel(projectId: string, csrfToken: string, payload: Pick<Label, "name" | "color" | "description">): Promise<Label> {
  return request<Label>(`/projects/${projectId}/labels`, csrfToken, { method: "POST", body: JSON.stringify(payload) });
}

export async function updateProjectLabel(labelId: string, csrfToken: string, payload: Partial<Pick<Label, "name" | "color" | "description">>): Promise<Label> {
  return request<Label>(`/labels/${labelId}`, csrfToken, { method: "PUT", body: JSON.stringify(payload) });
}

export async function deleteProjectLabel(labelId: string, csrfToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/labels/${labelId}`, {
    method: "DELETE",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
}
