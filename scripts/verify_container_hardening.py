"""Verify the running application containers enforce the Compose hardening boundary."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from typing import Any


APPLICATION_SERVICES = ("backend", "frontend")
EXPECTED_WRITABLE_MOUNTS = {
    "backend": {"/app/backend/data/sample_scan"},
    "frontend": set(),
}
ROOT_WRITE_PROBES = {
    "backend": "/app/.medi-rootfs-write-check",
    "frontend": "/usr/share/nginx/html/.medi-rootfs-write-check",
}


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def _container_id(service: str) -> str:
    container_id = _run("docker", "compose", "ps", "--quiet", service).stdout.strip()
    if not container_id:
        raise RuntimeError(f"{service} container is not running")
    return container_id


def _inspect(container_id: str) -> dict[str, Any]:
    payload = json.loads(_run("docker", "inspect", container_id).stdout)
    if len(payload) != 1:
        raise RuntimeError("unexpected container inspection result")
    return payload[0]


def _compose_exec(
    service: str,
    command: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run("docker", "compose", "exec", "-T", service, "sh", "-c", command, check=check)


def _assert_runtime_controls(service: str, inspection: dict[str, Any]) -> None:
    runtime_uid = _compose_exec(service, "id -u").stdout.strip()
    if runtime_uid == "0" or not runtime_uid.isdigit():
        raise RuntimeError(f"{service} must run with a numeric non-root UID")

    host_config = inspection["HostConfig"]
    if host_config.get("ReadonlyRootfs") is not True:
        raise RuntimeError(f"{service} root filesystem is not read-only")

    dropped = {value.upper() for value in host_config.get("CapDrop") or []}
    if "ALL" not in dropped:
        raise RuntimeError(f"{service} does not drop all Linux capabilities")

    security_options = set(host_config.get("SecurityOpt") or [])
    if "no-new-privileges:true" not in security_options:
        raise RuntimeError(f"{service} does not disable privilege escalation")

    tmpfs = host_config.get("Tmpfs") or {}
    if set(tmpfs) != {"/tmp"}:
        raise RuntimeError(f"{service} must expose only the approved temporary filesystem")
    tmp_options = set(tmpfs["/tmp"].split(","))
    for required in {"rw", "noexec", "nosuid", "nodev"}:
        if required not in tmp_options:
            raise RuntimeError(f"{service} temporary filesystem is missing {required}")

    writable_mounts = {
        mount["Destination"]
        for mount in inspection.get("Mounts", [])
        if mount.get("RW") is True
    }
    if writable_mounts != EXPECTED_WRITABLE_MOUNTS[service]:
        raise RuntimeError(f"{service} has an unexpected writable mount set")


def _assert_write_boundary(service: str) -> None:
    root_probe = ROOT_WRITE_PROBES[service]
    root_result = _compose_exec(
        service,
        f"touch {root_probe} 2>/dev/null",
        check=False,
    )
    if root_result.returncode == 0:
        _compose_exec(service, f"rm -f {root_probe}", check=False)
        raise RuntimeError(f"{service} root filesystem accepted a write")

    _compose_exec(service, "probe=/tmp/.medi-write-check; : > \"$probe\"; rm -f \"$probe\"")
    if service == "backend":
        _compose_exec(
            service,
            "probe=/app/backend/data/sample_scan/.medi-write-check; "
            ': > "$probe"; rm -f "$probe"',
        )


def _assert_health() -> None:
    for url in (
        "http://127.0.0.1:8000/health/live",
        "http://127.0.0.1:8000/health/ready",
        "http://127.0.0.1:8080/health",
    ):
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError("application health endpoint did not return 200")


def main() -> None:
    for service in APPLICATION_SERVICES:
        inspection = _inspect(_container_id(service))
        _assert_runtime_controls(service, inspection)
        _assert_write_boundary(service)
    _assert_health()
    print("Container hardening verification passed for backend and frontend.")


if __name__ == "__main__":
    main()
