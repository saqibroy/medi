/** TypeScript scan models matching backend Pydantic schemas.
 *
 * Keeping these interfaces aligned with backend/schemas.py gives developers a
 * concrete example of contract-first thinking across a full-stack project.
 */

export type Modality = "MRI" | "CT" | "PET" | "Ultrasound" | "XRAY";

export interface Scan {
  id: string;
  name: string;
  file_path: string;
  modality: Modality;
  num_slices: number;
  created_at: string;
}

export interface ScanCreate {
  name: string;
  modality: Modality;
  num_slices: number;
  file_name: string;
}

export interface SliceImage {
  scan_id: string;
  slice_index: number;
  image_base64: string;
}
