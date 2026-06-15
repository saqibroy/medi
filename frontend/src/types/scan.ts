/** TypeScript scan models matching backend Pydantic schemas.
 *
 * Keeping these interfaces aligned with backend/schemas.py gives developers a
 * concrete example of contract-first thinking across a full-stack project.
 */

export type Modality = "MRI" | "CT" | "PET" | "Ultrasound" | "XRAY";
export type SourceFormat = "synthetic" | "nifti" | "dicom" | "dicom_zip" | "unknown";
export type IngestionStatus = "pending" | "processing" | "ready" | "failed";

export interface Scan {
  id: string;
  project_id: string | null;
  name: string;
  modality: Modality;
  num_slices: number;
  source_format: SourceFormat;
  ingestion_status: IngestionStatus;
  ingestion_error: string | null;
  imaging_metadata: Record<string, unknown> | null;
  width: number | null;
  height: number | null;
  depth: number | null;
  spacing: number[] | null;
  window_center: number | null;
  window_width: number | null;
  created_at: string;
}

export interface ScanCreate {
  project_id?: string | null;
  name: string;
  modality: Modality;
  num_slices: number;
  file_name: string;
}

export interface ScanUpload {
  project_id: string;
  name: string;
  modality: Modality;
  file: File;
}

export interface SliceImage {
  scan_id: string;
  slice_index: number;
  image_base64: string;
}

export interface ScanMetadata {
  scan_id: string;
  scan_name: string;
  modality: Modality;
  source_format: SourceFormat;
  ingestion_status: IngestionStatus;
  ingestion_error: string | null;
  num_slices: number;
  width: number | null;
  height: number | null;
  depth: number | null;
  spacing: number[] | null;
  window_center: number | null;
  window_width: number | null;
  metadata: Record<string, unknown> | null;
}
