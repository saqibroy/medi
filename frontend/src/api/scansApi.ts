/** API client for scan-related backend routes.
 *
 * Centralizing fetch calls keeps components focused on UI and makes the network
 * contract easy to replace with generated clients or test doubles later.
 */

import type { Scan, ScanCreate, ScanMetadata, ScanUpload, SliceImage } from "../types/scan";
import type { ExportResponse } from "../types/annotation";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, token: string, options?: RequestInit): Promise<T> {
  /** Fetch JSON and convert HTTP errors into useful exceptions for hooks. */
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
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
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<Scan>;
}

export async function exportScanForMl(scanId: string, token: string): Promise<ExportResponse> {
  /** Load the approved annotation payload that an ML pipeline would consume. */
  return request<ExportResponse>(`/scans/${scanId}/export`, token);
}
