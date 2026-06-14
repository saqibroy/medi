import type { ExportResponse } from "./annotation";
import type { Modality } from "./scan";

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  modality: Modality;
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
