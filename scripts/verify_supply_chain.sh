#!/usr/bin/env bash
# Fail on leaked secrets and known high/critical dependency or container findings.

set -euo pipefail

python_bin="${PYTHON_BIN:-.venv/bin/python}"
gitleaks_image="ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
trivy_image="aquasec/trivy@sha256:be1190afcb28352bfddc4ddeb71470835d16462af68d310f9f4bca710961a41e"
backend_image="${SECURITY_BACKEND_IMAGE:-medi-backend-security}"
frontend_image="${SECURITY_FRONTEND_IMAGE:-medi-frontend-security}"
trivy_cache="$(mktemp -d)"
docker_sock_group="$(stat -c %g /var/run/docker.sock)"

cleanup() {
  if [[ "$trivy_cache" == /tmp/* ]]; then
    rm -rf "$trivy_cache"
  fi
}
trap cleanup EXIT

if [[ ! -x "$python_bin" ]] && ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python interpreter not found: $python_bin" >&2
  exit 2
fi
for command_name in docker npm; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required supply-chain command is unavailable: $command_name" >&2
    exit 2
  fi
done
if ! "$python_bin" -c 'import pip_audit' >/dev/null 2>&1; then
  echo "pip-audit is required; install the pinned CI version before running this script." >&2
  exit 2
fi

"$python_bin" -m pip_audit -r backend/requirements.txt
npm --prefix frontend audit --omit=dev --audit-level=high
docker run --rm -v "$PWD:/repo" -w /repo "$gitleaks_image" \
  git --redact --no-banner --exit-code 1 .

docker build --pull -f backend/Dockerfile -t "$backend_image" .
docker build --pull -f frontend/Dockerfile -t "$frontend_image" frontend

for image_name in "$backend_image" "$frontend_image"; do
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --group-add "$docker_sock_group" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$trivy_cache:/tmp/trivy-cache" \
    -e TRIVY_CACHE_DIR=/tmp/trivy-cache \
    "$trivy_image" image \
    --scanners vuln \
    --ignore-unfixed \
    --severity HIGH,CRITICAL \
    --exit-code 1 \
    "$image_name"
done
