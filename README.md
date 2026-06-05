# Medical Image Annotation Learning App

This is an educational full-stack medical image annotation codebase for
interview preparation. It is intentionally commented heavily so a developer can
trace how React, Cornerstone3D, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, and
local file storage fit together.

## Run The Backend

Create a PostgreSQL database named `medical_annotations`, then install and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python3 -m backend.seed
uvicorn backend.main:app --reload
```

Set `DATABASE_URL` if your PostgreSQL username, password, host, or database name
differs from the default in `backend/database.py`.

For a quick local-only demo when PostgreSQL is unavailable, use:

```bash
DATABASE_URL=sqlite:///./local-dev.db python3 -m backend.seed
DATABASE_URL=sqlite:///./local-dev.db uvicorn backend.main:app --reload
```

## Run The Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

The frontend defaults to `http://localhost:8000` for the API. Override it with
`VITE_API_BASE_URL` when the backend runs elsewhere.

## Learn The Flow

Start with `ARCHITECTURE.md`, then read:

- `backend/routers/scans.py` for scan and slice endpoints.
- `backend/routers/annotations.py` for annotation CRUD.
- `frontend/src/hooks/useScan.ts` for scan data flow.
- `frontend/src/hooks/useAnnotations.ts` for annotation data flow.
- `frontend/src/components/ViewerPanel.tsx` for Cornerstone lifecycle and canvas
  drawing behavior.
