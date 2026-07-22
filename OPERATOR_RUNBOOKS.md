# Operator Runbook Index

Status: repository procedures implemented; target contacts, provider commands,
approved thresholds, and exercise evidence must be supplied by each deployment.

These runbooks support Medi environments that may contain patient-related
medical images. They do not authorize sensitive-data processing, replace a
target incident plan, or make legal notification decisions. Until the Phase 4
deployment gates are approved, exercises must use **synthetic or properly anonymized data only**.

## Runbooks

- [SECURITY_INCIDENT_RUNBOOK.md](SECURITY_INCIDENT_RUNBOOK.md): triage,
  containment, evidence preservation, breach-assessment handoff, recovery, and
  exercises.
- [SERVICE_DEGRADATION_RUNBOOK.md](SERVICE_DEGRADATION_RUNBOOK.md): database,
  Redis, private storage, backend, and frontend degradation.
- [KEY_COMPROMISE_RUNBOOK.md](KEY_COMPROMISE_RUNBOOK.md): application secrets,
  database/Redis credentials, workload identity, and KMS key response.
- [DEPLOYMENT_ROLLBACK_RUNBOOK.md](DEPLOYMENT_ROLLBACK_RUNBOOK.md): release
  preflight, controlled migrations, verification, rollback, and evidence.
- [POSTGRES_MIGRATION_RUNBOOK.md](POSTGRES_MIGRATION_RUNBOOK.md): detailed
  database migration and restore safety.
- [STORAGE_OPERATIONS_RUNBOOK.md](STORAGE_OPERATIONS_RUNBOOK.md): private S3/KMS
  deployment, verification, recovery, and deletion.
- [CONTAINER_HARDENING_PLAN.md](CONTAINER_HARDENING_PLAN.md): application
  identities, writable-path boundary, local verification, ownership migration,
  and remaining target runtime gates.

## Target Worksheet

Before production use, store the following in the approved operations system,
not in Git. An unset field blocks the associated production exercise or release.

| Required target input | Approved value |
| --- | --- |
| Environment and service inventory | `<target-owned>` |
| Operations incident commander/on-call | `<target-owned>` |
| Security incident lead | `<target-owned>` |
| Controller/processor contact | `<target-owned>` |
| Privacy/DPO and legal decision owner | `<target-owned>` |
| Clinical/research escalation owner | `<target-owned>` |
| Customer communications owner | `<target-owned>` |
| Approved incident and change systems | `<target-owned>` |
| Monitoring and immutable evidence locations | `<target-owned>` |
| Ingress traffic-control procedure | `<target-owned>` |
| Database, Redis, storage, KMS, and secret-manager procedures | `<target-owned>` |
| Managed database connection budget and application replica/worker count | `<target-owned>` |
| Approved database pool, acquisition, statement, slow-query, and alert thresholds | `<target-owned>` |
| Approved RPO/RTO, severity, and rollback thresholds | `<target-owned>` |
| Backup/restore and break-glass owners | `<target-owned>` |

## Common Safety Rules

1. Assign one incident/change ID, UTC start time, operator, decision maker, and
   affected environment before changing state.
2. Never put patient identifiers, DICOM metadata values, pixels, annotation
   notes, filenames, object keys, database rows, request bodies, credentials,
   cookies, tokens, signed URLs, or key material in tickets, chat, commands,
   screenshots, or Git.
3. Use stable Medi IDs, server-generated request IDs, service names, UTC time
   ranges, counts, checksums, version/revision IDs, and controlled reason codes.
4. Preserve evidence before destructive containment when it is safe to do so.
   Do not copy sensitive data into a less protected system for convenience.
5. Use least-privilege target identities and separately approved break-glass
   access. Record who authorized and used elevated access.
6. Keep `EXTERNAL_AI_ENABLED=false` unless the exact provider and dataset flow
   have independent approval. Do not send incident samples to an external AI.
7. Prefer reversible traffic isolation, credential disablement, or workload
   scaling over deleting resources. Never test recovery by overwriting the only
   production copy.
8. Do not claim recovery until health, tenant isolation, audit continuity, and
   the affected data flow have been verified.

## Common Health Checks

Run these against the approved target hostname. They contain no credentials and
must not include query strings.

```bash
curl --fail --silent --show-error https://<target-host>/health/live
curl --fail --silent --show-error https://<target-host>/health/ready
```

`/health/live` proves only that the API process responds. `/health/ready`
currently proves API-to-database connectivity. It does not test Redis, private
object storage, KMS, backups, external monitoring, or end-to-end user flows.

## Minimum Evidence Record

Retain the following in the approved system:

- incident/change ID, UTC timeline, environment, service, release commit and
  image digest;
- approved operators and decision makers;
- alert IDs, request IDs, health statuses, safe error categories, counts, and
  checksums;
- containment, recovery, rollback, and verification decisions with reasons;
- Alembic revision, backup/restore job references, storage/KMS version
  references, and cleanup confirmation where applicable;
- privacy/legal assessment reference and notification outcome supplied by the
  responsible owner, without copying case evidence into engineering records;
- deviations, residual risk, follow-up owner, and due date.

Run the repository structure check after editing any runbook:

```bash
.venv/bin/python scripts/verify_operator_runbooks.py
```

This check proves that the required procedures, warnings, and local links are
present. It does not prove a target deployment, exercise, approval, or legal
outcome.
