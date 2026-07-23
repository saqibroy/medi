import type { ExportResponse } from "./annotation";
import type { Modality } from "./scan";

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  modality: Modality;
  lifecycle_status: "active" | "deleted";
  deleted_at: string | null;
  created_at: string;
}

export interface ProjectPayload {
  name: string;
  description: string | null;
  modality: Modality;
}

export interface Label {
  id: string;
  project_id: string;
  name: string;
  color: string;
  description: string | null;
  created_at: string;
}

export interface ProjectExportResponse {
  project_id: string;
  project_name: string;
  export_timestamp: string;
  scans: ExportResponse[];
  total_annotations: number;
  approved_count: number;
  pending_count: number;
}

export type DatasetReleaseStatus = "active" | "superseded" | "revoked";
export type DatasetReleaseReason = "quality_issue" | "source_withdrawn" | "policy_change" | "other";

export interface DatasetReleaseEvent {
  id: string;
  action: "created" | "superseded" | "revoked";
  reason_code: DatasetReleaseReason | "superseded" | null;
  related_release_id: string | null;
  actor_user_id: string;
  occurred_at: string;
}

export interface DatasetReleaseArtifact {
  id: string;
  artifact_type: "portable_manifest";
  schema_version: string;
  media_type: string;
  object_version_id: string;
  checksum_sha256: string;
  byte_size: number;
  created_by_user_id: string;
  created_at: string;
}

export interface DatasetReleaseSummary {
  id: string;
  organization_id: string;
  project_id: string;
  version: number;
  schema_version: string;
  content_sha256: string;
  manifest_sha256: string;
  supersedes_release_id: string | null;
  created_by_user_id: string;
  created_at: string;
  status: DatasetReleaseStatus;
  artifacts: DatasetReleaseArtifact[];
  lifecycle: DatasetReleaseEvent[];
}

export interface DatasetRelease extends DatasetReleaseSummary {
  manifest: Record<string, unknown>;
}
