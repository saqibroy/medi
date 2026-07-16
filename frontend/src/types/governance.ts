export interface RetentionPolicyPayload {
  approval_reference: string;
  original_minimum_days: number;
  mask_minimum_days: number;
  metadata_minimum_days: number;
  dataset_release_minimum_days: number;
  audit_minimum_days: number;
  backup_retention_days: number;
  rpo_hours: number;
  rto_hours: number;
}

export interface RetentionPolicy extends RetentionPolicyPayload {
  id: string;
  organization_id: string;
  version: number;
  created_by_user_id: string;
  created_at: string;
}

export interface LegalHold {
  id: string;
  organization_id: string;
  scope_type: "organization" | "project" | "scan";
  scope_id: string;
  reason_code: "litigation" | "regulatory" | "security_incident" | "customer_request";
  approval_reference: string;
  created_by_user_id: string;
  created_at: string;
  status: "active" | "released";
  events: Array<{ id: string; action: "applied" | "released"; actor_user_id: string; occurred_at: string }>;
}

export interface DeletionRequest {
  id: string;
  organization_id: string;
  scope_type: "project" | "scan";
  scope_id: string;
  reason_code: "erasure_request" | "source_withdrawal" | "contract_end" | "duplicate_data";
  approval_reference: string;
  retention_policy_id: string;
  retention_policy_version: number;
  inventory: Record<string, number>;
  earliest_execute_at: string;
  requested_by_user_id: string;
  created_at: string;
  status: "requested" | "approved" | "cancelled" | "executed" | "verified" | "failed";
  events: Array<{ id: string; action: string; actor_user_id: string; occurred_at: string }>;
  receipt: null | {
    id: string;
    receipt_sha256: string;
    completed_at: string;
    deleted_counts: Record<string, number>;
    object_versions_deleted: number;
    revoked_releases: number;
  };
}
