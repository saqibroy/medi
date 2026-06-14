# Phase 2 Imaging Plan

This plan upgrades Medi from placeholder slice generation to real research-file
ingestion and rendering. Phase 2 should still target de-identified,
non-diagnostic research workflows; it should not claim clinical decision support.

Status: planned.

## Current State

- Uploaded scan files are stored under `backend/data/sample_scan`.
- The upload form asks the user for `modality` and `num_slices`.
- `GET /scans/{scan_id}/slice/{slice_index}` returns a simulated PNG generated
  by Pillow, not pixels decoded from the uploaded file.
- `GET /scans/{scan_id}/slice/{slice_index}/metadata` returns teaching metadata,
  not parsed file metadata.
- The frontend viewer renders a base64 PNG to canvas and overlays annotations.

This is good for product workflow validation. It is not enough for real dataset
work because slice count, spacing, orientation, windowing, and pixel values must
come from the imaging file itself.

## Phase 2 Goal

An admin uploads a de-identified DICOM series or NIfTI file, Medi validates it,
extracts metadata, creates renderable preview slices, and lets annotators review
real image pixels inside the existing project workspace.

## Supported Inputs

Start narrow:

- [ ] Single-file NIfTI: `.nii`, `.nii.gz`
- [ ] Single DICOM file for smoke testing: `.dcm`
- [ ] Zipped DICOM series: `.zip`

Defer until later:

- DICOMweb import.
- PACS integration.
- Multi-series studies in one upload.
- Segmentation objects and RTSTRUCT import.

## Backend Packages

Recommended first pass:

- `nibabel` for NIfTI metadata and pixel access.
- `pydicom` for DICOM metadata parsing.
- `numpy` for pixel normalization and slice extraction.
- `pillow` remains useful for preview PNG generation.

Optional later:

- `SimpleITK` for more robust resampling and orientation handling.
- `highdicom` when DICOM segmentation and structured objects become necessary.

## Storage Layout

Keep local storage in Phase 2, but organize it like future object storage:

```text
backend/data/sample_scan/
  {project_id}/
    {scan_id}/
      original/
      derived/
        preview/
          000000.png
          000001.png
      metadata.json
```

Future S3-style object keys can mirror this layout:

```text
org/{organization_id}/project/{project_id}/scan/{scan_id}/...
```

## Data Model Additions

Add these fields to `scans` with an Alembic migration:

- [x] `storage_key`: stable path or object key root for scan assets.
- [x] `source_format`: `synthetic`, `nifti`, `dicom`, `dicom_zip`, or
  `unknown`.
- [x] `ingestion_status`: `pending`, `processing`, `ready`, `failed`.
- [x] `ingestion_error`: nullable failure detail safe to show admins.
- [x] `metadata`: JSON summary of parsed imaging metadata.
- [x] `width`: pixel width.
- [x] `height`: pixel height.
- [x] `depth`: slice count from the file.
- [x] `spacing`: JSON array such as `[row_mm, col_mm, slice_mm]`.
- [x] `window_center`: nullable numeric default.
- [x] `window_width`: nullable numeric default.

Keep `num_slices` for API compatibility at first, but set it from parsed `depth`.

## Ingestion Flow

1. [ ] Admin uploads a file.
2. [ ] Backend creates a scan with `ingestion_status="pending"`.
3. [ ] Backend stores original bytes in the scan storage folder.
4. [ ] Backend detects format from extension and file content.
5. [ ] Backend validates file size, emptiness, supported format, and project
   access.
6. [ ] Parser extracts metadata and volume dimensions.
7. [ ] Preview generator normalizes each slice to 8-bit PNG.
8. [ ] Scan is updated with parsed metadata, dimensions, `num_slices`, and
   `ingestion_status="ready"`.
9. [ ] On parser failure, scan becomes `ingestion_status="failed"` with a safe
   error message.

Phase 2 can process synchronously for small demo files. Production should move
steps 4-8 into a background worker so large studies do not block API requests.

## API Plan

Update existing endpoints:

- [ ] `POST /scans/upload`
  - Stop accepting user-supplied `num_slices` as truth.
  - Return scan with `ingestion_status`.

- [ ] `GET /scans/{scan_id}`
  - Include parsed dimensions, metadata summary, and ingestion status.

- [ ] `GET /scans/{scan_id}/slice/{slice_index}`
  - If `ready`, return the derived preview PNG.
  - If `pending` or `processing`, return `409 Conflict`.
  - If `failed`, return `422 Unprocessable Entity`.

Add:

- [x] `GET /scans/{scan_id}/metadata`
  - Return parsed file metadata safe for the UI.

- [ ] `POST /scans/{scan_id}/reprocess`
  - Admin-only retry after failed ingestion.

## Frontend Plan

- [x] Upload UI stops asking for `num_slices`.
- [ ] Scan list shows ingestion status.
- [ ] Viewer empty state explains `processing` and `failed` scans.
- [ ] Slice slider bounds come from parsed `num_slices`.
- [x] Viewer adds basic window/level controls for CT and MRI previews.
- [x] Metadata panel shows spacing, dimensions, source format, and acquisition
  summary.

The existing canvas annotation overlay can remain for Phase 2. True
Cornerstone imageIds can come after the preview pipeline is trustworthy.

## Security And Privacy Checks

- [ ] Enforce upload size limits.
- [ ] Restrict accepted file extensions and MIME hints.
- [ ] Never display raw patient names, accession numbers, or IDs.
- [ ] Add a parser-side PHI warning when DICOM tags likely contain identifying
  fields.
- [ ] Store sample files as synthetic or explicitly de-identified.
- [ ] Keep original upload paths out of public API responses once object storage
  is introduced.

## Testing Plan

Backend tests:

- [x] Synthetic NIfTI fixture generation creates a valid tiny `.nii.gz` volume.
- [x] NIfTI parser extracts dimensions, spacing, and preview slices from the
  synthetic fixture.
- [ ] DICOM parser extracts safe metadata from a synthetic fixture.
- [ ] Upload rejects empty and unsupported files.
- [x] Slice endpoint returns derived preview pixels for ready scans.
- [ ] Slice endpoint returns useful errors for pending, failed, and out-of-range
  scans.
- [ ] Organization scoping still protects uploaded files.

Frontend tests/manual checks:

- [ ] Upload form handles ready, processing, and failed states.
- [x] Viewer renders a derived preview slice.
- [ ] Existing annotation creation still stores coordinates in image pixel space.

## First Implementation Sequence

1. [x] Add scan ingestion fields and Alembic migration.
2. [x] Add `imaging_service.py` with format detection and parser interfaces.
3. [x] Add synthetic NIfTI fixture generation for tests.
4. [x] Implement NIfTI ingestion and preview PNG generation.
5. [x] Update upload endpoint to parse `num_slices` from the file.
6. [x] Serve derived preview PNGs from storage.
7. [ ] Update frontend upload form and scan status UI.
8. [ ] Add DICOM single-file parser.
9. [ ] Add zipped DICOM series parser.
10. [x] Add basic window/level controls.

## Phase 2 Exit Criteria

- [ ] A synthetic NIfTI upload becomes a ready scan without manual slice count.
- [ ] A synthetic DICOM upload becomes a ready scan without manual slice count.
- [ ] The viewer displays pixels derived from uploaded imaging files.
- [ ] Annotations remain project-scoped and slice-indexed correctly.
- [ ] Failed ingestion gives admins an actionable error.
- [ ] Tests cover parser success, parser failure, and access control.
