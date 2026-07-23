import type { DeletionRequest, LegalHold, RetentionPolicy, RetentionPolicyPayload } from "../types/governance";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, csrfToken: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `Governance request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const listRetentionPolicies = (csrfToken: string) => request<RetentionPolicy[]>("/governance/retention-policies", csrfToken);
export const createRetentionPolicy = (csrfToken: string, payload: RetentionPolicyPayload) => request<RetentionPolicy>("/governance/retention-policies", csrfToken, { method: "POST", body: JSON.stringify(payload) });
export const listLegalHolds = (csrfToken: string) => request<LegalHold[]>("/governance/legal-holds", csrfToken);
export const createLegalHold = (csrfToken: string, projectId: string, approvalReference: string) => request<LegalHold>("/governance/legal-holds", csrfToken, { method: "POST", body: JSON.stringify({ scope_type: "project", scope_id: projectId, reason_code: "customer_request", approval_reference: approvalReference }) });
export const createOrganizationLegalHold = (csrfToken: string, organizationId: string, approvalReference: string) => request<LegalHold>("/governance/legal-holds", csrfToken, { method: "POST", body: JSON.stringify({ scope_type: "organization", scope_id: organizationId, reason_code: "customer_request", approval_reference: approvalReference }) });
export const releaseLegalHold = (csrfToken: string, holdId: string) => request<LegalHold>(`/governance/legal-holds/${holdId}/release`, csrfToken, { method: "POST" });
export const listDeletionRequests = (csrfToken: string) => request<DeletionRequest[]>("/governance/deletion-requests", csrfToken);
export const createDeletionRequest = (csrfToken: string, projectId: string, approvalReference: string) => request<DeletionRequest>("/governance/deletion-requests", csrfToken, { method: "POST", body: JSON.stringify({ scope_type: "project", scope_id: projectId, reason_code: "source_withdrawal", approval_reference: approvalReference }) });
export const createOrganizationDeletionRequest = (csrfToken: string, organizationId: string, approvalReference: string) => request<DeletionRequest>("/governance/deletion-requests", csrfToken, { method: "POST", body: JSON.stringify({ scope_type: "organization", scope_id: organizationId, reason_code: "contract_end", approval_reference: approvalReference }) });
export const approveDeletionRequest = (csrfToken: string, requestId: string) => request<DeletionRequest>(`/governance/deletion-requests/${requestId}/approve`, csrfToken, { method: "POST" });
export const cancelDeletionRequest = (csrfToken: string, requestId: string) => request<DeletionRequest>(`/governance/deletion-requests/${requestId}/cancel`, csrfToken, { method: "POST" });
