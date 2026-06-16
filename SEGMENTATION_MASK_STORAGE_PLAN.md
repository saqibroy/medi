# Segmentation Mask Storage Plan

Medi should add segmentation masks only after the storage contract is clear.
Brush tools create large pixel data, so masks should not live inside the
`annotations.coordinates` JSON field. The database should own metadata and
tenant scoping; object storage should own the mask bytes.

## Decision

Use one binary PNG mask per segmentation annotation and slice as the first
representation.

Why PNG first:

- It works with local filesystem storage and future S3/GCS storage.
- It is easy for the browser to preview as an opacity overlay.
- It keeps sparse brush edits understandable during early implementation.
- It can be converted later to RLE, COCO segmentation, NIfTI masks, or training
  tensors during export.

RLE should be an export format or optimization, not the initial source of truth.
Brush strokes should be treated as transient frontend editing state until the
mask is committed.

## Object Key Layout

Segmentation masks should follow the scan object-storage pattern and include
organization, project, scan, annotation, and slice identifiers:

```text
org/{organization_id}/project/{project_id}/scan/{scan_id}/annotations/{annotation_id}/mask/{slice_index}.png
org/{organization_id}/project/{project_id}/scan/{scan_id}/annotations/{annotation_id}/mask/{slice_index}.metadata.json
```

Rules:

- IDs must come from trusted database rows, not client-provided path strings.
- Public API responses may expose annotation IDs and signed preview URLs, but
  not raw storage keys.
- Deleting an annotation must delete or tombstone its mask prefix.
- Mask dimensions must exactly match the parsed scan image dimensions.

## Database Shape

Add a dedicated table instead of overloading `annotations.coordinates`:

```text
segmentation_masks
- id
- annotation_id
- project_id
- scan_id
- slice_index
- storage_key
- width
- height
- encoding: png_binary
- byte_size
- checksum_sha256
- created_by_user_id
- updated_by_user_id
- created_at
- updated_at
```

The existing `annotations` row remains the semantic object:

```json
{
  "annotation_type": "segmentation",
  "coordinates": {
    "mask_ref": true,
    "representation": "png_binary"
  }
}
```

This keeps segmentation objects reviewable and exportable through the same
annotation workflow while avoiding large blobs in the database.

## API Shape

Minimum backend endpoints:

```text
POST /annotations/{annotation_id}/mask
GET /annotations/{annotation_id}/mask/{slice_index}
GET /annotations/{annotation_id}/mask/{slice_index}/url
DELETE /annotations/{annotation_id}/mask/{slice_index}
```

Upload behavior:

- Accept PNG mask bytes or a compact client-side canvas payload.
- Enforce annotation type is `segmentation`.
- Enforce annotation, project, scan, and user organization all match.
- Validate slice index, width, height, content type, byte size, and checksum.
- Replace existing mask for the same annotation and slice atomically.
- Record annotation history entry when a mask is created, replaced, or deleted.

Download behavior:

- For local MVP, return base64 PNG bytes like scan slices.
- For production-scale usage, return short-lived signed URLs.

## Frontend Workflow

Brush tools should operate on an offscreen mask canvas:

1. User selects `segmentation` mode.
2. Viewer creates or selects a segmentation annotation.
3. Brush and eraser mutate an offscreen alpha mask for the current slice.
4. Opacity slider controls mask preview over the image.
5. Save uploads the PNG mask for the selected annotation and slice.
6. Undo/redo operates locally on mask canvas snapshots before upload.

The frontend should not upload every brush movement. Save on explicit commit,
slice change, or debounce after idle time once autosave is introduced.

Current implementation status:

- Local brush, eraser, clear, and opacity controls are implemented in the
  viewer for segmentation mode.
- Backend mask metadata, local PNG storage, upload/read/delete endpoints,
  dimension checks, organization scoping, and mask audit history are implemented.
- Mask edits can now be saved, loaded, and deleted from the frontend viewer.
- Project and scan segmentation manifest exports now include approved mask
  metadata for training-data handoff.
- Brush, eraser, and clear edits now support local undo/redo snapshots before
  save.

## Export Path

Initial segmentation export should produce:

- Internal JSON with annotation metadata and mask file references.
- CSV rows with mask availability, dimensions, checksum, and review status.
- A ZIP-friendly manifest listing mask PNG object keys or signed download URLs.

Later export formats:

- COCO segmentation RLE or polygons after conversion.
- NIfTI mask volumes for medical-imaging workflows.
- Per-slice PNG masks for simple 2D training pipelines.

## Security And Compliance

- Store masks in private object storage with server-side encryption.
- Use tenant-scoped object keys and authorization checks on every mask route.
- Never expose raw storage keys to the browser.
- Keep masks tied to de-identified scan records only.
- Include mask create/update/delete events in annotation history.
- Include masks in future customer data deletion workflows.

## Implementation Sequence

1. [x] Add `segmentation_masks` model and Alembic migration.
2. [x] Add local storage methods for mask write/read/delete.
3. [x] Add backend mask upload, read, and delete endpoints.
4. [x] Add route tests for organization scoping, dimension validation, and delete.
5. [x] Add viewer mask overlay loading from the backend.
6. [x] Add local undo/redo snapshots for mask brush edits.
7. [x] Add internal JSON and CSV segmentation export metadata.
8. [ ] Add signed URL support when scan storage moves behind object storage.

## Acceptance Criteria

- Segmentation mask bytes are stored outside the relational annotation JSON.
- Mask dimensions are validated against scan image dimensions.
- Mask routes are project- and organization-scoped.
- Public responses do not expose raw storage keys.
- Annotation history records mask create/update/delete events.
- The implementation works with local Docker storage and can move to S3 without
  changing the API contract.
