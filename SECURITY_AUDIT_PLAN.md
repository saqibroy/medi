# Security Audit Implementation Plan

Status: Implementation boundary complete; production gates remain

This plan is the recovery point for the Phase 4 immutable security-audit work.
Audit records must provide operational accountability without becoming a
second store of patient data, credentials, or clinical free text.

## Current Implementation Boundary

- [x] Add a tenant-scoped, append-only security-event table with actor user and
  session identifiers, action, result, target type/ID, timestamp, request ID,
  and a strictly allowlisted details object.
- [x] Add keyed integrity hashes so exported or copied events can be verified.
- [x] Reject audit-event updates and deletes in both the ORM and database.
- [x] Add an admin-only, organization-scoped listing API. Do not add update or
  delete endpoints.
- [x] Record login success/failure, logout, medical-image intake and reprocess
  decisions, sensitive pixel/mask reads, signed-URL issuance, exports, project
  and label administration, annotation changes/reviews/deletions, and mask
  changes/deletions.
- [x] Record retention-policy, legal-hold, deletion-request approval/cancellation,
  and successful operator execution using only stable IDs and controlled scalar
  details; governance payloads, inventories, and receipts do not enter audit
  rows.
- [x] Prove tenant isolation, non-admin denial, safe-field behavior, integrity
  verification, and database-level immutability with automated tests.
- [x] Rebuild and run the complete application, rehearse migrations against
  PostgreSQL, and perform authenticated live smoke checks before publication.

## Data-Minimization Rules

Audit events must never contain:

- bearer tokens, token digests, passwords, cookies, or secrets;
- DICOM values removed or rejected by de-identification;
- uploaded filenames or object-storage keys;
- image pixels, mask bytes, annotation coordinates, or scan metadata;
- email addresses, free-text descriptions, annotation notes, or request bodies;
- raw network addresses or user-agent strings.

Identifiers already used for authorization boundaries may be recorded as UUIDs.
The `details` object is action-specific and accepts only documented keys with
bounded scalar values.

## Verification Evidence

Completed on 2026-07-16:

- 82 backend tests passed, including priority route emission, tenant isolation,
  safe-field exclusion, keyed-hash verification, and ORM/database immutability.
- The frontend TypeScript/Vite production build passed.
- PostgreSQL completed upgrade to head, downgrade to base, and a second upgrade
  to migration `20260716_0009`.
- Docker Compose rebuilt successfully; database, backend, and frontend health
  checks passed.
- Live authenticated smoke checks proved sensitive slice-read audit creation,
  organization-admin retrieval, correlation/session identifiers, non-admin
  denial, and absence of bearer/email values.
- A direct PostgreSQL `UPDATE` against the live audit table was rejected by the
  append-only trigger.

The later data-lifecycle increment adds audited governance routes and operator
execution without changing the ledger's allowlisted, payload-free boundary;
signed success evidence is transactionally committed with the deletion receipt
and lifecycle events, while failed attempts append signed error evidence. Its
full evidence is tracked in `DATA_LIFECYCLE_RECOVERY_PLAN.md`.

The external-AI governance increment adds explicit signed audits for provider
and project-flow creation/revocation plus every dry-run authorization decision.
Only stable targets, controlled purpose/reason, class count, provider version,
and allowed/denied result enter audit details; provider contracts, prompts,
medical payloads, credentials, and model responses do not. See
`EXTERNAL_AI_GOVERNANCE_PLAN.md`.

The privacy-operations increment audits processing-record creation/revocation
and every privacy-request transition. Audit details are limited to stable target
IDs plus controlled policy version, purpose, scope, request type, workflow
status, and reason codes. Raw or digested subject references, case/evidence
references, identity material, correspondence, and delivered data never enter
the audit ledger. See `PRIVACY_OPERATIONS_PLAN.md`.

Its local verification added signed-audit assertions to the 129-test backend
suite and an authenticated synthetic smoke proving the request-create audit is
present while the raw subject reference is absent from the API response and
audit details.

## Remaining Production Gates

- [ ] Export events to independently controlled append-only/WORM-capable
  storage and verify the keyed hashes after export.
- [ ] Approve an audit retention period, archival access process, and deletion
  exception policy with legal/security stakeholders.
- [ ] Replace annotation-history cascade deletion with retained tombstones or
  durable audit references before describing annotation history as immutable.
- [ ] Add safe network context only after a trusted-proxy policy and privacy
  review define what may be retained.
- [ ] Monitor integrity verification and alert on gaps or failed audit writes.
