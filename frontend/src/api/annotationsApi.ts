/** API client for annotation CRUD routes.
 *
 * The ML-facing JSON shape starts here in the browser, travels through Pydantic,
 * and lands in PostgreSQL JSONB without losing its geometry structure.
 */

import type { Annotation, AnnotationCreate, AnnotationHistory, AnnotationUpdate, ReviewStatus, SegmentationMask, SegmentationMaskImage } from "../types/annotation";

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

export async function uploadSegmentationMask(annotationId: string, sliceIndex: number, mask: Blob, token: string): Promise<SegmentationMask> {
  /** Upload a PNG mask through multipart form data so bytes stay out of JSON. */
  const formData = new FormData();
  formData.append("slice_index", String(sliceIndex));
  formData.append("file", mask, `mask-${sliceIndex}.png`);
  const response = await fetch(`${API_BASE_URL}/annotations/${annotationId}/mask`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<SegmentationMask>;
}

export async function getSegmentationMask(annotationId: string, sliceIndex: number, token: string): Promise<SegmentationMaskImage | null> {
  /** Return null when a valid segmentation annotation has no saved mask yet. */
  const response = await fetch(`${API_BASE_URL}/annotations/${annotationId}/mask/${sliceIndex}`, { headers: { Authorization: `Bearer ${token}` } });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<SegmentationMaskImage>;
}

export async function deleteSegmentationMask(annotationId: string, sliceIndex: number, token: string): Promise<void> {
  /** Delete the saved mask bytes while keeping the annotation row. */
  const response = await fetch(`${API_BASE_URL}/annotations/${annotationId}/mask/${sliceIndex}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok && response.status !== 404) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
}

export async function updateAnnotation(annotationId: string, payload: AnnotationUpdate, token: string): Promise<Annotation> {
  /** Persist geometry or metadata edits for one annotation. */
  return request<Annotation>(`/annotations/${annotationId}`, token, { method: "PUT", body: JSON.stringify(payload) });
}

export async function listAnnotationHistory(annotationId: string, token: string): Promise<AnnotationHistory[]> {
  /** Load audit entries for one annotation. */
  return request<AnnotationHistory[]>(`/annotations/${annotationId}/history`, token);
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
