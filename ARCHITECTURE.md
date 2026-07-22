# Medi Architecture

This repository is a production-minded research MVP. It uses
React, TypeScript, Tailwind CSS, Cornerstone3D, FastAPI, Pydantic, SQLAlchemy,
PostgreSQL with bounded application pools and statement timeouts, Alembic,
absolute/sliding-idle database-backed cookie sessions,
administrator session revocation, signed CSRF
protection, Redis-backed shared rate limits, role checks, and a local/S3
private-storage boundary. Real DICOM/NIfTI parsing, KMS-encrypted S3
writes, signed derived previews, a versioned quarantine gate, and a dedicated
append-only security-event ledger are implemented. Immutable dataset releases
also freeze approved training-data inputs and their deterministic evidence.
The application images run with numeric non-root identities, read-only root
filesystems, no Linux capabilities or privilege escalation, and explicit
temporary/persistent writable paths verified in CI.
Independent WORM export, retention approval, and broader compliance operations
remain explicit Phase 4 gates.

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

## Application Container Boundary

Compose fixes the backend at UID/GID `10001:10001` and Nginx at `101:101`.
Both application roots are read-only, all Linux capabilities are dropped, and
`no-new-privileges` is enabled. Nginx listens on unprivileged port `8080` and
keeps its PID and request/proxy temporary state in a 16 MiB `/tmp` tmpfs. The
backend receives a 64 MiB `/tmp` tmpfs for imaging preview work and runtime
caches plus the only persistent writable application mount: the development
`scan_storage` volume. Temporary mounts are `nodev`, `nosuid`, and `noexec`.

The runtime verifier rejects unexpected writable mounts and proves both denied
root-path writes and required temporary/storage writes. This Compose evidence
does not replace target admission policy, workload identity, network policy,
resource limits, immutable digests, or managed private storage. See
`CONTAINER_HARDENING_PLAN.md`.

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
| useAnnotations       |                          | annotations/releases |
+----------------------+                          +----------+-----------+
                                                             |
                                                  +----------+-----------+
                                                  | Redis                |
                                                  | Hashed rate keys     |
                                                  +----------+-----------+
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
9. `annotation_service.create_annotation_for_user()` first resolves the scan,
   project, label, and assignee inside the signed-in organization, then verifies
   project consistency, geometry, and that the requested slice is inside the
   scan volume. Updates cannot reparent an annotation away from its scan.
10. SQLAlchemy creates an `Annotation` ORM object and commits it to PostgreSQL.
11. The committed row is refreshed so generated fields like `id`, `created_at`,
   and `updated_at` are available.
12. FastAPI serializes the row with `AnnotationRead` and sends it back to React.
13. `useAnnotations()` appends the saved annotation to local state.
14. `ViewerPanel.tsx` redraws overlays for the current slice, and
   `AnnotationList.tsx` shows the saved annotation in the right panel.

## Freezing A Dataset Release

Administrators use `POST /projects/{project_id}/releases` to freeze one
project's ready scans and approved annotations. The service reads each original
and approved segmentation mask through the private-storage boundary, records
its object version, SHA-256, and byte size, then writes a canonical manifest
with a stable release ID and monotonic project version. The manifest includes
safe annotation geometry and lineage digests but excludes filenames, storage
keys, annotation/review notes, creator names, patient metadata, and pixels.

Release and lifecycle rows are append-only in both SQLAlchemy and the database.
A newer release appends a superseding event, while revocation appends a
controlled reason; neither operation rewrites the frozen manifest. Any signed-in
organization member may list or inspect its releases, but only administrators
may create or revoke them. These routes also write data-minimized security audit
events. The browser surface is `DatasetReleasePanel.tsx`; the service and schema
contract live in `backend/services/dataset_release_service.py` and
`backend/schemas.py`.

## Governing Retention, Holds, And Deletion

Organization administrators create explicit versioned retention policies; the
application supplies no production retention values. Legal holds and deletion
requests use immutable parent records plus append-only lifecycle events.
Deletion snapshots a value-free row/object-reference inventory and the exact
policy version. A different administrator must approve after minimum retention
has elapsed and all organization/project/scan holds are clear.

Deletion execution is deliberately absent from HTTP routes. The separately
enabled `backend.data_lifecycle_cli` requires the approved request UUID twice
and a third active administrator identity. It rechecks policy and holds, derives
the tenant prefix from database ownership, purges the exact local scope or every
S3 version/delete marker, verifies absence, revokes affected releases, and then
removes scan-owned rows. Project deletion leaves a data-minimized tombstone so
immutable release and audit identifiers remain valid. A checksum-protected,
append-only receipt records only stable IDs, counts, actors, timestamps, and
backup expiry. Its signed success audit is committed in the same database
transaction as the receipt/lifecycle events; failures append a signed error
audit beside the failed lifecycle event.

The normal S3 runtime role still cannot delete object versions. The operator
must use separately approved credentials, and target backup-vault/Object Lock,
organization-wide deletion, policy approval, and signed drills remain Phase 4
gates. `scripts/verify_backup_restore_drill.sh` proves the encrypted recovery
sequence only on disposable PostgreSQL databases and synthetic objects.

## Governing Privacy Operations

`/governance/privacy` exposes administrator-only processing records and privacy
request workflows. A processing record is an immutable, monotonic activity
version that pins controlled role, purpose, lawful-basis/Article 9 declarations,
data/subject/recipient categories, processor and location references, transfer
mechanism, the exact retention-policy version, security-control references, and
DPIA/DPO evidence. Append-only record events support second-administrator
revocation. A version whose DPIA outcome requires prior consultation is reported
as `consultation_required`, never active.

Privacy requests accept access, rectification, restriction, objection,
portability, and erasure case types. Medi does not become the identity system:
the supplied external subject reference is converted immediately to a tenant-
scoped HMAC-SHA-256 digest under a separate `PRIVACY_REFERENCE_KEY`; successful
responses expose only a short digest token. Identity documents, correspondence,
free-text decisions, and delivered copies stay outside Medi. A second
administrator must record external identity-verification evidence before
acceptance. The service computes a one-calendar-month target, supports one
controlled two-month extension, and derives on-time/overdue state from
append-only events.

Fulfillment stores only a controlled outcome and evidence reference. An erasure
case must link to the same tenant and project/scan scope in the existing deletion
workflow, and cannot be fulfilled until that request has an executed deletion
receipt. Other rights remain evidence-governed operator workflows rather than
unsafe automatic data disclosure or mutation. Signed audits contain only stable
targets, scope/type/status/reason codes, and no subject reference or case
evidence. Target legal decisions, identity tooling, secure delivery, and
end-to-end operational exercises remain gates in `PRIVACY_OPERATIONS_PLAN.md`.

## Governing External AI Egress

The normal runtime starts with `EXTERNAL_AI_ENABLED=false`, an empty exact-
origin allowlist, and no provider HTTP or vendor SDK client. Append-only provider
approvals pin purpose, model/version, HTTPS origin, region, allowed data classes,
retention, no-training terms, subprocessors, transfer mechanism, contract owner,
and an external approval reference. Project data-flow approvals pin a subset of
those classes to one exact provider version; revocation requires a different
administrator.

`POST /governance/external-ai/evaluate` is an authorization dry run, not an AI
request. It records only stable IDs, controlled data classes, result, reason,
actor, and timestamp. It denies unless the feature gate, deployment origin,
active provider and project flow, purpose, class subset, expiry, project state,
and de-identification status all pass. Raw DICOM, direct identifiers, raw DICOM
metadata, and clinical free text have no accepted API schema value and are
always outside this boundary. The security ledger audits the decision without
prompts, pixels, filenames, annotations, credentials, or response content.

CI statically rejects general HTTP/vendor-AI imports and new process-based
network bypasses in backend runtime code. This is defense in depth, not a
network firewall: a target egress proxy, DNS/firewall enforcement, approved
provider adapter, output provenance/versioning, and signed legal/privacy review
remain deployment gates in `EXTERNAL_AI_GOVERNANCE_PLAN.md`.

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
- The application PostgreSQL engine bounds steady/overflow connections and
  checkout waits per process, pre-pings pooled connections, applies a
  server-side statement timeout, and emits duration-only slow-query signals.
  SQL, parameters, schema names, exception text, and data values are excluded;
  the request ID connects a warning to the existing privacy-safe route log.
  SQLAlchemy failures become a generic `503` and `database_unavailable` event
  at the outer request boundary so default tracebacks cannot expose SQL or
  values.
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
