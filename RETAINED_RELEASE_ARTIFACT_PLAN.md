# Retained Private Dataset Release Artifact Plan

Status: repository implementation complete on 2026-07-23; target deployment and
policy evidence remain open.

This increment turns each immutable dataset release into a portable,
content-addressed JSON artifact without retaining every mutable COCO, CSV,
YOLO, or native export response. The artifact is sensitive annotation data: it
must remain private even though patient metadata, free text, filenames, storage
keys, creator names, and image pixels are excluded by the release builder.

## Implemented Boundary

- [x] Create one canonical `portable_manifest` artifact automatically with each
  new release; administrators can idempotently materialize artifacts for legacy
  releases.
- [x] Store artifacts under the organization/project-scoped
  `retained-release/.../release-artifact/...` namespace, outside ordinary
  project and scan purge prefixes.
- [x] Derive the object key from the release ID and manifest SHA-256, tag S3
  writes as `dataset-release`, and never return the private storage key.
- [x] Record object version, checksum, byte size, media/schema versions, actor,
  and timestamp in an append-only database row protected by ORM guards and
  PostgreSQL/SQLite triggers.
- [x] Re-read and verify the recorded object version, SHA-256, and byte size
  before every authenticated download; fail closed on absence or tampering.
- [x] Keep superseded artifacts downloadable for reproducibility, retain
  revoked artifacts as controlled evidence, and deny downloads after
  revocation or source withdrawal.
- [x] Audit artifact materialization and download using only stable release
  identifiers; artifact bytes, manifests, storage keys, and filenames never
  enter the audit ledger.
- [x] Include retained artifact counts in deletion inventory and receipts.
  Project/scan deletion removes normal object prefixes, revokes affected
  releases, and preserves the separately namespaced artifact.
- [x] Add browser controls for checksum display, download, revocation state, and
  legacy artifact materialization.
- [x] Extend the fail-closed route matrix to all 90 API routes and cover both
  artifact routes with cross-tenant opaque `404` tests.

## Storage Lifecycle

- `export` remains the class for transient generated artifacts and follows its
  separately approved expiry.
- `dataset-release` is a distinct retained class. The deployable bucket policy
  accepts the tag, while the lifecycle verifier requires that no current or
  noncurrent automatic-expiration rule targets it.
- Application project/scan purge prefixes cannot reach retained-release keys.
- Revocation changes access, not artifact bytes or append-only metadata.
- Organization deletion, approved retention duration, legal holds, and any
  exceptional erasure behavior still require an explicit policy decision.

## Verification Evidence

- [x] Focused release, lifecycle, storage, S3-control, and authorization suite:
  33 tests passed.
- [x] Frontend TypeScript/Vite production build passed.
- [x] SQLite completed upgrade to migration `20260723_0016`, downgrade to base,
  and a second upgrade to head.
- [x] Full backend suite: 155 tests passed.
- [x] PostgreSQL completed upgrade to `20260723_0016`, downgrade to base, and a
  second upgrade to head; pool and statement-timeout verification passed.
- [x] External-AI egress, operator-runbook, CloudFormation lint, repository
  diff, and container-hardening verifiers passed.
- [x] Rebuilt Compose database, Redis, backend, and frontend are healthy at
  migration `20260723_0016`; live/readiness and frontend HTTP checks passed.
- [x] Authenticated synthetic smoke created an artifact, re-read canonical
  bytes, verified SHA-256, revoked the release, observed download `410`, and
  confirmed minimized success/failure audit events.

## Deployment Gates

- [ ] Verify actual S3 VersionId and checksum capture against the approved
  versioned bucket and KMS key.
- [ ] Configure and prove S3 Object Lock or independently controlled WORM
  replication if the approved release policy requires it.
- [ ] Approve release-artifact retention, legal-hold, source-withdrawal,
  organization-deletion, backup, and exceptional-erasure rules.
- [ ] Run a target exercise proving that revoked artifacts cannot be delivered
  and retained artifacts survive the intended project/scan deletion workflow.

These controls are an engineering foundation, not a lawful basis for retaining
health-related data and not automatic GDPR compliance.

## Next Repository Task

Design organization-wide governed deletion and revocation, including
session/cache/queue, retained-release, backup, and target-service enumeration,
without weakening immutable evidence or inventing an unapproved retention
policy.
