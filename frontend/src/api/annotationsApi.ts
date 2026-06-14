/** API client for annotation CRUD routes.
 *
 * The ML-facing JSON shape starts here in the browser, travels through Pydantic,
 * and lands in PostgreSQL JSONB without losing its geometry structure.
 */

import type { Annotation, AnnotationCreate, ReviewStatus } from "../types/annotation";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, token: string, options?: RequestInit): Promise<T> {
  /** Fetch JSON responses and surface HTTP failures to React hooks. */
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function listAnnotations(token: string, scanId?: string): Promise<Annotation[]> {
  /** Load annotations globally or for a selected scan. */
  const query = scanId ? `?scan_id=${scanId}` : "";
  return request<Annotation[]>(`/annotations${query}`, token);
}

export async function createAnnotation(payload: AnnotationCreate, token: string): Promise<Annotation> {
  /** Persist a new annotation captured from the viewer canvas. */
  return request<Annotation>("/annotations", token, { method: "POST", body: JSON.stringify(payload) });
}

export async function reviewAnnotation(annotationId: string, reviewer: string, status: ReviewStatus, token: string, notes?: string | null): Promise<Annotation> {
  /** PATCH is used because QA changes only review fields, not the whole annotation. */
  return request<Annotation>(`/annotations/${annotationId}/review`, token, {
    method: "PATCH",
    body: JSON.stringify({ reviewer, review_status: status, notes: notes ?? null }),
  });
}

export async function deleteAnnotation(annotationId: string, token: string): Promise<void> {
  /** Delete an annotation and intentionally ignore the empty 204 response body. */
  const response = await fetch(`${API_BASE_URL}/annotations/${annotationId}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
}
