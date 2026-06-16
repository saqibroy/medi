/** TypeScript annotation models matching backend Pydantic schemas.
 *
 * The coordinates field is intentionally flexible because medical annotation
 * formats vary by tool: a box, polygon, or segmentation mask all need different
 * geometry structures.
 */

export type AnnotationType = "bounding_box" | "polygon" | "segmentation";
export type ReviewStatus = "pending" | "approved" | "rejected" | "needs_changes";

export interface BoundingBoxCoordinates {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PolygonPoint {
  x: number;
  y: number;
}

export interface PolygonCoordinates {
  points: PolygonPoint[];
}

export interface Annotation {
  id: string;
  project_id: string | null;
  scan_id: string;
  label_id: string | null;
  label: string;
  annotation_type: AnnotationType;
  coordinates: Record<string, unknown>;
  slice_index: number;
  created_by: string;
  confidence_score: number | null;
  review_status: ReviewStatus;
  reviewer: string | null;
  reviewed_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnnotationCreate {
  project_id?: string | null;
  scan_id: string;
  label_id?: string | null;
  label: string;
  annotation_type: AnnotationType;
  coordinates: Record<string, unknown>;
  slice_index: number;
  created_by: string;
  confidence_score?: number | null;
  review_status?: ReviewStatus;
  reviewer?: string | null;
  reviewed_at?: string | null;
  notes?: string | null;
}

export interface AnnotationUpdate {
  project_id?: string | null;
  label_id?: string | null;
  label?: string;
  annotation_type?: AnnotationType;
  coordinates?: Record<string, unknown> | BoundingBoxCoordinates;
  slice_index?: number;
  created_by?: string;
  confidence_score?: number | null;
  review_status?: ReviewStatus;
  reviewer?: string | null;
  reviewed_at?: string | null;
  notes?: string | null;
}

export interface ExportAnnotation {
  id: string;
  label: string;
  annotation_type: AnnotationType;
  coordinates: Record<string, unknown>;
  slice_index: number;
  confidence_score: number | null;
  created_by: string;
  review_status: ReviewStatus;
}

export interface ExportResponse {
  scan_id: string;
  scan_name: string;
  modality: string;
  num_slices: number;
  export_timestamp: string;
  annotations: ExportAnnotation[];
  total_annotations: number;
  approved_count: number;
  pending_count: number;
}
