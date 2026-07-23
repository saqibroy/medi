# Immutable Dataset Release Plan

Status: repository implementation and verification complete. Remaining items
below require approved deployment infrastructure or policy decisions.

This increment creates reproducible, project-scoped dataset releases without
copying patient-related free text or exposing private object-storage keys. A
release is a permanent snapshot; later annotation, label, scan, or mask changes
must not alter its stored manifest or checksum.

## Security And Data-Minimization Requirements

- [x] Scope every release through the signed-in user's organization and require
  administrators to create, supersede, or revoke releases.
- [x] Include only ready scans and approved annotations; never include
  quarantined images, annotation notes, patient metadata, creator names, raw
  storage paths, pixels, or external-AI content.
- [x] Snapshot label taxonomy, approved annotation geometry/review evidence,
  lineage digests, scan originals, and approved segmentation masks.
- [x] Record content SHA-256, complete manifest SHA-256, object versions,
  object checksums, byte sizes, metadata-profile versions, and export/tool
  versions with deterministic canonical JSON.
- [x] Keep release and lifecycle rows append-only at both ORM and database
  layers; superseding and revocation must append events rather than mutate or
  delete history.
- [x] Audit release creation, listing, reading, superseding, and revocation with
  stable identifiers and no manifest payloads in the audit ledger.
- [x] Create a separately classified, content-addressed private artifact from
  canonical release JSON and verify its object version/checksum/size on every
  authenticated download.
- [x] Preserve superseded artifacts, deny revoked artifact delivery, and keep
  mutable live export responses out of retained storage.

## Implementation

- [x] Add release and lifecycle-event models plus a reversible migration.
- [x] Add storage snapshot metadata for local and versioned S3 objects.
- [x] Add deterministic manifest creation, status derivation, and tenant-safe
  release services.
- [x] Add create/list/read/revoke APIs and browser controls.
- [x] Add automatic artifact creation, idempotent legacy materialization,
  authenticated download, append-only artifact metadata, and browser controls.
- [x] Add tests for immutability, monotonic versions, lineage, checksums,
  superseding/revocation, authorization, tenant isolation, and data minimization.

## Verification Evidence

- [x] Backend tests pass: 106 tests on 2026-07-16.
- [x] Frontend production build passes on 2026-07-16.
- [x] PostgreSQL upgrade/downgrade rehearsal passes through revision
  `20260716_0010` on 2026-07-16.
- [x] Infrastructure configuration lints successfully with `cfn-lint 1.53.0`.
- [x] Rebuilt Compose services are healthy and pass a live create, supersede,
  retrieve, mutate-live-data, checksum-stability, and revoke smoke test.
- [x] GitHub pull-request checks pass on PR #11 before merge.
- [x] The retained artifact follow-on is implemented and locally verified in
  `RETAINED_RELEASE_ARTIFACT_PLAN.md`.

## Remaining Deployment Gates

- [ ] Verify real S3 VersionId capture and checksum behavior against the
  approved target bucket and KMS policy.
- [x] Define and implement retained canonical-JSON release artifact packaging,
  authorization, integrity-checked download, and storage lifecycle semantics.
- [ ] Configure and prove long-term S3 Object Lock or independent WORM
  replication when the approved customer release policy requires it.
- [ ] Approve retention, legal-hold, source-withdrawal, and organization-deletion
  behavior for releases and their referenced object versions.
