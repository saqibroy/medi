# Annotation History Tombstone Plan

Status: repository boundary complete on 2026-07-22

This tracker closes the deletion-retention gap for annotation revision history.
Raw history can contain geometry and free-text notes, so it must still be
deleted when an approved annotation, scan, or project deletion executes. Medi
now retains a separate value-free tombstone instead of retaining those values.

## Implemented Boundary

- [x] Create one durable tombstone for every deleted annotation, including an
  annotation with no revision entries.
- [x] Retain only organization, project, scan, annotation, deletion actor/source,
  entry count, controlled action counts, changed-field names, bounded
  timestamps, and keyed SHA-256 integrity evidence.
- [x] Exclude geometry, labels, notes, creator/reviewer names, mask bytes,
  filenames, storage keys, medical metadata, and other history values.
- [x] Create the tombstone in the same database transaction as direct
  annotation deletion.
- [x] Create tombstones for every affected annotation before approved project
  or scan lifecycle deletion cascades raw history.
- [x] Record tombstone counts in lifecycle inventories and checksum-protected
  deletion receipts.
- [x] Keep frozen dataset-release manifests unchanged after live annotation and
  history deletion.
- [x] Reject tombstone updates and deletes through SQLAlchemy and PostgreSQL/
  SQLite database triggers.
- [x] Add migration `20260722_0015` with a complete PostgreSQL and SQLite
  upgrade/downgrade path.

## Verification Evidence

Completed locally on 2026-07-22 using synthetic records only:

- 153 backend tests passed, including direct deletion, lifecycle deletion,
  value minimization, keyed integrity, immutable ORM/database guards, and
  frozen release stability.
- The frontend TypeScript/Vite production build passed.
- PostgreSQL completed upgrade to `20260722_0015`, downgrade to base, and a
  second upgrade to `20260722_0015`; pool and statement-timeout checks passed.
- Backend compilation, external-AI egress verification, operator-runbook
  verification, and `git diff --check` passed.
- The rebuilt Compose stack is healthy at PostgreSQL migration head
  `20260722_0015`; backend live/readiness, frontend HTTP `200`, and the
  container-hardening runtime verifier passed.

These controls preserve engineering evidence; they do not define a lawful
retention period or override an approved erasure, legal-hold, or backup policy.
Independent WORM retention and target operator evidence remain deployment
gates.

## Follow-on

Retained private dataset-release artifacts are now implemented and evidenced in
`RETAINED_RELEASE_ARTIFACT_PLAN.md`. Organization-wide governed deletion now
retains the same value-free tombstones while removing tenant working data; see
`ORGANIZATION_DELETION_PLAN.md`.
