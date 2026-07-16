import type { PrivacyProcessingRecord, PrivacyProcessingRecordPayload, PrivacyRequest, PrivacyRequestType } from "../types/privacyGovernance";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, csrfToken: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `Privacy governance request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, csrfToken: string, payload?: object) => request<T>(path, csrfToken, {
  method: "POST",
  body: payload ? JSON.stringify(payload) : undefined,
});

export const listPrivacyProcessingRecords = (csrfToken: string) => request<PrivacyProcessingRecord[]>("/governance/privacy/processing-records", csrfToken);
export const createPrivacyProcessingRecord = (csrfToken: string, payload: PrivacyProcessingRecordPayload) => post<PrivacyProcessingRecord>("/governance/privacy/processing-records", csrfToken, payload);
export const revokePrivacyProcessingRecord = (csrfToken: string, recordId: string) => post<PrivacyProcessingRecord>(`/governance/privacy/processing-records/${recordId}/revoke`, csrfToken);
export const listPrivacyRequests = (csrfToken: string) => request<PrivacyRequest[]>("/governance/privacy/requests", csrfToken);
export const createPrivacyRequest = (csrfToken: string, payload: { case_reference: string; external_subject_reference: string; request_type: PrivacyRequestType; scope_type: "project"; scope_id: string }) => post<PrivacyRequest>("/governance/privacy/requests", csrfToken, payload);
export const verifyPrivacyIdentity = (csrfToken: string, requestId: string, evidenceReference: string) => post<PrivacyRequest>(`/governance/privacy/requests/${requestId}/verify-identity`, csrfToken, { evidence_reference: evidenceReference });
export const acceptPrivacyRequest = (csrfToken: string, requestId: string, evidenceReference: string, deletionRequestId?: string) => post<PrivacyRequest>(`/governance/privacy/requests/${requestId}/accept`, csrfToken, { evidence_reference: evidenceReference, linked_deletion_request_id: deletionRequestId || null });
export const fulfillPrivacyRequest = (csrfToken: string, requestId: string, evidenceReference: string, outcomeCode: string) => post<PrivacyRequest>(`/governance/privacy/requests/${requestId}/fulfill`, csrfToken, { evidence_reference: evidenceReference, outcome_code: outcomeCode });
export const denyPrivacyRequest = (csrfToken: string, requestId: string, evidenceReference: string, reasonCode: string) => post<PrivacyRequest>(`/governance/privacy/requests/${requestId}/deny`, csrfToken, { evidence_reference: evidenceReference, reason_code: reasonCode });
export const cancelPrivacyRequest = (csrfToken: string, requestId: string, evidenceReference: string) => post<PrivacyRequest>(`/governance/privacy/requests/${requestId}/cancel`, csrfToken, { evidence_reference: evidenceReference, reason_code: "requester_withdrew" });
export const extendPrivacyRequest = (csrfToken: string, requestId: string, evidenceReference: string, reasonCode: string) => post<PrivacyRequest>(`/governance/privacy/requests/${requestId}/extend`, csrfToken, { evidence_reference: evidenceReference, reason_code: reasonCode });
