# Medi Architecture

This repository is a production-minded research MVP. It uses
React, TypeScript, Tailwind CSS, Cornerstone3D, FastAPI, Pydantic, SQLAlchemy,
PostgreSQL, Alembic, expiring database-backed bearer sessions, role checks, and
a local/S3 private-storage boundary. Real DICOM/NIfTI parsing, KMS-encrypted S3
writes, signed derived previews, a versioned quarantine gate, and a dedicated
append-only security-event ledger are implemented. Independent WORM export,
retention approval, and broader compliance operations remain explicit Phase 4
gates.

## Medical Data Safety Boundary

Medi's default supported data class is synthetic or properly anonymized
research imaging. DICOM/NIfTI files are treated as potentially sensitive at
intake because identifiers can exist in metadata, filenames, linked sidecars,
private tags, free text, or burned-in pixels.

The production architecture must enforce these boundaries:

- quarantine-first storage before versioned metadata checks and normal viewer
  availability;
- allowlisted metadata projection rather than raw header persistence;
- encryption for transport, databases, objects, and backups;
- tenant and role authorization before every scan, mask, export, and signed URL;
- immutable security audit events plus reproducible dataset releases;
- private object storage, tested backup/restore, retention, and verified delete;
- external AI egress disabled unless an approved provider and data flow are
  explicitly configured.

The detailed implementation and release evidence are tracked in
`PHASE4_PRODUCTION_OPERATIONS_PLAN.md`.

## Component Diagram

```text
                       +-----------------------------+
                       |         Radiologist          |
                       +--------------+--------------+
                                      |
                                      v
+----------------------+    HTTP JSON/base64     +----------------------+
| React + TypeScript   | <----------------------> | FastAPI backend      |
| Tailwind UI          |                          | Routers              |
| Cornerstone3D init   |                          | Pydantic schemas     |
| Canvas box overlay   |                          | Service + audit      |
+----------+-----------+                          +----------+-----------+
           |                                                 |
           | local browser state                             | SQLAlchemy Session
           v                                                 v
+----------------------+                          +----------------------+
| Viewer state hooks   |                          | PostgreSQL           |
| useScan              |                          | scans table          |
| useAnnotations       |                          | annotations + audit  |
+----------------------+                          +----------+-----------+
                                                             |
                                                             v
                                                  +----------------------+
                                                  | Private storage      |
                                                  | Local Compose / S3   |
                                                  | Tenant-scoped keys   |
                                                  +----------------------+
```

## Opening A Scan

1. The React app mounts `App.tsx`, which calls `useScan()`.
2. `useScan()` calls `listScans()` in `frontend/src/api/scansApi.ts`.
3. The browser sends `GET /scans` to FastAPI.
4. `backend/routers/scans.py` receives the request. The route uses
   `Depends(get_db)` so FastAPI creates one SQLAlchemy `Session` for that
   request and closes it after the response.
5. The router delegates to `scan_service.list_scans(db)`.
6. The service runs a SQLAlchemy `select(Scan)` query against PostgreSQL.
7. FastAPI serializes the ORM objects through the `ScanRead` Pydantic schema.
   Pydantic is important here because it converts UUIDs and datetimes into JSON
   strings the frontend can consume.
8. React stores the scans in state and selects the first scan.
9. When `selectedScan` or `sliceIndex` changes, `useScan()` calls
   `GET /scans/{scan_id}/slice/{slice_index}`.
10. The backend validates that the scan exists and the slice index is in range.
11. `scan_service.get_slice_image_base64()` returns a derived PNG for parsed
   DICOM/NIfTI uploads and retains a generated fallback for synthetic scans.
12. `ViewerPanel.tsx` receives the base64 slice, draws it to a canvas, and shows
   annotation overlays for the current slice.
13. `useViewer()` initializes a Cornerstone3D `RenderingEngine` and viewport so
   developers can see where real image rendering would plug in. The simplified
   canvas keeps drawing behavior easy to inspect during interview prep.

## Drawing And Saving An Annotation

1. The radiologist chooses label, annotation type, and creator in
   `AnnotationTools.tsx`.
2. In `ViewerPanel.tsx`, mouse down records the starting canvas coordinate.
3. Mouse move updates a draft bounding box using canvas-space coordinates.
4. Mouse up normalizes the box so width and height are positive.
5. `ViewerPanel.tsx` calls `onSaveAnnotation()` with an `AnnotationCreate`
   payload:

```json
{
  "scan_id": "uuid",
  "label": "tumour",
  "annotation_type": "bounding_box",
  "coordinates": { "x": 120, "y": 140, "width": 86, "height": 72 },
  "slice_index": 32,
  "created_by": "Dr. Interview"
}
```

6. `useAnnotations()` calls `createAnnotation()` in
   `frontend/src/api/annotationsApi.ts`.
7. The browser sends `POST /annotations` with JSON.
8. `backend/routers/annotations.py` receives the payload as `AnnotationCreate`.
   Pydantic validates required fields, UUID shape, allowed annotation types, and
   non-negative `slice_index` before service code runs.
9. `annotation_service.create_annotation()` verifies that the referenced scan
   exists and that the requested slice is inside the scan volume.
10. SQLAlchemy creates an `Annotation` ORM object and commits it to PostgreSQL.
11. The committed row is refreshed so generated fields like `id`, `created_at`,
   and `updated_at` are available.
12. FastAPI serializes the row with `AnnotationRead` and sends it back to React.
13. `useAnnotations()` appends the saved annotation to local state.
14. `ViewerPanel.tsx` redraws overlays for the current slice, and
   `AnnotationList.tsx` shows the saved annotation in the right panel.

## ML Team Consumption

The ML team would usually start with:

```text
GET /annotations?scan_id={scan_id}
```

or:

```text
GET /scans/{scan_id}/annotations
```

The response contains one JSON object per annotation. The important fields for
training data are:

- `scan_id`: connects labels to the source imaging volume.
- `slice_index`: places a 2D annotation inside the 3D volume.
- `label`: gives the supervised learning target such as `tumour` or `lesion`.
- `annotation_type`: tells preprocessing code how to interpret geometry.
- `coordinates`: stores the actual geometry. For bounding boxes this project
  uses `{ "x": number, "y": number, "width": number, "height": number }`.

This structure matters because ML preprocessing pipelines must transform human
annotation geometry into model-ready tensors. A bounding-box detector needs box
coordinates, a segmentation model needs masks, and a classification model may
only need label presence per slice or scan. Keeping `annotation_type` next to
`coordinates` lets one API support multiple training workflows without forcing
all geometry into one awkward shape.

## Architectural Decisions

- Routers stay thin so HTTP concerns do not swallow business logic.
- Services own validation that depends on stored data, such as checking whether
  a slice index is valid for a scan.
- Pydantic schemas define the public API contract and teach why validation
  belongs at the application boundary.
- SQLAlchemy ORM models define persistent database structure and relationships.
- Explicitly mapped security-sensitive routes append organization-scoped audit
  events containing stable identifiers and allowlisted scalar details only.
  Keyed hashes support integrity verification, while ORM guards and PostgreSQL/
  SQLite triggers reject updates and deletes. The ledger never copies request
  bodies, credentials, filenames, DICOM values, pixels, geometry, or free text.
- Local file storage simulates S3 paths while keeping the app easy to run on a
  laptop.
- Production object-storage controls are expressed as linted CloudFormation:
  KMS encryption, versioning, disabled ACLs/public access, TLS/KMS deny policy,
  least-privilege runtime permissions, and lifecycle rules keyed by trusted
  `medi-data-class` tags. A read-only verifier supplies deployment evidence;
  account deployment and recovery/deletion drills remain operational gates.
- Cornerstone3D is initialized to demonstrate real viewer lifecycle concepts,
  while canvas drawing keeps the first learning pass approachable.
