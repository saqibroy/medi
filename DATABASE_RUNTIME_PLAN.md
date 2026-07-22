# Database Runtime Safety Plan

Status: repository-controlled runtime protections complete. Target capacity,
managed-database limits, alert routing, and production exercise evidence remain
deployment gates.

These controls protect application availability and reduce the impact of
runaway PostgreSQL work. They do not replace query review, target sizing,
managed-database monitoring, backups, or incident procedures.

## Requirements

- [x] Bound the steady and overflow connection count for each backend process.
- [x] Fail connection acquisition within a configured time instead of waiting
  indefinitely when the application pool is exhausted.
- [x] Apply a PostgreSQL server-side statement timeout to every application
  connection.
- [x] Detect completed slow queries at a threshold below the statement timeout.
- [x] Log only the operation class, duration, and request correlation ID; never
  log SQL text, bind parameters, table/column names, database URLs, exception
  text, or patient-related values.
- [x] Convert SQLAlchemy failures, including pool/statement timeouts, to a
  generic `503` and value-free `database_unavailable` event before a default
  server traceback can expose exception content.
- [x] Require explicit production values and validate bounded ranges before
  migrations or application startup.
- [x] Keep SQLite as a development/test fallback without pretending it proves
  PostgreSQL statement-timeout behavior.

## Configuration

- `DATABASE_POOL_SIZE`: steady connections per backend process, range 1-50.
- `DATABASE_MAX_OVERFLOW`: temporary connections per process, range 0-50.
- `DATABASE_POOL_TIMEOUT_SECONDS`: maximum pool checkout wait, range 1-60.
- `DATABASE_STATEMENT_TIMEOUT_MS`: PostgreSQL statement limit, range
  100-300000.
- `DATABASE_SLOW_QUERY_THRESHOLD_MS`: completed-query warning threshold, range
  10-300000 and strictly below the statement timeout.

The maximum application connections are approximately:

`backend replicas × worker processes × (pool size + max overflow)`

Target owners must leave capacity for migrations, operators, monitoring,
failover, and other approved database clients.

## Verification Evidence

- [x] All 148 backend tests pass, including settings, engine-construction,
  SQLite-boundary, generic database-failure handling, and log-minimization
  coverage.
- [x] The disposable PostgreSQL rehearsal proves the configured pool size,
  overflow bound, acquisition timeout, effective server statement timeout, and
  cancellation of a synthetic over-time statement.
- [x] The frontend production build, external-AI and operator-runbook policy
  verifiers, and rebuilt Compose health checks pass.
- [x] Supply-chain checks report no Python advisories, no secret leaks, and zero
  high/critical container findings; the three moderate viewer-chain advisories
  remain tracked for a deliberate major upgrade.
- [x] Pull-request and post-merge `main` CI run the PostgreSQL runtime verifier.

## Remaining Deployment Gates

- [ ] Approve replica/worker counts and pool values against the managed
  PostgreSQL connection budget, including failover headroom.
- [ ] Approve workload-specific statement and slow-query thresholds using
  synthetic or properly anonymized performance tests.
- [ ] Route `database_slow_query`, `database_unavailable`, and managed-database
  availability signals to the approved privacy-safe monitoring service.
- [ ] Define sustained-rate alerts and exercise pool exhaustion, slow queries,
  failover, and recovery in the target environment without recording SQL or
  sensitive values.
