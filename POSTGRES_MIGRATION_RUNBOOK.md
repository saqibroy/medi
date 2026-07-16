# PostgreSQL Migration And Rollback Runbook

This runbook applies to a managed PostgreSQL deployment that may contain
patient-related metadata. Treat database URLs, backup locations, and migration
logs as sensitive operational data. Do not paste credentials, patient data, or
raw `pg_dump` output into tickets, chat, CI logs, or Git.

## Safety Rule

Use forward migrations for normal releases. A production schema downgrade is an
exception and is allowed only for a reviewed, explicitly reversible migration.
The usual recovery path is: stop the failing release, roll the application back
to compatible code, then restore the verified pre-deployment backup into an
isolated target before any controlled cutover. Never run `alembic downgrade
base` against a shared or production database; it is a disposable-test-only
command and can destroy schema and data.

## Release Preflight

1. Schedule the release and identify the on-call owner and the decision maker
   for rollback.
2. Confirm the current deployed commit, target commit, and expected Alembic
   revision. `alembic heads` must report one reviewed head.
3. Confirm the production `APP_ENV=production` configuration is valid and that
   production secrets are loaded only by the deployment secret manager.
4. Place the application in the planned maintenance/write-control state if the
   migration is not proven online-safe. Stop background writers first.
5. Create an encrypted, access-controlled PostgreSQL backup and record its
   location, checksum, timestamp, database version, and Alembic revision in the
   approved change record. Keep the backup outside the database volume.
6. Restore that backup to an isolated non-production target and run the health
   and data-integrity checks appropriate to the release. A backup is not
   considered valid until it has been restored successfully.
7. Review each migration for locks, irreversible data changes, data backfills,
   and application-version compatibility. Large or destructive changes require
   a separately rehearsed expand/migrate/contract plan.

## Forward Deployment

Run these commands only from the release environment, with the database
connection injected by the secret manager. Do not echo `DATABASE_URL`.

```bash
alembic current
alembic heads
alembic upgrade head
alembic current
```

Then start the compatible backend release, verify `/health/ready`, run the
approved smoke test, and monitor database errors, migration duration, and
application error rates. Record the resulting revision and release commit.

## Rollback Decision And Recovery

1. Stop further writes and preserve relevant non-sensitive operational logs.
2. If the migration is additive and the previous application version remains
   schema-compatible, roll back the application first and assess impact.
3. For a schema or data regression, restore the pre-deployment backup to an
   isolated target, verify the expected Alembic revision and integrity checks,
   then perform the approved cutover. Do not overwrite the original evidence
   database before restore validation succeeds.
4. Use `alembic downgrade <reviewed_revision>` only when the migration's
   downgrade has been reviewed, tested on a restored copy, and the change owner
   has approved the data-loss and locking implications.
5. After recovery, verify readiness, tenant access boundaries, annotation and
   scan counts, backups, and the incident/change record. Schedule a follow-up
   for any data reconciliation.

## Disposable PostgreSQL Rehearsal

The repository contains a local-only rehearsal that creates and drops a database
named `medi_migration_qa`. It uses the default development Compose PostgreSQL
credentials and must not be pointed at production:

```bash
bash scripts/verify_postgres_migrations.sh
```

It proves the complete migration chain can upgrade to the current head,
downgrade to base, and upgrade again. GitHub Actions performs the same cycle on
an ephemeral PostgreSQL service for every pull request and push to `main`.

The separate encrypted restore rehearsal pairs PostgreSQL with a synthetic
private-object snapshot and never targets the application database:

```bash
bash scripts/verify_backup_restore_drill.sh
```

Its value-free receipt proves isolated restoration, revision/count equality,
object checksum equality, and cleanup. Production acceptance still requires an
approved managed backup/vault, separate credentials, alerts, RPO/RTO, and a
signed target-environment drill.
