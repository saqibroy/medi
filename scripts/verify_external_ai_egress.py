#!/usr/bin/env python3
"""Fail CI when backend runtime code adds an ungoverned network/AI client."""

from __future__ import annotations

import ast
from pathlib import Path


RESTRICTED_MODULES = (
    "aiohttp",
    "anthropic",
    "google.generativeai",
    "http.client",
    "httpx",
    "openai",
    "requests",
    "socket",
    "urllib.request",
)
BOTO3_ALLOWLIST = {Path("backend/services/storage_service.py")}
PROCESS_ALLOWLIST = {Path("backend/startup.py")}


def _import_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return [f"{module}.{alias.name}" if module else alias.name for alias in node.names]
    return []


def verify_repository(root: Path) -> list[str]:
    errors: list[str] = []
    backend_root = root / "backend"
    for path in sorted(backend_root.rglob("*.py")):
        relative = path.relative_to(root)
        if "tests" in relative.parts or "migrations" in relative.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            for imported in _import_names(node):
                if any(imported == module or imported.startswith(f"{module}.") for module in RESTRICTED_MODULES):
                    errors.append(f"{relative}:{getattr(node, 'lineno', 1)} restricted runtime import {imported}")
                if (imported == "boto3" or imported.startswith("boto3.")) and relative not in BOTO3_ALLOWLIST:
                    errors.append(f"{relative}:{getattr(node, 'lineno', 1)} boto3 is allowed only in private storage")
                if (imported == "subprocess" or imported.startswith("subprocess.")) and relative not in PROCESS_ALLOWLIST:
                    errors.append(f"{relative}:{getattr(node, 'lineno', 1)} subprocess is not allowed in backend runtime code")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr in {"popen", "system"}:
                    errors.append(f"{relative}:{getattr(node, 'lineno', 1)} shell network bypass primitives are prohibited")

    required_text = {
        Path(".env.example"): "EXTERNAL_AI_ENABLED=false",
        Path("docker-compose.yml"): "EXTERNAL_AI_ENABLED: ${EXTERNAL_AI_ENABLED:-false}",
        Path("backend/settings.py"): 'values.get("EXTERNAL_AI_ENABLED", "false")',
    }
    for relative, marker in required_text.items():
        if marker not in (root / relative).read_text(encoding="utf-8"):
            errors.append(f"{relative}: missing deny-by-default marker {marker}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = verify_repository(root)
    if errors:
        print("External AI egress policy failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("External AI egress policy passed: default disabled and no ungoverned runtime clients found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
