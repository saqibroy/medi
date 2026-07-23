# Production Storage Plan

Status: repository-controlled target-account boundary complete. The path-safe local backend,
private S3 backend, organization/project/scan key layout, KMS-encrypted writes,
and tenant-authorized short-lived preview URLs are implemented and tested for
originals, previews, reprocessing, and segmentation masks. Encrypted disposable
restore automation, every-version operator purge, versioned retention policies,
legal holds, two-person approval, and value-free receipts are also implemented.
Retained dataset-release manifests now use a separate tenant/project namespace,
append-only object evidence, integrity-checked downloads, and a non-expiring
`dataset-release` data class.
Target bucket/vault deployment, approved policy values, alerts, organization
deletion, and signed recovery/deletion drills remain production gates.

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
org/{organization_id}/retained-release/project/{project_id}/release-artifact/{release_id}/{manifest_sha256}.json
```

Rules:

- `organization_id`, `project_id`, and `scan_id` must come from trusted database
  records, not client input.
- `filename` must be sanitized with the same basename-only rule used today.
- Public API responses may include scan IDs and metadata, but not storage keys.
- Services may store object keys internally in `file_path` and `storage_key`
  until a dedicated object table is introduced.
- Retained release keys sit outside the ordinary project/scan purge prefix;
  deletion revokes access and records retention rather than silently destroying
  immutable release evidence.

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
3. [x] Add S3 implementation using `boto3`.
4. [x] Add signed preview URL endpoint.
5. [x] Keep current base64 slice endpoint as compatibility fallback.
6. [x] Add data-class tags and deployable lifecycle rules for quarantine,
   derived previews, exports, and noncurrent customer-data versions.
7. [x] Add private-bucket, KMS, versioning, public-access-block, TLS-deny, and
   least-privilege runtime policy as reviewed CloudFormation.
8. [x] Add a read-only verifier for encryption, public access, ownership,
   versioning, policy, and lifecycle controls.
9. [x] Document backup, restore, legal-hold, and customer-deletion procedures.
10. [ ] Deploy and verify the controls in the approved target AWS account.
11. [ ] Configure independent backups/alerts and record restore and deletion
    drills with synthetic evidence.
12. [x] Add encrypted disposable PostgreSQL/object recovery automation in CI
    plus governed project/scan deletion and every-version operator purge.
13. [x] Add content-addressed retained release artifacts, append-only storage
    evidence, verified authenticated downloads, a separate non-expiring data
    class, revocation-aware access, and legacy materialization.
14. [x] Add organization-wide exact ordinary-prefix purge, retained-prefix
    exclusion/revocation, target disposition evidence, and fail-closed retry.

## Acceptance Criteria

- No public response includes local filesystem paths or raw object keys.
- Existing upload, slice, metadata, and reprocess tests pass on local storage.
- S3 storage can upload originals, read originals for reprocess, write previews,
  write segmentation masks, and generate signed preview URLs.
- Cross-organization tests prove signed URLs cannot be created for another
  tenant's scans.
- Docker Compose remains local-only and requires no cloud credentials.
- Retained release artifacts never expose storage keys, fail closed on object
  version/checksum/size mismatch, survive project/scan deletion, and cannot be
  downloaded after revocation.
- Organization deletion purges every ordinary project version/delete marker,
  leaves retained artifacts inaccessible pending approved policy, and remains
  locked if target storage fails.

## Repository Verification Evidence

Completed on 2026-07-16:

- 113 backend tests pass across the current repository, including S3 write
  tagging, exact-prefix every-version purge, fail-closed controls, governance,
  and recovery/deletion safety.
- `cfn-lint 1.53.0` accepted
  `infrastructure/aws/medi-private-storage.json`; the same pinned check now runs
  in CI.
- The frontend production build, PostgreSQL upgrade/rollback rehearsal at
  `20260716_0011`, and encrypted PostgreSQL/synthetic-object restore drill pass.
- Docker Compose rebuilt successfully and live readiness, authentication,
  versioned policy, value-free deletion request/cancellation, disabled operator,
  private slice access, and audit evidence checks passed.
- No cloud account was mutated and no real credentials or patient data were
  introduced. Target-account verifier output and operational drill records
  remain required evidence.
