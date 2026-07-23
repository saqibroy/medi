# Organization-Wide Governed Deletion And Revocation

## Purpose

This tracker records the repository boundary for shutting down one customer
workspace without weakening immutable security, governance, privacy, or dataset
release evidence. It uses synthetic fixtures and controlled references only.
It does not decide whether deletion is legally required, whether a retention
exception applies, or how a real backup/provider must execute deletion.

## Implemented Repository Boundary

- [x] Add `organization` to the immutable deletion-request scope and require the
  existing versioned retention policy, exact organization UUID confirmation,
  different requester/approver identities, and a third administrator operator.
- [x] Treat every active organization/project/scan legal hold as blocking an
  organization request.
- [x] Prevent an organization request from racing an active child-scope request,
  and prevent a child request while an organization request is active.
- [x] Snapshot a value-free organization inventory covering users, sessions,
  projects, scans, labels, annotations/history/tombstones, masks, releases,
  retained artifacts, governance/privacy/audit evidence, external-AI approvals,
  object references, cache entries, and queue jobs.
- [x] Lock the organization as `deletion_in_progress` and revoke all sessions
  before external object deletion. Authentication and login require an active
  organization as well as an active user.
- [x] Leave a failed organization purge locked and sessionless. The same
  approved request can retry the idempotent exact-prefix purge; it cannot
  silently reopen the workspace.
- [x] Purge all ordinary organization project-prefix object versions and delete
  markers while excluding the separately namespaced retained-release prefix.
- [x] Remove scans, labels, annotations, raw annotation history, masks, and
  sessions; retain value-free annotation-history tombstones.
- [x] Tombstone projects, user identities, and the organization; deactivate all
  users and replace credentials with an unusable value.
- [x] Revoke every dataset release, external-AI provider/data-flow approval, and
  processing-record version through append-only events.
- [x] Retain append-only audit, governance, privacy-case, release-manifest, and
  release-artifact evidence. Retained artifacts remain private and inaccessible
  because the releases and organization are revoked.
- [x] Add a checksum-covered `target_dispositions` receipt field and expose only
  controlled status/count values.
- [x] Add administrator UI for organization holds and deletion requests.
- [x] Add Alembic migration `20260723_0017` and preserve the append-only
  deletion-request trigger through the SQLite constraint rebuild.

## Target Dispositions

| Target | Repository behavior |
| --- | --- |
| PostgreSQL working data | Deleted or data-minimized; immutable evidence retained |
| User sessions | Revoked before purge, then removed |
| Redis rate-limit counters | HMAC-derived peer counters are not organization-scoped and expire by bounded TTL |
| Background queue | Explicitly recorded as `not_configured`; no repository job rows exist yet |
| Ordinary private objects | Every scoped version/delete marker is purged and absence verified |
| Retained release objects | Access revoked; artifacts retained pending approved retention/exception policy |
| External AI | All approvals revoked; no provider network-call adapter is implemented |
| Backups | Receipt records policy expiry; it does not claim immediate vault erasure |

Any future queue, cache, export store, provider adapter, or object namespace must
update this enumeration and the organization deletion tests before deployment.

## Verification

- [x] Focused lifecycle tests cover tenant scoping, organization inventory,
  child-hold blocking, three-person execution, session invalidation, identity
  tombstoning, working-row/object purge, retained-artifact survival, release and
  external-AI revocation, receipt integrity, and cross-tenant continuity.
- [x] A simulated object-storage failure proves fail-closed locking and safe
  retry of the same approved request.
- [x] Frontend TypeScript/Vite production build passes.
- [x] PostgreSQL upgrade/downgrade/upgrade rehearsal passes at
  `20260723_0017`.
- [x] Full backend suite passes all 157 tests; backend compilation, external-AI
  policy, operator-runbook, container-hardening, and diff checks pass.
- [x] Encrypted PostgreSQL/synthetic-object recovery restores migration
  `20260723_0017` with verified table/object checksums.
- [x] Rebuilt database, Redis, backend, and frontend are healthy at
  `20260723_0017`; live/readiness, frontend HTTP, container-hardening, login,
  project/governance/session reads, and OpenAPI organization-scope probes pass.
- [ ] Record the pull-request, merge, and post-merge `main` evidence before
  closing this increment.

## Deployment And Policy Gates

- [ ] Approve organization deletion, retained-release, exceptional-erasure,
  audit/privacy evidence, and backup-expiry rules with privacy/legal/security.
- [ ] Prove the separately authorized operator identity, maintenance/write
  isolation, exact target bucket scope, every-version deletion, and receipt
  custody in the target environment.
- [ ] Configure managed backup/vault expiry and obtain provider-side deletion
  evidence where an approved external processor actually received data.
- [ ] Run a signed synthetic organization-deletion exercise in the target
  account and verify database, object versions, sessions, caches, queues,
  exports, backups, and every configured external target.

These controls are an engineering foundation, not legal approval or automatic
GDPR compliance.

## Next Repository Task

Implement the planned background ingestion job/worker boundary for large
studies, and extend this deletion target adapter so organization/project/scan
shutdown cancels or drains scoped jobs before any queue is enabled.
