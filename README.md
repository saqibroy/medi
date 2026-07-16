# Medi

Medi is a medical imaging annotation workspace for AI, research, and education
teams working with de-identified imaging datasets. The current product focus is
project-based scan review, label management, annotation QA, and ML-ready export
workflows.

See `PRODUCT_ROADMAP.md` and `PHASE1_IMPLEMENTATION_PLAN.md` for the product
and engineering plan.

## Run The Backend

Create a PostgreSQL database named `medical_annotations`, then install and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
alembic upgrade head
python3 -m backend.seed
uvicorn backend.main:app --reload
```

Set `DATABASE_URL` if your PostgreSQL username, password, host, or database name
differs from the default in `backend/database.py`.

For a quick local-only demo when PostgreSQL is unavailable, use:

```bash
DATABASE_URL=sqlite:///./local-dev.db alembic upgrade head
DATABASE_URL=sqlite:///./local-dev.db python3 -m backend.seed
DATABASE_URL=sqlite:///./local-dev.db uvicorn backend.main:app --reload
```

If you already have an older `local-dev.db` from the pre-migration demo path,
start with a fresh local database before running `alembic upgrade head`.

Seeded demo users:

- `admin@medi.local` / `password`
- `annotator@medi.local` / `password`
- `reviewer@medi.local` / `password`

Seeded scans are synthetic placeholder records with `data_safety="synthetic"`;
the repository does not ship patient imaging files. Uploaded DICOM/NIfTI files
should be de-identified before import. Uploaded originals enter quarantine
first; `medi-deid-screening-v1` promotes only files that pass the supported
DICOM/NIfTI metadata checks and never returns detected patient values. This is
not a substitute for validated pixel OCR/defacing or legal anonymization.

## Run The Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

The frontend defaults to `http://localhost:8000` for the API. Override it with
`VITE_API_BASE_URL` when the backend runs elsewhere.

## Run With Docker Compose

For a production-like local demo with PostgreSQL, the FastAPI backend, and the
built frontend:

```bash
docker compose up --build
```

Then open:

- Frontend: `http://localhost:8080`
- Backend API docs: `http://localhost:8000/docs`
- Backend readiness: `http://localhost:8000/health/ready`
- Backend liveness: `http://localhost:8000/health/live`

The default Compose profile is explicitly **development-only**: it runs
migrations, seeds synthetic demo users, and stores uploaded scan files in the
`scan_storage` Docker volume. Copy `.env.example` to a local ignored `.env` if
you need to override its local settings.

For production, set `APP_ENV=production`, a non-development `DATABASE_URL`, a
unique `TOKEN_SECRET` of at least 32 characters, distinct `CSRF_SECRET` and
`AUDIT_SIGNING_KEY` values of at least 32 characters, exact comma-separated
HTTPS `CORS_ORIGINS`, `SEED_DEMO_DATA=false`, `SESSION_COOKIE_SECURE=true`,
`RATE_LIMIT_BACKEND=redis`, and an encrypted `rediss://` connection in
`RATE_LIMIT_REDIS_URL`. The backend validates these before migrations run and
refuses unsafe startup. Keep real values in the deployment secret manager,
never in `.env.example`, images, or Git.

Production scan storage also fails closed unless it uses a private S3 bucket
with KMS encryption. Set `SCAN_STORAGE_BACKEND=s3`, `SCAN_STORAGE_BUCKET`,
`SCAN_STORAGE_REGION`, `SCAN_STORAGE_SSE=aws:kms`, and
`SCAN_STORAGE_KMS_KEY_ID`. `SCAN_STORAGE_SIGNED_URL_TTL_SECONDS` defaults to 300
and is limited to 60-900 seconds. Supply AWS credentials through workload
identity or the deployment secret manager, not repository files. The signed URL
endpoint authorizes the current organization before minting a derived-preview
URL; it never signs original uploads. Local development continues to use the
private `scan_storage` volume and returns no local file URL.

Target-account S3 controls are defined in
`infrastructure/aws/medi-private-storage.json`; deployment verification and
backup/restore/deletion evidence procedures are in
`STORAGE_OPERATIONS_RUNBOOK.md`. Retention parameters intentionally have no
production defaults and require explicit approval.

Browser sessions are opaque, stored only as keyed token digests in PostgreSQL
and as `HttpOnly`, `SameSite` cookies in the browser, expire after
`SESSION_TTL_MINUTES` (480 by default), and are revoked by `POST /auth/logout`.
State-changing cookie requests require a signed, session-bound CSRF cookie and
header pair. Production uses `Secure`, `__Host-` cookies; the development names
exist only because local HTTP cannot set `Secure` cookies. Explicit bearer
headers remain supported for non-browser clients, but login never returns the
raw credential in JSON.

`LOGIN_RATE_LIMIT_PER_MINUTE` and `SENSITIVE_RATE_LIMIT_PER_MINUTE` configure
shared Redis counters in Compose and production. Rate-limit identities are
keyed hashes rather than raw client addresses, and protected routes fail closed
if the shared production limiter is unavailable. Managed Redis provisioning,
authentication, high availability, and outage evidence remain deployment gates
in `SESSION_AND_RATE_LIMIT_PLAN.md`.

Security-relevant authentication, imaging, export, annotation, and
administrative operations are written to an append-only audit table. Each row
has a keyed integrity hash derived from `AUDIT_SIGNING_KEY`; keep that key in the
deployment secret manager and separate from `TOKEN_SECRET`. Application code
and database triggers reject audit-row updates and deletes. Independent WORM
export and an approved retention policy remain production deployment gates in
`SECURITY_AUDIT_PLAN.md`.

Administrators can freeze a project through
`POST /projects/{project_id}/releases`. Each immutable release has a stable ID,
monotonic project version, deterministic manifest/content checksums, private
object-version evidence, approved annotation lineage, and append-only
superseding/revocation events. Organization members can list releases at
`GET /projects/{project_id}/releases` and inspect one at
`GET /dataset-releases/{release_id}`; administrators revoke through
`POST /dataset-releases/{release_id}/revoke`. Manifests exclude filenames,
storage paths, notes, creator names, patient metadata, and pixels. Target S3
VersionId evidence, retained artifact/WORM packaging, and retention approval
remain gates in `DATASET_RELEASE_PLAN.md`.

Administrators manage versioned retention/RPO/RTO policy, legal holds, and
two-person project/scan deletion requests under `/governance`. These records,
their lifecycle events, and value-free deletion receipts are append-only. The
web runtime cannot execute deletion. Execution requires the separately enabled
`backend.data_lifecycle_cli`, a matching request-ID confirmation, and an admin
operator distinct from requester and approver; production S3 execution also
requires a separate workload identity allowed to remove versions. Keep
`DATA_DELETION_OPERATOR_ENABLED=false` in normal application environments.
See `DATA_LIFECYCLE_RECOVERY_PLAN.md` and `STORAGE_OPERATIONS_RUNBOOK.md`.

Administrators manage privacy evidence under `/governance/privacy`. Processing
activity records are immutable, monotonic versions that pin the declared role,
purpose, Article 6 basis, Article 9 condition, processors/locations/transfers,
retention-policy version, security controls, and DPIA/DPO approval references.
Privacy requests cover access, rectification, restriction, objection,
portability, and erasure through append-only events. The external subject
reference is converted immediately to a keyed digest using
`PRIVACY_REFERENCE_KEY`; keep this production secret distinct from session,
CSRF, and audit keys. Identity proof, request correspondence, and delivered
personal-data copies remain in an approved external case system. Erasure cannot
be marked fulfilled without a matching executed deletion receipt. See
`PRIVACY_OPERATIONS_PLAN.md`; these engineering controls are not legal approval.

## PostgreSQL Migration Safety

Use [POSTGRES_MIGRATION_RUNBOOK.md](POSTGRES_MIGRATION_RUNBOOK.md) for the
required preflight, encrypted backup/restore rehearsal, forward deployment, and
rollback procedure. A local disposable PostgreSQL migration cycle can be run
with `bash scripts/verify_postgres_migrations.sh`; it is not a production
rollback command.

Run `bash scripts/verify_backup_restore_drill.sh` for the encrypted disposable
PostgreSQL plus synthetic private-object restore proof. It does not replace a
signed target backup-vault drill.

## External AI Boundary

External AI is disabled and has no provider-call implementation by default:

```dotenv
EXTERNAL_AI_ENABLED=false
EXTERNAL_AI_ALLOWED_ORIGINS=
```

Administrators may record append-only provider and project data-flow approvals
and run a value-free authorization decision, but this does not transmit data.
Enabling the feature gate requires one or more exact HTTPS gateway origins and
still does not create a provider client. Run the static repository policy with:

```bash
.venv/bin/python scripts/verify_external_ai_egress.py
```

See `EXTERNAL_AI_GOVERNANCE_PLAN.md` for prohibited data classes, approval
fields, operational boundaries, and deployment-only network/legal gates.

## Run Quality Checks

Use these before pushing production-minded changes:

```bash
.venv/bin/python -m compileall backend
.venv/bin/python scripts/verify_external_ai_egress.py
.venv/bin/python -m pytest backend/tests
cd frontend
npm run build
```

The GitHub Actions workflow in `.github/workflows/ci.yml` runs the same backend
and frontend checks, plus an Alembic migration and seed pass against a fresh
SQLite database.

## Product Flow

Start with `PRODUCT_ROADMAP.md`, then read:

- `PHASE1_IMPLEMENTATION_PLAN.md` for the current MVP build sequence.
- `PHASE2_IMAGING_PLAN.md` for the real DICOM/NIfTI ingestion plan.
- `PHASE3_ANNOTATION_TOOLS_PLAN.md` for advanced annotation workflows.
- `PHASE3_FRONTEND_QA_CHECKLIST.md` for the browser QA pass before Phase 3 exit.
- `PHASE4_PRODUCTION_OPERATIONS_PLAN.md` for production, medical-data security,
  privacy, backup, audit, versioning, and external-AI release gates.
- `DATASET_RELEASE_PLAN.md` for immutable release boundaries, verified evidence,
  and remaining deployment gates.
- `DATA_LIFECYCLE_RECOVERY_PLAN.md` for recovery automation, retention, holds,
  deletion approval, operator boundaries, and remaining deployment evidence.
- `EXTERNAL_AI_GOVERNANCE_PLAN.md` for default egress denial, provider and
  dataset-flow approvals, decision evidence, and remaining deployment gates.
- `PRIVACY_OPERATIONS_PLAN.md` for processing/DPIA evidence, privacy-request
  workflows, keyed subject-reference minimization, and deployment legal gates.
- `IMAGING_DEIDENTIFICATION_PLAN.md` for the versioned upload quarantine,
  metadata-screening profile, threat model, and human-review boundary.
- `PRODUCTION_STORAGE_PLAN.md` for object storage and signed URL planning.
- `BACKGROUND_INGESTION_PLAN.md` for large-study worker planning.
- `BUSINESS_PRICING_MODEL.md` for the first research-team pricing strategy.
- `PRODUCT_DEMO_SCRIPT.md` for the short buyer-facing demo flow.
- `backend/routers/auth.py` for login/session endpoints.
- `backend/routers/projects.py` for projects, project scans, labels, releases,
  and export.
- `backend/routers/scans.py` for scan and slice endpoints.
- `backend/routers/annotations.py` for annotation CRUD.
- `frontend/src/hooks/useScan.ts` for scan data flow.
- `frontend/src/hooks/useAnnotations.ts` for annotation data flow.
- `frontend/src/components/ViewerPanel.tsx` for Cornerstone lifecycle and canvas
  drawing behavior.
