/** TypeScript annotation models matching backend Pydantic schemas.
 *
 * The coordinates field is intentionally flexible because medical annotation
 * formats vary by tool: a box, polygon, or segmentation mask all need different
 * geometry structures.
 */

export type AnnotationType = "bounding_box" | "polygon" | "segmentation";

export interface BoundingBoxCoordinates {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Annotation {
  id: string;
  scan_id: string;
  label: string;
  annotation_type: AnnotationType;
  coordinates: Record<string, unknown>;
  slice_index: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AnnotationCreate {
  scan_id: string;
  label: string;
  annotation_type: AnnotationType;
  coordinates: Record<string, unknown>;
  slice_index: number;
  created_by: string;
}
