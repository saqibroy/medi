/** API client for scan-related backend routes.
 *
 * Centralizing fetch calls keeps components focused on UI and makes the network
 * contract easy to replace with generated clients or test doubles later.
 */

import type { Scan, ScanCreate, SliceImage } from "../types/scan";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  /** Fetch JSON and convert HTTP errors into useful exceptions for hooks. */
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function listScans(): Promise<Scan[]> {
  /** Load all scans for the left panel. */
  return request<Scan[]>("/scans");
}

export async function getScan(scanId: string): Promise<Scan> {
  /** Load one scan's metadata for viewer configuration. */
  return request<Scan>(`/scans/${scanId}`);
}

export async function getScanSlice(scanId: string, sliceIndex: number): Promise<SliceImage> {
  /** Load one base64 PNG slice for the current viewport. */
  return request<SliceImage>(`/scans/${scanId}/slice/${sliceIndex}`);
}

export async function createScan(payload: ScanCreate): Promise<Scan> {
  /** Create fake scan metadata and storage entry. */
  return request<Scan>("/scans", { method: "POST", body: JSON.stringify(payload) });
}
