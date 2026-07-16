# Production Storage Plan

Status: in progress. The path-safe `LocalPrivateStorage` boundary and
organization/project/scan key layout are implemented for originals, previews,
reprocessing, and segmentation masks. S3, signed preview URLs, encryption
configuration, lifecycle controls, and cloud integration tests remain.

Medi currently stores scan originals and derived preview PNGs on the local
filesystem so the product can run simply in development and Docker Compose. For
production, scan assets should move behind an object-storage abstraction with
private buckets and short-lived signed URLs.

## Goals

- Keep original uploads and derived previews outside the application container.
- Keep object keys tenant-scoped by organization, project, and scan.
- Never expose local filesystem paths or raw bucket paths in public API
  responses.
- Support reprocessing from the stored original object.
- Prepare for background ingestion workers without changing the API contract.

## Object Key Layout

Use deterministic keys that mirror the current local folder structure:

```text
org/{organization_id}/project/{project_id}/scan/{scan_id}/original/{filename}
org/{organization_id}/project/{project_id}/scan/{scan_id}/derived/preview/{slice_index}.png
org/{organization_id}/project/{project_id}/scan/{scan_id}/metadata/ingestion.json
org/{organization_id}/project/{project_id}/scan/{scan_id}/annotations/{annotation_id}/mask/{slice_index}.png
org/{organization_id}/project/{project_id}/scan/{scan_id}/annotations/{annotation_id}/mask/{slice_index}.metadata.json
```

Rules:

- `organization_id`, `project_id`, and `scan_id` must come from trusted database
  records, not client input.
- `filename` must be sanitized with the same basename-only rule used today.
- Public API responses may include scan IDs and metadata, but not storage keys.
- Services may store object keys internally in `file_path` and `storage_key`
  until a dedicated object table is introduced.

## Storage Interface

Introduce a `storage_service` boundary before adding S3/GCS/Azure code:

```python
class ScanStorage:
    def write_original(key: str, content: bytes) -> None: ...
    def read_original(key: str) -> bytes: ...
    def write_preview(key: str, content: bytes) -> None: ...
    def read_preview(key: str) -> bytes: ...
    def write_mask(key: str, content: bytes) -> None: ...
    def read_mask(key: str) -> bytes: ...
    def delete_prefix(prefix: str) -> None: ...
    def signed_get_url(key: str, expires_seconds: int) -> str: ...
```

Initial implementations:

- `LocalScanStorage` for tests and Docker Compose.
- `S3ScanStorage` for production.

The parser can keep writing previews through `Path` during Phase 2, but the next
implementation step should move preview writes behind this interface.
Segmentation masks should use the same storage abstraction so brush tools can
write local PNG masks during development and private object-storage masks in
production.

## Signed URLs

For the current API, `GET /scans/{scan_id}/slice/{slice_index}` can continue
returning base64 PNGs because it keeps the frontend simple. For production-scale
datasets, add a separate endpoint:

```text
GET /scans/{scan_id}/slice/{slice_index}/url
```

Behavior:

- Enforce the same organization and ingestion-status checks as the base64 slice
  endpoint.
- Return a short-lived signed URL for the derived preview object.
- Default expiry: 5 minutes.
- Do not sign original uploads for browser access.

## Configuration

Recommended environment variables:

```text
SCAN_STORAGE_BACKEND=local|s3
SCAN_STORAGE_ROOT=/app/backend/data/sample_scan
SCAN_STORAGE_BUCKET=medi-scans-prod
SCAN_STORAGE_REGION=us-east-1
SCAN_STORAGE_SIGNED_URL_TTL_SECONDS=300
SCAN_STORAGE_SSE=aws:kms
SCAN_STORAGE_KMS_KEY_ID=...
```

For local development, keep `SCAN_STORAGE_BACKEND=local` and the Docker
`scan_storage` volume.

## Security Baseline

- Bucket must be private.
- Application role can read/write only the configured prefix or bucket.
- Browser clients receive signed preview URLs only after API authorization.
- Original uploads remain server-only.
- Enable server-side encryption.
- Enable object versioning or retention for recovery, with a documented delete
  workflow for customer data.
- Log object reads/writes with organization, project, scan, user, and action.

## Migration Path

1. [x] Add `storage_service.py` with local implementation and unit tests.
2. [x] Move upload original writes, preview reads, preview deletion, and reprocess
   reads behind the storage interface.
3. [ ] Add S3 implementation using `boto3`.
4. [ ] Add signed preview URL endpoint.
5. [x] Keep current base64 slice endpoint as compatibility fallback.
6. Add lifecycle rules for derived previews and retained originals.
7. Document backup, restore, and customer deletion processes.

## Acceptance Criteria

- No public response includes local filesystem paths or raw object keys.
- Existing upload, slice, metadata, and reprocess tests pass on local storage.
- S3 storage can upload originals, read originals for reprocess, write previews,
  write segmentation masks, and generate signed preview URLs.
- Cross-organization tests prove signed URLs cannot be created for another
  tenant's scans.
- Docker Compose remains local-only and requires no cloud credentials.
