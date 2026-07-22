# Service Degradation Runbook

Status: repository response paths defined; target topology, commands, alerts,
failover behavior, thresholds, and exercise evidence remain deployment inputs.

Read [OPERATOR_RUNBOOKS.md](OPERATOR_RUNBOOKS.md) first. Never bypass tenant,
privacy, encryption, rate-limit, or audit controls to restore availability.

## Triage

1. Open an incident record; assign the operations lead and decision maker.
2. Record UTC start time, environment, affected services, release/image digest,
   request IDs, health results, and safe error categories.
3. Check `/health/live` and `/health/ready`. Remember that readiness checks only
   the database; a green response does not prove Redis or object storage.
4. Determine whether the event is degradation, a security incident, or both.
   If unauthorized activity or integrity loss is plausible, also activate
   [SECURITY_INCIDENT_RUNBOOK.md](SECURITY_INCIDENT_RUNBOOK.md).
5. Freeze unrelated deploys, migrations, deletion execution, and key changes
   until the failure domain is understood.

## Failure Matrix

| Service | Expected Medi behavior | Immediate safe action | Recovery proof |
| --- | --- | --- | --- |
| PostgreSQL | Liveness may remain 200; readiness returns 503 and database-backed routes fail; pool acquisition and over-time statements fail within configured bounds | Remove the backend from ready traffic, stop writers/background work, preserve DB evidence, activate managed DB failover/recovery | Ready 200, expected Alembic revision, approved pool/timeout values, safe integrity/count checks, tenant smoke test |
| Redis rate limiter | Readiness may remain 200; login and protected expensive routes return 503 because production rate limiting fails closed | Keep fail-closed behavior, pause affected workflows, restore the approved encrypted Redis service | Login and one approved expensive-route test no longer return limiter-unavailable; HA/alert state verified |
| Private S3/KMS | Health probes may remain green; upload, preview, mask, release, export, or deletion operations can fail | Pause affected storage workflows, preserve object/version and KMS event references, do not switch production to local storage | Synthetic tenant-scoped put/read/signed-preview check, encryption/tag/version evidence, cross-tenant denial |
| Backend process | Liveness/readiness fail or time out | Remove unhealthy instances from traffic; inspect safe platform status/log fields; restart/redeploy reviewed image | Sustained live/ready success and approved end-to-end smoke tests |
| Frontend | Frontend health/UI fails while API may remain healthy | Serve status through approved channel; roll back/redeploy reviewed static image | Frontend health 200, asset load, login page, and one non-sensitive UI flow |

Redis currently provides shared rate-limit counters; Medi does not yet run a
general background queue on Redis. If a future queue is introduced, add its
pause, replay, idempotency, dead-letter, and privacy-safe backlog procedures
before claiming queue-outage coverage.

## PostgreSQL Degradation

1. Confirm failure from target monitoring and `/health/ready`; do not rely on
   liveness.
2. Correlate `database_slow_query`, `database_unavailable`, managed-database,
   and readiness signals using request IDs and safe time windows. Do not enable
   SQL, parameter, schema-name, database-error, or data-value logging during
   triage.
3. Stop routing new work to unready backends and stop any independent writers.
4. Do not run migrations, broad diagnostics, or automatic retry storms during
   an unstable database event.
5. Check whether replica/worker scaling can exceed the approved connection
   budget: `replicas × workers × (pool size + overflow)`. Preserve headroom for
   migrations, monitoring, failover, and approved operators.
6. Use the target managed failover procedure. For restore or migration-related
   failure, follow [POSTGRES_MIGRATION_RUNBOOK.md](POSTGRES_MIGRATION_RUNBOOK.md).
7. Restore into an isolated target first if corruption or data loss is possible.
8. Before traffic returns, verify revision, connectivity, audit triggers,
   organization/role isolation, scan/annotation counts or checksums using safe
   aggregate evidence, approved pool/timeout settings, and backup continuity.

## Redis Degradation

1. Confirm encrypted Redis connectivity and service status through the target
   control plane; never print `RATE_LIMIT_REDIS_URL`.
2. Expect 503 on login, release/revoke, governance, upload/reprocess/export, and
   other routes selected by the rate-limit middleware.
3. Do not set `RATE_LIMIT_BACKEND=memory` in production. That would create
   inconsistent per-process enforcement and weaken abuse controls.
4. Restore/fail over the approved Redis service. Treat counters as ephemeral;
   do not import untrusted counter data or customer values.
5. Verify the encrypted endpoint, authentication, availability alerts, 503
   recovery, and 429 behavior with a bounded synthetic test.

## Private Storage Or KMS Degradation

1. Identify the affected operation and tenant-safe Medi IDs. Do not list or
   download broad prefixes.
2. Pause uploads, reprocessing, previews, masks, releases, exports, and deletion
   execution as applicable using the approved traffic/workflow control.
3. Preserve target policy/configuration versions and safe provider event IDs.
   Do not weaken public-access blocking, encryption, tenant prefixes, or KMS
   requirements to recover availability.
4. Use the provider procedure referenced by
   [STORAGE_OPERATIONS_RUNBOOK.md](STORAGE_OPERATIONS_RUNBOOK.md). If KMS access
   may be compromised, also use [KEY_COMPROMISE_RUNBOOK.md](KEY_COMPROMISE_RUNBOOK.md).
5. Test with a new synthetic object in an isolated prefix. Confirm KMS
   encryption, data-class tag, versioning, checksum, authorized read, signed
   preview expiry, and cross-tenant denial before resuming production workflows.

## Local Compose Diagnostic Only

These commands inspect the development stack. They are not production failover
or recovery commands and must not be pointed at a target environment.

```bash
docker compose ps
curl --fail --silent --show-error http://localhost:8000/health/live
curl --fail --silent --show-error http://localhost:8000/health/ready
curl --fail --silent --show-error http://localhost:8080/health
```

## Close And Follow Up

Record cause, affected interval/services, safe impact, recovery/failover steps,
achieved RPO/RTO, data reconciliation, alert gaps, approvals, and residual work.
Run a synthetic target exercise for database, Redis, and storage failure before
processing sensitive data and after material topology changes.
