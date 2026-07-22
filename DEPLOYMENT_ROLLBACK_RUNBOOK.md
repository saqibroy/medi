# Deployment And Rollback Runbook

Status: repository release procedure defined; target platform commands,
approvers, thresholds, maintenance controls, and exercise evidence remain
deployment inputs.

This procedure covers application releases. Database-specific details remain in
[POSTGRES_MIGRATION_RUNBOOK.md](POSTGRES_MIGRATION_RUNBOOK.md), storage changes
in [STORAGE_OPERATIONS_RUNBOOK.md](STORAGE_OPERATIONS_RUNBOOK.md), and common
privacy/evidence rules in [OPERATOR_RUNBOOKS.md](OPERATOR_RUNBOOKS.md).

## Release Record

Before changing state, record:

- change ID, environment, release owner, operations owner, approver, rollback
  decision maker, window, and communications channel;
- current and target Git commits, immutable backend/frontend image digests,
  expected Alembic revision, configuration version, and infrastructure version;
- reviewed changes to data flows, authorization, DICOM/NIfTI handling,
  retention/deletion, external AI, secrets, dependencies, and migrations;
- approved success/rollback thresholds, monitoring window, RPO/RTO, backup and
  restore references, and previous compatible artifacts.

Do not record credentials, environment-file contents, patient data, object
names, database rows, signed URLs, or raw error payloads.

## Preflight

1. Require green CI for the exact commit, including tests, migrations, build,
   secret/dependency scans, and high/critical container scans.
2. Build once and deploy immutable digests. Do not rebuild different artifacts
   between staging, approval, and production.
3. Confirm the target uses approved TLS ingress, managed PostgreSQL/Redis,
   private KMS-encrypted storage, secret delivery, backups, monitoring, and
   workload identities.
4. Validate that production configuration uses `APP_ENV=production`,
   `SEED_DEMO_DATA=false`, secure/distinct application secrets, exact HTTPS
   origins, secure cookies, encrypted Redis, private S3, and KMS. Do not print
   configuration values.
5. Confirm `EXTERNAL_AI_ENABLED=false` unless the exact provider/data flow is
   separately approved. Confirm `DATA_DELETION_OPERATOR_ENABLED=false` in the
   web runtime.
6. Review migrations for locking, compatibility, destructive changes, and
   reversibility. Create and restore-test an encrypted backup according to the
   PostgreSQL runbook.
7. Confirm the previous application artifacts and compatible configuration are
   available. A rollback plan that depends on rebuilding an old branch is not
   ready.
8. Pause conflicting deletion, restore, key-rotation, and migration work.
9. Confirm the target workload runs backend/frontend as the reviewed non-root
   UIDs with read-only roots, no added capabilities, no privilege escalation,
   and only approved temporary/storage writes. Review ownership migration and
   rollback evidence before replacing any older root-running workload; see
   `CONTAINER_HARDENING_PLAN.md`.

## Deploy

1. Apply the target maintenance/write-control procedure if the change is not
   proven online-safe.
2. Run migrations exactly once from the approved release environment, then
   verify `alembic current` matches the reviewed head. Medi's container startup
   also runs `alembic upgrade head`; the target rollout must prevent multiple
   uncoordinated migration executors and start only schema-compatible images.
3. Deploy backend instances by immutable digest. Keep unready instances out of
   traffic until `/health/live` and `/health/ready` pass.
4. Deploy the frontend by immutable digest and verify `/health` plus asset load.
5. Restore traffic gradually according to the target platform procedure.
6. Hold the approved observation window. Do not declare success immediately
   after probes turn green.

Provider-specific deploy commands are intentionally absent. Add reviewed target
commands to the approved operations system after the platform, account,
workload identities, and traffic controls exist.

## Privacy-Safe Smoke Test

Use a dedicated synthetic tenant and fixture. Verify:

1. backend live/ready and frontend health;
2. login, session cookie/CSRF behavior, logout, and one bounded rate-limit test;
3. organization/role isolation and cross-tenant denial;
4. synthetic scan listing/view, authorized derived preview, and annotation
   create/update/delete as applicable to the release;
5. a safe audit event and its integrity verification;
6. private storage encryption/tag/version behavior when storage changed;
7. no unexpected external egress and no patient-related values in logs/errors.

Record only fixture IDs, request/audit IDs, statuses, counts, versions, and
checksums.

## Rollback Decision

Rollback when an approved threshold is crossed or when authorization,
confidentiality, integrity, migration, tenant isolation, audit, or medical-image
safety cannot be demonstrated. The decision maker records the reason and time.
Activate [SECURITY_INCIDENT_RUNBOOK.md](SECURITY_INCIDENT_RUNBOOK.md) if the
release may have exposed or altered data improperly.

## Rollback Procedure

1. Stop rollout and remove the failing version from new traffic. Preserve image
   digests, configuration versions, request IDs, alerts, and safe logs.
2. Stop incompatible writes/background work. Do not delete the failed
   deployment or overwrite source data before evidence and recovery needs are
   assessed.
3. If the schema remains backward-compatible, deploy the previous immutable
   application/configuration artifacts and verify probes and smoke tests.
4. If schema or data changed, follow
   [POSTGRES_MIGRATION_RUNBOOK.md](POSTGRES_MIGRATION_RUNBOOK.md). Prefer
   compatible code rollback or forward repair. Run `alembic downgrade` only for
   an explicitly reviewed, rehearsed downgrade; otherwise restore the verified
   pre-release backup into an isolated target before controlled cutover.
5. If storage/infrastructure changed, restore the prior reviewed policy without
   weakening encryption, public-access, versioning, retention, tenant, or legal
   hold controls. Verify with synthetic data.
6. Restore traffic gradually and re-run the full privacy-safe smoke test.
7. Confirm audit continuity, backup continuity, data reconciliation, achieved
   RPO/RTO, and incident/change status before closure.

## Local Rehearsal Only

The following verifies the development stack and disposable recovery paths. It
is not a production deployment or rollback command.

```bash
docker compose up --build --detach
docker compose ps
curl --fail --silent --show-error http://localhost:8000/health/live
curl --fail --silent --show-error http://localhost:8000/health/ready
curl --fail --silent --show-error http://localhost:8080/health
python3 scripts/verify_container_hardening.py
bash scripts/verify_postgres_migrations.sh
bash scripts/verify_backup_restore_drill.sh
```

## Closure

Record deployed/rolled-back digests, configuration and Alembic versions,
approvals, smoke evidence, monitoring interval, recovery evidence, deviations,
and follow-ups. A successful local or CI rehearsal does not complete the target
deployment gate; retain signed target exercise evidence separately.
