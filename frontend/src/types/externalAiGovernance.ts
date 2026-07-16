export type ExternalAIPurpose = "research_inference" | "annotation_assistance" | "quality_assurance";
export type ExternalAIDataClass = "deidentified_pixels" | "derived_previews" | "deidentified_metadata" | "annotation_geometry" | "label_taxonomy";
export type ExternalAITransferMechanism = "not_applicable" | "adequacy_decision" | "standard_contractual_clauses" | "approved_derogation";

export interface ExternalAIStatus {
  enabled: boolean;
  allowed_origins: string[];
  provider_network_call_implemented: false;
  permanently_prohibited_data_classes: string[];
}

export interface ExternalAIProviderPayload {
  provider_key: string;
  display_name: string;
  model_name: string;
  model_version: string;
  purpose_code: ExternalAIPurpose;
  endpoint_origin: string;
  region_code: string;
  data_classes: ExternalAIDataClass[];
  retention_days: number;
  training_use_allowed: false;
  subprocessors: string[];
  transfer_mechanism: ExternalAITransferMechanism;
  contract_owner_reference: string;
  approval_reference: string;
}

export interface ExternalAIProvider extends ExternalAIProviderPayload {
  id: string;
  organization_id: string;
  version: number;
  created_by_user_id: string;
  created_at: string;
  status: "active" | "revoked" | "unapproved";
  events: Array<{ id: string; action: "approved" | "revoked"; actor_user_id: string; occurred_at: string }>;
}

export interface ExternalAIDataFlowPayload {
  project_id: string;
  provider_approval_id: string;
  purpose_code: ExternalAIPurpose;
  data_classes: ExternalAIDataClass[];
  approval_reference: string;
  expires_at: string | null;
}

export interface ExternalAIDataFlow extends ExternalAIDataFlowPayload {
  id: string;
  organization_id: string;
  created_by_user_id: string;
  created_at: string;
  status: "active" | "revoked" | "expired" | "unapproved";
  events: Array<{ id: string; action: "approved" | "revoked"; actor_user_id: string; occurred_at: string }>;
}

export interface ExternalAIDecision {
  id: string;
  organization_id: string;
  provider_approval_id: string;
  data_flow_id: string;
  project_id: string;
  actor_user_id: string;
  purpose_code: ExternalAIPurpose;
  requested_data_classes: ExternalAIDataClass[];
  result: "allowed" | "denied";
  reason_code: string;
  occurred_at: string;
}
