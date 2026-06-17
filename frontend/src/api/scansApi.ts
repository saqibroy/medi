/** API client for scan-related backend routes.
 *
 * Centralizing fetch calls keeps components focused on UI and makes the network
 * contract easy to replace with generated clients or test doubles later.
 */

import type { ReviewStats, Scan, ScanCreate, ScanMetadata, ScanUpload, SliceImage } from "../types/scan";
import type { ExportResponse } from "../types/annotation";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function responseError(response: Response): Promise<Error> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return new Error(body.detail);
    }
    if (Array.isArray(body.detail)) {
      return new Error(body.detail.map((item) => (typeof item?.msg === "string" ? item.msg : "Validation error")).join(", "));
    }
  } catch {
    // Fall back to the HTTP status below when the body is not JSON.
  }
  return new Error(`API request failed: ${response.status} ${response.statusText}`);
}

async function request<T>(path: string, token: string, options?: RequestInit): Promise<T> {
  /** Fetch JSON and convert HTTP errors into useful exceptions for hooks. */
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw await responseError(response);
  }
  return response.json() as Promise<T>;
}

export async function listScans(token: string): Promise<Scan[]> {
  /** Load all scans for the left panel. */
  return request<Scan[]>("/scans", token);
}

export async function getScan(scanId: string, token: string): Promise<Scan> {
  /** Load one scan's metadata for viewer configuration. */
  return request<Scan>(`/scans/${scanId}`, token);
}

export async function getScanSlice(scanId: string, sliceIndex: number, token: string): Promise<SliceImage> {
  /** Load one base64 PNG slice for the current viewport. */
  return request<SliceImage>(`/scans/${scanId}/slice/${sliceIndex}`, token);
}

export async function getScanMetadata(scanId: string, token: string): Promise<ScanMetadata> {
  /** Load parsed imaging metadata for the selected scan. */
  return request<ScanMetadata>(`/scans/${scanId}/metadata`, token);
}

export async function getScanStats(scanId: string, token: string): Promise<ReviewStats> {
  /** Load annotation and review metrics for one scan. */
  return request<ReviewStats>(`/scans/${scanId}/stats`, token);
}

export async function createScan(payload: ScanCreate, token: string): Promise<Scan> {
  /** Create fake scan metadata and storage entry. */
  return request<Scan>("/scans", token, { method: "POST", body: JSON.stringify(payload) });
}

export async function uploadScan(payload: ScanUpload, token: string): Promise<Scan> {
  /** Upload a scan file and create project-scoped metadata. */
  const formData = new FormData();
  formData.append("project_id", payload.project_id);
  formData.append("name", payload.name);
  formData.append("modality", payload.modality);
  formData.append("file", payload.file);
  const response = await fetch(`${API_BASE_URL}/scans/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!response.ok) {
    throw await responseError(response);
  }
  return response.json() as Promise<Scan>;
}

export async function exportScanForMl(scanId: string, token: string): Promise<ExportResponse> {
  /** Load the approved annotation payload that an ML pipeline would consume. */
  return request<ExportResponse>(`/scans/${scanId}/export`, token);
}

export async function exportScanAsCoco(scanId: string, token: string): Promise<Record<string, unknown>> {
  /** Load approved bounding boxes in COCO format. */
  return request<Record<string, unknown>>(`/scans/${scanId}/export/coco`, token);
}

export async function exportScanAsCsv(scanId: string, token: string): Promise<Record<string, unknown>> {
  /** Load annotations in spreadsheet-friendly CSV format. */
  return request<Record<string, unknown>>(`/scans/${scanId}/export/csv`, token);
}

export async function exportScanAsYolo(scanId: string, token: string): Promise<Record<string, unknown>> {
  /** Load approved bounding boxes in YOLO format. */
  return request<Record<string, unknown>>(`/scans/${scanId}/export/yolo`, token);
}

export async function exportScanAsSegmentation(scanId: string, token: string): Promise<Record<string, unknown>> {
  /** Load approved segmentation masks as a training manifest. */
  return request<Record<string, unknown>>(`/scans/${scanId}/export/segmentation`, token);
}
