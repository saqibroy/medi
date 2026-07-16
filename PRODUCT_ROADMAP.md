# Medi Product Roadmap

Medi should become a focused medical imaging annotation platform for AI,
research, and education teams. The first commercial version should target
de-identified datasets and non-diagnostic workflows, then expand toward
enterprise healthcare readiness after the product proves demand.

## Positioning

Initial offer:

> A lightweight medical image annotation and review workspace for AI teams
> working with CT, MRI, X-ray, and other imaging datasets.

Avoid early claims that the product diagnoses, recommends treatment, replaces
radiologists, or provides clinical decision support. Those claims can trigger a
much harder regulatory path and slow down early traction.

## First Customers

- Medical AI startups preparing supervised learning datasets.
- University labs and imaging research groups.
- Healthcare data science teams working with de-identified studies.
- Education programs teaching medical image labeling workflows.
- Small annotation teams that need review and export workflows without a large
  enterprise platform.

Hospitals and direct clinical deployments are later targets because procurement,
security review, compliance, and integrations are much slower.

## Phase 1: Product Foundation

Goal: turn the current learning app into a credible product MVP.

Status: complete.

Backend:

- [x] Add Alembic migration scaffolding.
- [x] Add users with secure password hashing.
- [x] Add organizations or workspaces.
- [x] Add projects scoped to an organization.
- [x] Attach scans to projects.
- [x] Add labels scoped to projects.
- [x] Add auth endpoints for login and current user.
- [x] Protect scan and annotation routes with bearer auth.
- [x] Add project-level export endpoint.
- [x] Add initial service tests for auth, projects, labels, and exports.
- [x] Add richer role enforcement for admin, annotator, and reviewer actions.
- [x] Replace compatibility schema upgrades with a fully migration-first flow.
- [x] Add API-level route tests for critical auth and workspace flows.
- [x] Add Docker Compose production-like local profile.
- [x] Add CI checks for backend tests and frontend builds.

Frontend:

- [x] Reposition the app from learning demo to product workspace.
- [x] Add login/session state.
- [x] Add project selection as the main workflow entry point.
- [x] Add label management UI.
- [x] Replace hardcoded annotator names with the signed-in user.
- [x] Add project and scan export controls.
- [x] Add workspace stats and label color cues.
- [x] Improve empty, loading, and error states across all panels.
- [x] Add project creation/editing UI.
- [x] Add project-scoped scan creation UI for placeholder scan records.
- [x] Add scan file upload UI scoped to projects.
- [x] Split heavy viewer dependencies from the initial app bundle.
- [x] Add real DICOM/NIfTI parsing and rendering.

Business:

- [x] Define a simple pricing model for research teams.
- [x] Plan DICOM/NIfTI ingestion and rendering for Phase 2.
- [x] Prepare demo data and a short product demo script.
- [x] Keep all sample data clearly synthetic or de-identified.

## Phase 2: Real Imaging Support

Goal: support useful research datasets rather than generated placeholder slices.

- [x] Add upload pipeline for image series.
- [x] Add DICOM or NIfTI ingestion.
- [x] Parse metadata needed for display and dataset management.
- [ ] Store files outside the application directory, preferably behind an object
  storage abstraction.
- [x] Add window and level controls.
- [x] Add import validation and PHI warning checks where practical.
- [ ] Add background processing for large studies.

## Phase 3: Annotation Tools

Goal: make the product efficient for real labeling work.

Status: complete. Inter-annotator agreement metrics are deferred to a later
analytics iteration and are not part of the Phase 3 exit criteria.

- [x] Editable bounding boxes.
- [x] Polygon drawing and editing.
- [x] Segmentation mask workflow.
- [x] Local segmentation brush, eraser, and opacity controls.
- [x] Backend segmentation mask metadata, local PNG storage, and API endpoints.
- [x] Frontend segmentation mask save, load, and delete-saved controls.
- [x] Segmentation mask manifest export for training data.
- [x] Local undo/redo snapshots for segmentation mask brush edits.
- [x] Undo and redo.
- [x] Zoom and pan controls.
- [x] Copy annotation to adjacent slice.
- [x] Clear empty states when no label is selected.
- [x] Keyboard shortcuts.
- [x] Annotation version history.
- [x] Review statuses: pending, approved, rejected, needs changes.
- [x] Annotation edit panel for label/status/notes.
- [x] Review summary metrics per project and scan.
- [x] Annotation assignment/ownership field.
- [ ] Inter-annotator agreement metrics.
- [x] Exports for common ML formats such as JSON, CSV, COCO, YOLO, and segmentation
  training formats.

## Phase 4: Production Operations

Goal: make the app deployable and supportable.

Status: in progress. Detailed gates: `PHASE4_PRODUCTION_OPERATIONS_PLAN.md`.

- [x] Docker Compose for local production-like development.
- [x] Migration-only schema startup for backend containers.
- [x] CI for backend tests and frontend builds.
- Production PostgreSQL configuration.
- Object storage configuration.
- [x] Structured JSON request logging, correlation IDs, and payload-safe redaction.
- Error tracking.
- [x] Database-aware backend readiness/liveness and frontend health checks.
- [x] PostgreSQL migration/rollback runbook and isolated CI rehearsal.
- [x] Shared Redis login and expensive-route rate enforcement with hashed
  identities and fail-closed production behavior.
- Backups and restore documentation.
- Admin tools for organizations, users, and projects.

## Phase 5: Security And Compliance Baseline

Goal: become credible with serious research and healthcare-adjacent teams.

- HTTPS-only production deployment.
- Secure session/token handling.
- Encryption for stored files and database backups.
- Audit logs for access and data changes.
- Tenant isolation checks.
- Principle-of-least-privilege roles.
- Secure file upload limits and validation.
- Data retention and deletion controls.
- Privacy policy, terms, and security documentation.

Medical-data controls begin in Phase 4 rather than waiting for Phase 5. DICOM
and NIfTI intake, encryption, immutable auditing, dataset versioning, private
storage, retention/deletion, GDPR operations, and external-AI egress gates are
tracked in `PHASE4_PRODUCTION_OPERATIONS_PLAN.md`.

HIPAA readiness, Business Associate Agreements, SOC 2-style controls, and
clinical regulatory strategy should come after the research MVP shows traction.

Implemented Phase 4 intake baseline: originals now enter tenant-scoped
quarantine under neutral names, `medi-deid-screening-v1` records value-free
DICOM/NIfTI decisions, and unsafe scans cannot expose pixels, signed URLs,
annotations, masks, statistics, or exports. Validated pixel anonymization and
legal/deployment evidence remain tracked separately.

## Recommended First Sprint

Build a product-grade foundation without jumping into real DICOM complexity yet.

1. [x] Add Alembic migrations.
2. [x] Add user, organization, project, and label models.
3. [x] Scope scans and annotations through projects.
4. [x] Add auth endpoints.
5. [x] Seed realistic product demo data.
6. [x] Update the frontend to start from a project workspace.
7. [x] Add backend smoke tests for the new domain model.
8. [x] Add project export and label management UI.
9. [x] Add project creation/editing UI.
10. [x] Add project-scoped scan creation UI.
11. [x] Add role enforcement.
12. [x] Add API-level route tests.

Definition of done:

- [x] A user can log in.
- [x] A user can select a project.
- [x] A project contains scans, labels, annotations, review status, and export data.
- [x] Demo data presents Medi as a product, not an interview-prep app.
- [x] The backend has a repeatable schema migration path scaffold.
- [x] The frontend builds successfully.
- [x] Admins can create projects from the UI.
- [x] Users can add placeholder scans to a selected project from the UI.
- [x] Reviewer-only and admin-only actions are enforced.
- [x] Route-level API tests cover the critical workflow.

## Current Next Priorities

1. Completed: add append-only, tenant-scoped security audit events for
   authentication, medical-image intake decisions, object access, exports, and
   administrative/annotation changes. Remaining WORM and retention gates are
   tracked in `SECURITY_AUDIT_PLAN.md`.
2. Completed repository boundary: add deployable target-account storage
   controls, lifecycle tagging, read-only verification, and backup/restore/
   deletion procedures. Cloud deployment and drill evidence remain dependent
   on an approved AWS account, retention values, and operators.
3. Completed repository boundary: shared Redis rate enforcement plus HttpOnly,
   SameSite browser sessions and signed, session-bound CSRF protection.
   Production TLS/managed-Redis evidence remains in
   `SESSION_AND_RATE_LIMIT_PLAN.md`.
4. Completed repository boundary: immutable, monotonic project dataset
   releases now freeze ready scan object versions/checksums, label taxonomy,
   approved annotation lineage, and segmentation masks. Superseding and
   revocation append lifecycle events; tenant-safe APIs, admin controls, audit
   coverage, and checksum-stability tests are implemented. Target S3 VersionId,
   retained artifact/WORM, and retention approval remain deployment gates in
   `DATASET_RELEASE_PLAN.md`.
5. Next: automate encrypted backup/restore drills and define enforceable
   retention, legal-hold, source-withdrawal, and verified-deletion behavior.
