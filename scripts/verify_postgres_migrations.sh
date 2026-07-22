#!/usr/bin/env bash
# Exercise every Alembic upgrade and downgrade on a disposable local PostgreSQL database.

set -euo pipefail

test_database="${MIGRATION_TEST_DATABASE:-medi_migration_qa}"
python_bin="${PYTHON_BIN:-.venv/bin/python}"

if [[ ! "$test_database" =~ ^medi_migration_[a-z0-9_]+$ ]]; then
  echo "MIGRATION_TEST_DATABASE must start with medi_migration_ and contain only lowercase letters, numbers, and underscores." >&2
  exit 2
fi

if [[ ! -x "$python_bin" ]]; then
  echo "Python interpreter not found: $python_bin" >&2
  exit 2
fi

cleanup() {
  docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
    -c "DROP DATABASE IF EXISTS \"$test_database\";" >/dev/null
}

docker compose up -d db >/dev/null
trap cleanup EXIT
cleanup
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "CREATE DATABASE \"$test_database\";" >/dev/null

export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/$test_database"
export DATABASE_POOL_SIZE=3
export DATABASE_MAX_OVERFLOW=1
export DATABASE_POOL_TIMEOUT_SECONDS=2
export DATABASE_STATEMENT_TIMEOUT_MS=250
export DATABASE_SLOW_QUERY_THRESHOLD_MS=100

"$python_bin" -m alembic upgrade head
head_revision="$("$python_bin" -m alembic heads | awk 'NR == 1 { print $1 }')"
current_revision="$("$python_bin" -m alembic current | awk 'NR == 1 { print $1 }')"
test "$current_revision" = "$head_revision"

"$python_bin" -m alembic downgrade base
test -z "$("$python_bin" -m alembic current)"

"$python_bin" -m alembic upgrade head
current_revision="$("$python_bin" -m alembic current | awk 'NR == 1 { print $1 }')"
test "$current_revision" = "$head_revision"

"$python_bin" -m scripts.verify_database_runtime

echo "PostgreSQL migration upgrade/downgrade cycle passed at $head_revision."
