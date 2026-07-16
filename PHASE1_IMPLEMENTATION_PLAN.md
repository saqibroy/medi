# Phase 1 Implementation Plan

This plan turns Medi from a scan-level demo into a project-based annotation
workspace. Phase 1 intentionally avoids real DICOM ingestion so the product
foundation can become solid before the imaging pipeline becomes complex.

Status: complete. Production hardening continues in
`PHASE4_PRODUCTION_OPERATIONS_PLAN.md`.

## Target User Flow

1. [x] A user logs in.
2. [x] The user lands in a project workspace.
3. [x] The user selects a scan inside that project.
4. [x] The user annotates slices using project-defined labels.
5. [x] A reviewer approves or rejects annotations.
6. [x] The team exports reviewed annotations for ML training.
7. [x] An admin-style user can create, edit, and delete unused labels.
8. [x] An admin-style user can create and edit projects.
9. [x] A user can add placeholder scans to a selected project from the UI.

## Backend Domain Model

### User

Fields:

- [x] `id`
- [x] `organization_id`
- [x] `email`
- [x] `full_name`
- [x] `password_hash`
- [x] `role`
- [x] `is_active`
- [x] `created_at`

Initial roles:

- `admin`
- `annotator`
- `reviewer`

### Organization

Fields:

- [x] `id`
- [x] `name`
- [x] `created_at`

Organizations create the future path for multi-tenant SaaS. Phase 1 can seed a
single organization while keeping the data model ready for teams.

### Project

Fields:

- [x] `id`
- [x] `organization_id`
- [x] `name`
- [x] `description`
- [x] `modality`
- [x] `created_at`

Projects are the main business object. Scans, labels, and annotations should be
project-scoped.

### Label

Fields:

- [x] `id`
- [x] `project_id`
- [x] `name`
- [x] `color`
- [x] `description`
- [x] `created_at`

Labels should replace hardcoded values such as `tumour`, `lesion`, and
`healthy_tissue` in the frontend.

### Scan Changes

Add:

- [x] `project_id`

Scans should belong to one project.

### Annotation Changes

Add:

- [x] `project_id`
- [x] `label_id`
- [x] `updated_by_user_id`
- [x] `reviewed_by_user_id`

Keep `label` as a denormalized snapshot for early export compatibility, but use
`label_id` for the product workflow.

## API Plan

### Auth

- [x] `POST /auth/login`
- [x] `GET /auth/me`

The Phase 1 token evolved into a database-backed opaque session. Browser
credentials now use an HttpOnly cookie with signed CSRF protection; explicit
bearer headers remain available for non-browser API clients.

### Users

- [ ] `GET /users/me`
- [x] `GET /users`

Phase 1 can keep user management minimal and seed demo users.

### Projects

- [x] `GET /projects`
- [x] `POST /projects`
- [x] `GET /projects/{project_id}`
- [x] `GET /projects/{project_id}/scans`
- [x] `GET /projects/{project_id}/labels`
- [x] `GET /projects/{project_id}/export`

### Labels

- [x] `POST /projects/{project_id}/labels`
- [x] `PUT /labels/{label_id}`
- [x] `DELETE /labels/{label_id}`

### Scan And Annotation Updates

Existing scan and annotation endpoints should keep working, but service
validation should ensure objects belong to the expected project.

Status:

- [x] Existing scan and annotation endpoints require an authenticated cookie or
  explicit API bearer session.
- [x] Scan and annotation access is organization-scoped through projects.
- [x] Annotation creation validates scan and label project consistency.
- [x] Role-based authorization enforces admin, annotator, and reviewer mutation rules.

## Frontend Plan

### App Shell

- [x] Add authenticated state.
- [x] Add project list or project switcher.
- [x] Treat the annotation screen as a selected project workspace.
- [x] Add compact workspace stats.
- [x] Add project creation/editing.

### Annotation Tools

- [x] Load labels from the selected project.
- [x] Show label color swatches.
- [x] Save `label_id` and label name with annotations.
- [x] Use the current user as creator.
- [x] Add label create/edit/delete UI.

### Panels

- [x] Left panel: projects, workspace stats, labels, and scans.
- [x] Center: viewer and annotation tools.
- [x] Right panel: annotation list, review actions, and project/scan export.
- [x] Add stronger empty states when projects, scans, labels, or annotations are missing.
- [x] Add project-scoped scan creation UI.

## Migration Strategy

1. [x] Add Alembic to backend dependencies.
2. [x] Create migration scaffolding.
3. [x] Add a Phase 1 migration for users, organizations, projects, labels, and
   new foreign keys.
4. [x] Replace `ensure_learning_schema_upgrades` with proper migrations after
   the new migration path is working.

For local demo continuity, seed data can recreate the database cleanly rather
than trying to preserve existing `local-dev.db` content.

## Testing Plan

Backend smoke tests:

- [x] Seed/demo database can be created.
- [x] Login returns a token at the service level.
- [x] `GET /auth/me` route returns the signed-in user.
- [x] Projects list returns seeded projects at the service level.
- [x] Labels are project-scoped at the service level.
- [x] Scans are project-scoped in route tests.
- [x] Annotation creation validates scan and label project consistency in tests.
- [x] Export returns reviewed annotations at the service level.
- [x] API route tests cover auth, projects, labels, scans, annotations, and export.

Frontend verification:

- [x] `npm run build`
- [x] Viewer dependencies are split out of the initial app bundle.
- [ ] Manual browser smoke test after each major UI slice.

CI verification:

- [x] GitHub Actions workflow runs backend migration, seed, compile, and tests.
- [x] GitHub Actions workflow runs frontend install and production build.

## First Coding Sequence

1. [x] Add backend auth/security dependencies.
2. [x] Add Alembic files and migration configuration.
3. [x] Add new SQLAlchemy models and schemas.
4. [x] Add auth, project, and label services/routers.
5. [x] Update seed data for organization, users, projects, labels, scans, and
   annotations.
6. [x] Update existing scan/annotation services to respect project fields.
7. [x] Update frontend types and API clients.
8. [x] Update `App.tsx` workflow for login and project selection.
9. [x] Add project export and label management UI.
10. [x] Build and test.
11. [x] Add project creation/editing UI.
12. [x] Add project-scoped scan creation UI.
13. [x] Add role-specific authorization.
14. [x] Add project-scoped scan file upload and storage.
15. [x] Add CI workflow and local quality-check documentation.
16. [x] Split viewer dependencies out of the initial frontend bundle.

## Phase 1 Exit Criteria

- [x] Product docs no longer present Medi only as interview prep.
- [x] App opens as a project workspace.
- [x] Users, projects, labels, scans, annotations, and exports share one coherent
  domain model.
- [x] Demo data tells a plausible business story.
- [x] Backend schema changes have migration scaffolding.
- [x] Backend startup and seed flow use migrations instead of runtime schema
  mutation.
- [x] Basic service tests protect the critical workflow.
- [x] Route-level tests protect authenticated HTTP behavior.
- [x] Admin/reviewer/annotator permissions are enforced.
- [x] Users can add placeholder scans without editing seed data.
- [x] Users can upload scan files without editing seed data.
- [ ] Uploaded scan files are parsed into real renderable image volumes.

## Work Completed So Far

- Product roadmap and Phase 1 plan created.
- README repositioned around Medi as a product.
- User, organization, project, label, scan, and annotation domain model added.
- Demo auth, opaque sessions, seeded users, and seeded product data added.
- Project workspace UI added with login, project selector, stats, labels, scans,
  viewer, review list, and export.
- Label management UI added for creating, editing, selecting, and deleting
  unused labels.
- Project and scan ML export supported.
- Project creation/editing UI added.
- Project-scoped placeholder scan creation UI added.
- Role-specific backend authorization and role-aware UI controls added.
- Route-level API tests added for login, roles, labels, scans, annotations, and
  export.
- Empty, loading, and error states added for projects, labels, scans, viewer,
  annotations, and exports.
- Project-scoped scan upload and local file storage added.
- Docker Compose profile added for PostgreSQL, backend, and built frontend.
- Backend service tests added and passing.
- Migration-only schema flow added; API startup and seed no longer create or
  alter tables.
- CI workflow added for backend migration/seed/tests and frontend build.
- Frontend bundle split added so the app shell, React, and viewer dependencies
  build as separate chunks.
- Phase 2 DICOM/NIfTI ingestion and rendering plan added.
- Research-team pricing model added.
- Product demo script added for the seeded research workspace.
- Phase 2 scan ingestion fields and parser interface skeleton added.
- Synthetic NIfTI fixture generation added for parser tests.
- NIfTI upload parsing and preview PNG generation added.
- Upload UI no longer asks for manual slice count when a file is selected.
- Slice endpoint now serves derived preview PNGs for parsed uploads.
- Scan metadata endpoint and UI panel added.
- Basic window/level controls added for preview rendering.
- Single-file DICOM parser added for synthetic Explicit VR Little Endian images.
- Zipped DICOM series parser added for synthetic Explicit VR Little Endian series.
- Upload UI now shows parser-specific ingestion errors and saving states.
- DICOM parser limits and validation hardening added.
- Upload extension and MIME hint allowlist added.
- DICOM PHI warning checks added without exposing raw patient identifiers.
- Slice endpoint now returns explicit errors for pending, failed, and out-of-range scans.
- Organization scoping tests now cover uploaded scan routes and files.
- Annotation coordinates now stay in parsed image pixel space with bounds checks.
- Public scan API responses no longer expose local `file_path` or `storage_key` values.
- Seeded sample scans now carry explicit synthetic/de-identification metadata.
- Failed uploads now persist as failed scans and can be reprocessed by admins.
- Production object storage and signed URL plan added.
- Background ingestion worker plan added for large studies.
- Phase 3 annotation tools checklist added.
- Phase 3 selected annotation state added to the viewer and annotation list.
- Bounding boxes can now be moved and resized from the viewer.
- Selected annotations can now be deleted from the viewer with admin-only controls.
- Route tests now cover annotation delete permissions across admin, annotator,
  reviewer, and outside-organization users.
- Polygon annotations can now be drawn, closed, rendered, and selected in the
  viewer.
- Polygon route tests now reject out-of-bounds and malformed point geometry.
- Polygon vertices can now be dragged in the viewer and saved through the
  annotation update API.
- Polygon update tests now reject edited points outside scan image bounds.
- Annotation history table, migration, and API response schema added.
- Annotation updates and reviews now record who changed what and when.
- Route tests now cover annotation history records and organization scoping.
- COCO and YOLO export endpoints added for approved bounding-box annotations at
  project and scan scope.
- Export panel now supports internal JSON, COCO, and YOLO previews.
- Route tests now cover COCO/YOLO coordinate conversion and tenant scoping.
- Review workflow now supports the `needs_changes` status.
- Annotation list now has review filter tabs with counts for all, pending,
  approved, needs changes, and rejected annotations.
- Route tests now cover `needs_changes` review decisions and search filtering.
- CSV export endpoints added for spreadsheet review at project and scan scope.
- Export panel now supports CSV previews alongside JSON, COCO, and YOLO.
- Route tests now cover CSV content, row counts, review statuses, and tenant scoping.
- Annotation list now shows created, updated, reviewed timestamps, reviewer,
  and review notes.
- Selected annotations now show their audit history in the right panel.
- Keyboard shortcuts added for box/polygon tools, label cycling, slice navigation,
  selected-annotation review decisions, draft cancel, and polygon finish.
- Segmentation mask storage plan added with binary PNG masks, tenant-scoped
  object keys, dedicated mask metadata table, mask API shape, and export path.
- Production storage plan now includes segmentation mask object keys and storage
  interface methods.
- Viewer geometry edits now support undo and redo for bounding-box move/resize
  and polygon vertex drag changes.
- Local segmentation brush, eraser, clear, and opacity controls added in the
  viewer using an offscreen mask canvas.
- Backend segmentation mask metadata table, migration, local PNG storage
  service, upload/read/delete endpoints, and route tests added.
- Frontend segmentation masks can now be saved, loaded, and deleted through the
  mask API from the viewer.
- Segmentation mask manifest export added at project and scan scope, with CSV
  mask metadata columns for training-data handoff.
- Segmentation mask brush and clear actions now support local undo/redo
  snapshots in the viewer.
- COCO export now includes approved polygon annotations with segmentation
  points, derived bounding boxes, and polygon area.
- Selected annotations can now be edited from the right panel for label,
  status, and notes with role-aware save actions.
- Project and selected-scan review summary metrics now show annotation totals,
  review status counts, completion rate, top labels, annotated slices, and
  annotator counts.
- Annotation assignment/ownership added with organization-scoped user listing,
  default assignment to the creating annotator, auditable reassignment, and a
  right-panel assignee picker.
- Viewer zoom and pan controls added so users can inspect image details while
  keeping saved annotation coordinates in original scan pixel space.
- Selected bounding box and polygon annotations can now be copied to adjacent
  slices with review status reset to pending.
- Annotation tools and viewer now clearly block unlabeled drawing when a project
  has no selectable labels.
- Annotation create/update validation now explicitly protects bounding box,
  polygon, and segmentation coordinate shapes.
- Geometry validation rules moved into a reusable service module for annotation
  CRUD and future batch/import workflows.
- Route tests now cover role and tenant permissions for annotation edit,
  delete, review, and export workflows.
- Annotation list, search, and direct fetch now scope through the scan's
  project organization, including legacy annotations without a direct
  `project_id`.
- Viewer interactions now use explicit Select, Pan, Box, Polygon, and Mask
  tools instead of mixing pan and drawing state.
- Annotation tools now use icon buttons with accessible labels and hover/focus
  tooltips for the active viewer modes.
- Phase 3 frontend QA checklist added with browser setup, role accounts,
  workflow steps, expected results, and evidence fields.
- Phase 3 browser QA completed for box and polygon editing, draft label
  switching, keyboard safety, responsive layout, zoom, pan, and overlay
  alignment.
- Phase 4 operations plan now treats medical-image de-identification,
  encryption, immutable auditing, dataset versioning, private storage,
  retention/deletion, GDPR, and external-AI egress as production gates.
- Database-aware backend readiness/liveness and frontend health checks are
  implemented for Docker Compose.
- Versioned `medi-deid-screening-v1` intake now stores uploaded originals in
  quarantine first, neutralizes filenames, records value-free decisions, and
  blocks unsafe scans from pixels, signed URLs, annotations, masks, statistics,
  and exports. Validated OCR/defacing and transformation remain Phase 4 gates.
- Append-only, tenant-scoped security events now cover authentication,
  medical-image intake, sensitive reads, signed URLs, exports, administration,
  annotations, reviews, masks, and deletions. Events use allowlisted fields,
  keyed integrity hashes, admin-only reads, and ORM/database mutation guards.
  WORM export, retention approval, safe network context, and annotation-history
  tombstoning remain Phase 4 gates.
- Production S3 infrastructure now has deployable KMS encryption, versioning,
  public-access blocking, TLS/KMS deny policies, least-privilege runtime access,
  data-class lifecycle tagging, a read-only verifier, CI linting, and backup/
  restore/deletion procedures. Target-account deployment, approved retention,
  independent backup automation, and drill evidence remain production gates.
- Browser authentication now keeps opaque credentials in HttpOnly, SameSite
  cookies, requires signed session-bound CSRF tokens for state changes, and
  removes browser token storage. Redis provides shared, hashed rate counters
  with fail-closed production behavior; target TLS and managed-Redis evidence
  remains tracked in `SESSION_AND_RATE_LIMIT_PLAN.md`.
- Immutable dataset releases now freeze ready scan evidence, approved
  annotation geometry and safe lineage digests, label taxonomy, segmentation
  masks, object versions/checksums, and tool/export versions. Monotonic project
  versions, append-only superseding/revocation, tenant-safe APIs, admin UI,
  audit coverage, and live checksum-stability evidence are complete; target S3
  and retention/WORM gates remain in `DATASET_RELEASE_PLAN.md`.
- Versioned retention/RPO/RTO policies, append-only legal holds, data-minimized
  deletion requests, requester/approver/operator separation, source-withdrawal
  release revocation, every-version storage purge, checksum receipts, and an
  encrypted disposable database/object recovery drill are implemented. The web
  runtime cannot execute deletion and the operator flag defaults off. Target
  vault/role evidence, approved values, and organization deletion remain in
  `DATA_LIFECYCLE_RECOVERY_PLAN.md`.
- External AI now defaults off with no provider client. Append-only provider
  versions and project data-flow approvals, exact HTTPS deployment origins,
  permanent high-risk data-class exclusions, de-identification checks,
  value-free decisions/audits, admin controls, and a static CI policy form the
  repository boundary. Target network enforcement and real-provider approval
  remain in `EXTERNAL_AI_GOVERNANCE_PLAN.md`.
- Privacy operations now use immutable processing/DPIA evidence versions,
  controlled categories and approval references, a separate keyed subject-
  reference digest, append-only access/rectification/restriction/objection/
  portability/erasure requests, two-person identity verification, calendar-
  aware deadlines, and executed-deletion-receipt enforcement for erasure.
  Target legal decisions and case/delivery tooling remain in
  `PRIVACY_OPERATIONS_PLAN.md`.

## Next Engineering Priorities

1. Completed: add append-only security audit events for authentication,
   medical-image intake decisions, object access, exports, and administrative
   changes. Remaining WORM/retention work is tracked in
   `SECURITY_AUDIT_PLAN.md`.
2. Completed repository boundary: add deployable target-account storage
   controls, lifecycle tagging, read-only verification, and backup/restore/
   deletion procedures. Cloud deployment and drill evidence remain dependent
   on an approved AWS account, retention values, and operators.
3. Completed repository boundary: shared Redis rate enforcement plus HttpOnly,
   SameSite browser sessions and signed, session-bound CSRF protection.
   Production TLS/managed-Redis evidence remains in
   `SESSION_AND_RATE_LIMIT_PLAN.md`.
4. Completed repository boundary: add immutable dataset releases with scan
   object versions/checksums, label snapshots, approved annotation lineage,
   segmentation masks, deterministic manifests, and append-only lifecycle
   events. Deployment gates remain in `DATASET_RELEASE_PLAN.md`.
5. Completed repository boundary: encrypted recovery drills, versioned
   retention/RPO/RTO policy, legal holds, source withdrawal, two-person
   project/scan deletion, every-version operator purge, and verified value-free
   receipts. Deployment gates remain in `DATA_LIFECYCLE_RECOVERY_PLAN.md`.
6. Completed repository boundary: enforce external-AI default denial,
   approved-provider versions, project data-flow policy, value-free decisions,
   administrator controls, and static CI enforcement. Deployment gates remain
   in `EXTERNAL_AI_GOVERNANCE_PLAN.md`.
7. Completed repository boundary: versioned processing/DPIA evidence and a
   data-minimized privacy-request lifecycle with keyed subject references,
   two-person identity verification, deadline evidence, and governed erasure
   handoff. Deployment gates remain in `PRIVACY_OPERATIONS_PLAN.md`.
8. Next: run the Phase 4 production-readiness review and separate remaining
   repository work from target-environment, operator, and legal evidence.
