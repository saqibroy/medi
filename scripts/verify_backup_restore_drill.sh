#!/usr/bin/env bash
# Encrypted, disposable PostgreSQL and synthetic-object backup/restore drill.

set -euo pipefail

source_database="${RECOVERY_SOURCE_DATABASE:-medi_recovery_source}"
restore_database="${RECOVERY_RESTORE_DATABASE:-medi_recovery_restore}"
python_bin="${PYTHON_BIN:-.venv/bin/python}"
work_dir="$(mktemp -d)"
key_file="$work_dir/drill.key"
database_backup="$work_dir/database.dump.enc"
object_backup="$work_dir/objects.tar.enc"
source_objects="$work_dir/source-objects"
restored_objects="$work_dir/restored-objects"

for database_name in "$source_database" "$restore_database"; do
  if [[ ! "$database_name" =~ ^medi_recovery_[a-z0-9_]+$ ]]; then
    echo "Recovery database names must start with medi_recovery_ and use lowercase letters, numbers, or underscores." >&2
    exit 2
  fi
done
if [[ "$source_database" == "$restore_database" ]]; then
  echo "Recovery source and restore databases must differ." >&2
  exit 2
fi
if [[ ! -x "$python_bin" ]] && ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python interpreter not found." >&2
  exit 2
fi
for command_name in docker openssl sha256sum tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required recovery-drill command is unavailable: $command_name" >&2
    exit 2
  fi
done

drop_database() {
  local database_name="$1"
  docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$database_name' AND pid <> pg_backend_pid();" >/dev/null
  docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
    -c "DROP DATABASE IF EXISTS \"$database_name\";" >/dev/null
}

cleanup() {
  drop_database "$restore_database" || true
  drop_database "$source_database" || true
  if [[ "$work_dir" == /tmp/* ]]; then
    rm -rf "$work_dir"
  fi
}

trap cleanup EXIT
docker compose up -d db >/dev/null
drop_database "$restore_database"
drop_database "$source_database"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "CREATE DATABASE \"$source_database\";" >/dev/null

export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/$source_database"
"$python_bin" -m alembic upgrade head >/dev/null
"$python_bin" -m backend.seed >/dev/null

source_revision="$(docker compose exec -T db psql -At -v ON_ERROR_STOP=1 -U postgres -d "$source_database" -c 'SELECT version_num FROM alembic_version')"
source_counts="$(docker compose exec -T db psql -At -v ON_ERROR_STOP=1 -U postgres -d "$source_database" -c "SELECT concat_ws(',', (SELECT count(*) FROM organizations), (SELECT count(*) FROM projects), (SELECT count(*) FROM scans), (SELECT count(*) FROM annotations), (SELECT count(*) FROM security_audit_events), (SELECT count(*) FROM dataset_releases));")"

openssl rand -hex 32 >"$key_file"
chmod 600 "$key_file"
docker compose exec -T db pg_dump -U postgres -Fc "$source_database" \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$key_file" -out "$database_backup"
database_backup_sha256="$(sha256sum "$database_backup" | awk '{print $1}')"

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c "CREATE DATABASE \"$restore_database\";" >/dev/null
openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$key_file" -in "$database_backup" \
  | docker compose exec -T db pg_restore --exit-on-error --no-owner -U postgres -d "$restore_database"

restored_revision="$(docker compose exec -T db psql -At -v ON_ERROR_STOP=1 -U postgres -d "$restore_database" -c 'SELECT version_num FROM alembic_version')"
restored_counts="$(docker compose exec -T db psql -At -v ON_ERROR_STOP=1 -U postgres -d "$restore_database" -c "SELECT concat_ws(',', (SELECT count(*) FROM organizations), (SELECT count(*) FROM projects), (SELECT count(*) FROM scans), (SELECT count(*) FROM annotations), (SELECT count(*) FROM security_audit_events), (SELECT count(*) FROM dataset_releases));")"
test "$source_revision" = "$restored_revision"
test "$source_counts" = "$restored_counts"

mkdir -p "$source_objects/org/synthetic/project/synthetic/scan/synthetic/original" "$restored_objects"
printf 'synthetic recovery fixture\n' >"$source_objects/org/synthetic/project/synthetic/scan/synthetic/original/volume.bin"
source_object_sha256="$(sha256sum "$source_objects/org/synthetic/project/synthetic/scan/synthetic/original/volume.bin" | awk '{print $1}')"
tar -C "$source_objects" -cf - . \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$key_file" -out "$object_backup"
openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$key_file" -in "$object_backup" \
  | tar -C "$restored_objects" -xf -
restored_object_sha256="$(sha256sum "$restored_objects/org/synthetic/project/synthetic/scan/synthetic/original/volume.bin" | awk '{print $1}')"
test "$source_object_sha256" = "$restored_object_sha256"

SOURCE_REVISION="$source_revision" SOURCE_COUNTS="$source_counts" DATABASE_BACKUP_SHA256="$database_backup_sha256" \
OBJECT_SHA256="$restored_object_sha256" "$python_bin" -c '
import json, os
print(json.dumps({
    "database_backup_encrypted": True,
    "database_backup_sha256": os.environ["DATABASE_BACKUP_SHA256"],
    "object_backup_encrypted": True,
    "object_sha256": os.environ["OBJECT_SHA256"],
    "restored_alembic_revision": os.environ["SOURCE_REVISION"],
    "verified_table_counts": [int(value) for value in os.environ["SOURCE_COUNTS"].split(",")],
}, sort_keys=True))
'
