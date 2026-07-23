# Background Ingestion Worker Plan

Medi currently parses small DICOM/NIfTI uploads synchronously in the API
request. That is acceptable for Phase 2 demos, but production uploads can be
large enough to block requests, exhaust memory, or time out behind a reverse
proxy. The next production step is to move parsing and preview generation into
a background ingestion worker.

## Goals

- Return quickly from `POST /scans/upload` after storing the original file.
- Track ingestion as `pending`, `processing`, `ready`, or `failed`.
- Let the frontend poll scan status without changing the viewer contract.
- Reuse the same parser code for initial ingestion and admin reprocess.
- Keep job execution idempotent so retries do not corrupt previews.
- Cancel or drain organization/project/scan jobs before governed deletion
  removes their database rows or object prefixes.

## Recommended Stack

For the first production version:

- Redis as the broker.
- RQ or Celery for Python workers.
- One worker queue named `ingestion`.
- Docker Compose service for local worker development.

RQ is simpler and good enough for a first commercial research MVP. Celery is a
better later choice if the app needs scheduled tasks, chains, routing, or
multiple worker pools.

## Job Model

Add an `ingestion_jobs` table:

```text
id
scan_id
organization_id
project_id
status              pending | processing | succeeded | failed
attempt_count
max_attempts
queued_at
started_at
finished_at
error_message
worker_name
job_key             unique idempotency key
created_at
updated_at
```

Rules:

- `scan_id` points to the scan being processed.
- `organization_id` and `project_id` are copied for audit and tenant-safe
  filtering.
- `job_key` should be unique for active jobs, such as
  `scan:{scan_id}:ingest:{attempt_number}`.
- Store safe errors only. Parser tracebacks belong in logs, not API metadata.
- A deletion lock prevents new jobs for the scope; pending jobs become
  `cancelled`, and an already-running worker must observe cancellation before
  committing previews or ready state.

## Upload Flow

1. API validates auth, project scope, file size, extension, and MIME hints.
2. API creates the scan with `ingestion_status="pending"`.
3. API stores original bytes through the storage abstraction.
4. API creates an `ingestion_jobs` row with `status="pending"`.
5. API enqueues `ingest_scan(scan_id, job_id)`.
6. API returns `201 Created` with the scan record.
7. Worker sets scan status to `processing`.
8. Worker reads original bytes from storage.
9. Worker detects source format, parses metadata, and writes previews.
10. Worker updates scan geometry and marks it `ready`.
11. On parser failure, worker marks scan and job `failed`.

## Reprocess Flow

`POST /scans/{scan_id}/reprocess` should:

- Require admin.
- Require the scan to be `failed`.
- Create a new ingestion job.
- Reset scan status to `pending`.
- Enqueue the worker.
- Return the updated scan immediately.

For local Phase 2 compatibility, the endpoint can continue to support a
synchronous fallback when no worker broker is configured.

## Idempotency And Cleanup

Before writing new previews, the worker should delete or replace the existing
`derived/preview/` prefix for the scan. A retry should produce the same final
state as a single successful run.

Rules:

- Never delete the original object during ingestion.
- Write previews to a temporary prefix first for object storage, then promote
  or update metadata only after all slices are written.
- If a worker crashes, a later retry can safely clear and regenerate previews.

## API Behavior

Existing endpoints already support the needed user experience:

- `GET /scans/{scan_id}` returns ingestion status and safe errors.
- `GET /scans/{scan_id}/metadata` returns parsed metadata when ready.
- `GET /scans/{scan_id}/slice/{slice_index}` returns:
  - `409 Conflict` for pending/processing scans.
  - `422 Unprocessable Entity` for failed scans.
  - Preview pixels for ready scans.

Optional later endpoint:

```text
GET /scans/{scan_id}/ingestion-jobs
```

This can expose job history to admins when operational debugging matters.

## Configuration

Recommended environment variables:

```text
INGESTION_MODE=sync|worker
INGESTION_QUEUE_URL=redis://redis:6379/0
INGESTION_QUEUE_NAME=ingestion
INGESTION_MAX_ATTEMPTS=3
INGESTION_JOB_TIMEOUT_SECONDS=900
INGESTION_WORKER_CONCURRENCY=1
```

Default to `INGESTION_MODE=sync` for local development until the worker service
is implemented.

## Observability

Log every transition:

- scan created as pending
- job queued
- job started
- parser success
- parser failure
- reprocess requested

Each log line should include `organization_id`, `project_id`, `scan_id`,
`job_id`, `source_format`, and `attempt_count`.

## Migration Path

1. Extract current synchronous parser call into `run_ingestion(scan_id)`.
2. Add `ingestion_jobs` model and Alembic migration.
3. Add local synchronous job runner for tests.
4. Add Redis + RQ/Celery worker service.
5. Change upload and reprocess endpoints to enqueue jobs when
   `INGESTION_MODE=worker`.
6. Add polling-friendly frontend refresh for pending/processing scans.
7. Add operational docs for starting workers and clearing failed jobs.
8. Replace the current `background_queue: not_configured` deletion disposition
   with counted cancellation/drain evidence and tests.

## Acceptance Criteria

- Upload returns quickly with `ingestion_status="pending"` in worker mode.
- Worker turns valid uploads into `ready` scans with preview slices.
- Worker turns parser failures into `failed` scans with safe errors.
- Reprocess creates a new job and can recover a failed scan.
- Existing synchronous tests remain available for local development.
- Cross-organization access rules remain unchanged for pending, failed, and
  ready scans.
- Organization/project/scan deletion cannot race a queued/running job or allow a
  worker to recreate purged data.
