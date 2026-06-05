/** API client for annotation CRUD routes.
 *
 * The ML-facing JSON shape starts here in the browser, travels through Pydantic,
 * and lands in PostgreSQL JSONB without losing its geometry structure.
 */

import type { Annotation, AnnotationCreate } from "../types/annotation";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  /** Fetch JSON responses and surface HTTP failures to React hooks. */
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function listAnnotations(scanId?: string): Promise<Annotation[]> {
  /** Load annotations globally or for a selected scan. */
  const query = scanId ? `?scan_id=${scanId}` : "";
  return request<Annotation[]>(`/annotations${query}`);
}

export async function createAnnotation(payload: AnnotationCreate): Promise<Annotation> {
  /** Persist a new annotation captured from the viewer canvas. */
  return request<Annotation>("/annotations", { method: "POST", body: JSON.stringify(payload) });
}

export async function deleteAnnotation(annotationId: string): Promise<void> {
  /** Delete an annotation and intentionally ignore the empty 204 response body. */
  const response = await fetch(`${API_BASE_URL}/annotations/${annotationId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
}
