# Data Lifecycle And Recovery Plan

Status: repository implementation, local verification, and pull-request checks
complete on 2026-07-16.

This increment adds repository-controlled recovery evidence and deletion
governance without inventing medical-data retention periods or granting the web
runtime destructive cloud permissions. All drills use synthetic data and
environment-variable placeholders. Target-account backup vaults, legal policy,
approved operators, and customer authorization remain deployment gates.

## Security And Governance Requirements

- [x] Store explicit, versioned organization retention/RPO/RTO policies with no
  production defaults and stable approval references.
- [x] Apply tenant-scoped legal holds to organization, project, or scan scopes;
  release a hold only through an append-only event by a different administrator.
- [x] Create data-minimized deletion requests for project or scan scopes with a
  controlled reason, value-free inventory, policy snapshot, earliest execution
  time, and two-person approval.
- [x] Block approval or execution while retention or any applicable legal hold
  applies, and re-check both immediately before destructive work.
- [x] Keep governance requests, events, holds, policies, and receipts append-only
  through ORM and database guards; audit web and operator actions without PHI.
  Signed operator audit evidence is committed in the same database transaction
  as successful receipts/events or failed-attempt events.
- [x] Revoke affected dataset releases for source withdrawal while retaining
  their immutable, already data-minimized manifests and lifecycle history.
- [x] Inventory and retain separately namespaced dataset-release artifacts,
  include their count in deletion receipts, and deny delivery after affected
  releases are revoked.
- [x] Purge local objects or every S3 object version/delete marker only through
  an explicit operator path; the application runtime policy must continue to
  exclude `s3:DeleteObjectVersion`.
- [x] Produce a checksum-protected deletion receipt containing only stable IDs,
  counts, state, timestamps, backup disposition, and approval/operator IDs.
- [x] Before annotation, scan, or project deletion cascades raw annotation
  revisions, retain one append-only value-free tombstone per annotation and
  include tombstone counts in the checksum-protected receipt.

## Recovery Automation

- [x] Add a guarded disposable PostgreSQL backup/restore drill using an
  encrypted temporary dump, isolated restore database, schema revision and row
  count verification, bounded database-readiness gate, and cleanup on failure
  or success.
- [x] Add an encrypted synthetic private-object snapshot/restore check with
  checksum and path-containment verification.
- [x] Emit a value-free machine-readable drill receipt and make failures visible
  in CI without printing database credentials, object contents, or encryption
  keys.
- [x] Document the production mapping to managed encrypted backups, independent
  vault/account credentials, alerts, approved RPO/RTO, quarterly drills, and
  backup-expiry communication.

## Product And Operator Controls

- [x] Add administrator APIs and UI for policy visibility, legal holds, deletion
  request creation, second-person approval, cancellation, and receipt review.
- [x] Add an operator-only command requiring an explicit enable flag, matching
  request-ID confirmation, approved request state, and a distinct operator.
- [x] Add tests for roles, tenants, data minimization, hold/retention blocks,
  approval separation, exact-scope purge, S3 versions, receipts, immutability,
  signed operator-audit integrity, and failure safety.

## Verification Evidence

- [x] Backend tests pass: 113 tests on 2026-07-16.
- [x] Frontend production build passes on 2026-07-16.
- [x] PostgreSQL migration rehearsal passes through `20260716_0011`, and the
  encrypted PostgreSQL/synthetic-object recovery drill restores and verifies,
  including from a newly initialized Compose volume.
- [x] Infrastructure configuration lints successfully with `cfn-lint 1.53.0`.
- [x] Rebuilt Compose services are healthy and pass live versioned-policy,
  value-free deletion-request/cancellation, audit, migration-head, and disabled
  operator checks. Legal-hold/approval/execution paths use isolated automated
  tests so the persistent demo dataset is not destructively changed.
- [x] GitHub pull-request #12 checks pass before merge, including the fresh-
  volume encrypted recovery drill.

The later annotation-history tombstone increment extends this workflow without
changing the approved destructive boundary. Direct and operator deletion now
preserve stable scope/count/summary/hash evidence while removing raw geometry
and notes; current verification is in `ANNOTATION_HISTORY_TOMBSTONE_PLAN.md`.

The retained-release-artifact increment keeps portable release evidence outside
ordinary project/scan purge prefixes. Deletion inventory and checksum-protected
receipts count retained artifacts, source withdrawal revokes their releases,
and authenticated downloads return `410` while the append-only object evidence
remains. See `RETAINED_RELEASE_ARTIFACT_PLAN.md`.

## Remaining Deployment Gates

- [ ] Approve organization-specific retention periods, RPO/RTO, lawful erasure
  exceptions, legal-hold authority, and two-person operator roles.
- [ ] Configure and verify encrypted managed PostgreSQL backups plus independent
  S3 backup/replication, vault lock/Object Lock, alerts, and restore isolation.
- [ ] Run signed target-environment restore and deletion drills with synthetic
  evidence, including every S3 version/delete marker and backup expiry.
- [ ] Obtain privacy/security/legal approval before using these controls for
  identifiable or pseudonymized patient data.
- [ ] Approve organization-deletion and exceptional-erasure behavior for
  retained release artifacts and referenced object versions.
