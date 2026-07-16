import type { ExternalAIDataFlow, ExternalAIDataFlowPayload, ExternalAIDecision, ExternalAIProvider, ExternalAIProviderPayload, ExternalAIStatus } from "../types/externalAiGovernance";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, csrfToken: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `External AI governance request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

const base = "/governance/external-ai";
export const getExternalAIStatus = (csrf: string) => request<ExternalAIStatus>(`${base}/status`, csrf);
export const listExternalAIProviders = (csrf: string) => request<ExternalAIProvider[]>(`${base}/providers`, csrf);
export const createExternalAIProvider = (csrf: string, payload: ExternalAIProviderPayload) => request<ExternalAIProvider>(`${base}/providers`, csrf, { method: "POST", body: JSON.stringify(payload) });
export const revokeExternalAIProvider = (csrf: string, id: string) => request<ExternalAIProvider>(`${base}/providers/${id}/revoke`, csrf, { method: "POST" });
export const listExternalAIDataFlows = (csrf: string) => request<ExternalAIDataFlow[]>(`${base}/data-flows`, csrf);
export const createExternalAIDataFlow = (csrf: string, payload: ExternalAIDataFlowPayload) => request<ExternalAIDataFlow>(`${base}/data-flows`, csrf, { method: "POST", body: JSON.stringify(payload) });
export const revokeExternalAIDataFlow = (csrf: string, id: string) => request<ExternalAIDataFlow>(`${base}/data-flows/${id}/revoke`, csrf, { method: "POST" });
export const listExternalAIDecisions = (csrf: string) => request<ExternalAIDecision[]>(`${base}/decisions`, csrf);
export const evaluateExternalAIEgress = (csrf: string, flow: ExternalAIDataFlow) => request<ExternalAIDecision>(`${base}/evaluate`, csrf, { method: "POST", body: JSON.stringify({ data_flow_id: flow.id, purpose_code: flow.purpose_code, requested_data_classes: flow.data_classes }) });
