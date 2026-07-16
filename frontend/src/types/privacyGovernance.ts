export type PrivacyRequestType = "access" | "rectification" | "restriction" | "objection" | "portability" | "erasure";

export interface PrivacyProcessingRecordPayload {
  activity_key: string;
  organization_role: "controller" | "processor" | "joint_controller";
  purpose_code: "research_dataset_annotation" | "imaging_quality_assurance" | "ml_dataset_export" | "security_and_audit" | "service_operations" | "customer_support" | "external_ai_inference";
  lawful_basis: "consent" | "contract" | "legal_obligation" | "vital_interests" | "public_task" | "legitimate_interests";
  health_data_processed: boolean;
  article9_condition: "not_applicable" | "explicit_consent" | "employment_social_security" | "vital_interests" | "nonprofit" | "made_public" | "legal_claims" | "substantial_public_interest" | "healthcare" | "public_health" | "research_statistics";
  data_subject_categories: string[];
  personal_data_categories: string[];
  recipient_categories: string[];
  processor_references: string[];
  processing_locations: string[];
  transfer_mechanism: "not_applicable" | "adequacy_decision" | "standard_contractual_clauses" | "binding_corporate_rules" | "approved_derogation";
  transfer_safeguard_reference: string | null;
  retention_policy_id: string;
  security_measure_references: string[];
  dpia_required: boolean;
  dpia_outcome: "not_required" | "approved" | "consultation_required";
  dpia_reference: string;
  dpo_review_reference: string;
  approval_reference: string;
}

export interface PrivacyProcessingRecord extends PrivacyProcessingRecordPayload {
  id: string;
  organization_id: string;
  version: number;
  retention_policy_version: number;
  created_by_user_id: string;
  created_at: string;
  status: "active" | "superseded" | "revoked" | "consultation_required" | "unrecorded";
  events: Array<{ id: string; action: "recorded" | "revoked"; actor_user_id: string; occurred_at: string }>;
}

export interface PrivacyRequestEvent {
  id: string;
  action: "received" | "identity_verified" | "accepted" | "fulfilled" | "denied" | "cancelled" | "deadline_extended";
  actor_user_id: string;
  reason_code: string | null;
  outcome_code: string | null;
  evidence_reference: string | null;
  linked_deletion_request_id: string | null;
  new_due_at: string | null;
  occurred_at: string;
}

export interface PrivacyRequest {
  id: string;
  organization_id: string;
  case_reference: string;
  subject_reference_token: string;
  request_type: PrivacyRequestType;
  scope_type: "organization" | "project" | "scan";
  scope_id: string;
  received_at: string;
  response_due_at: string;
  effective_due_at: string;
  created_by_user_id: string;
  created_at: string;
  status: "received" | "identity_verified" | "accepted" | "fulfilled" | "denied" | "cancelled" | "untracked";
  deadline_status: "on_time" | "overdue" | "completed_on_time" | "completed_late";
  events: PrivacyRequestEvent[];
}
