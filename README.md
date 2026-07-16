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
should be de-identified before import, and parser metadata flags likely
PHI-bearing DICOM tags without returning raw patient identifiers.

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

The backend container runs migrations, seeds demo users, and stores uploaded scan
files in the `scan_storage` Docker volume.

## Run Quality Checks

Use these before pushing production-minded changes:

```bash
.venv/bin/python -m compileall backend
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
- `PRODUCTION_STORAGE_PLAN.md` for object storage and signed URL planning.
- `BACKGROUND_INGESTION_PLAN.md` for large-study worker planning.
- `BUSINESS_PRICING_MODEL.md` for the first research-team pricing strategy.
- `PRODUCT_DEMO_SCRIPT.md` for the short buyer-facing demo flow.
- `backend/routers/auth.py` for login/session endpoints.
- `backend/routers/projects.py` for projects, project scans, labels, and export.
- `backend/routers/scans.py` for scan and slice endpoints.
- `backend/routers/annotations.py` for annotation CRUD.
- `frontend/src/hooks/useScan.ts` for scan data flow.
- `frontend/src/hooks/useAnnotations.ts` for annotation data flow.
- `frontend/src/components/ViewerPanel.tsx` for Cornerstone lifecycle and canvas
  drawing behavior.
