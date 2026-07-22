#!/usr/bin/env python3
"""Check the operator runbook package for required safety and response coverage."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK_REQUIREMENTS = {
    "OPERATOR_RUNBOOKS.md": (
        "## Target Worksheet",
        "## Common Safety Rules",
        "## Common Health Checks",
        "## Minimum Evidence Record",
        "synthetic or properly anonymized data only",
    ),
    "SECURITY_INCIDENT_RUNBOOK.md": (
        "## Privacy-Safe Evidence Preservation",
        "## Personal-Data Breach Assessment Handoff",
        "## Eradicate, Recover, And Verify",
        "not automatically",
    ),
    "SERVICE_DEGRADATION_RUNBOOK.md": (
        "## Failure Matrix",
        "## PostgreSQL Degradation",
        "## Redis Degradation",
        "## Private Storage Or KMS Degradation",
        "Do not set `RATE_LIMIT_BACKEND=memory` in production",
    ),
    "KEY_COMPROMISE_RUNBOOK.md": (
        "## Medi Secret Inventory And Effects",
        "## Rotation Sequence",
        "## Audit And Privacy Key Limitation",
        "no key identifier",
    ),
    "DEPLOYMENT_ROLLBACK_RUNBOOK.md": (
        "## Preflight",
        "## Privacy-Safe Smoke Test",
        "## Rollback Procedure",
        "Provider-specific deploy commands are intentionally absent",
    ),
}
LINK_PATTERN = re.compile(r"\[[^]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")


def main() -> None:
    errors: list[str] = []
    for relative_path, requirements in RUNBOOK_REQUIREMENTS.items():
        path = ROOT / relative_path
        if not path.is_file():
            errors.append(f"missing runbook: {relative_path}")
            continue
        content = path.read_text(encoding="utf-8")
        for requirement in requirements:
            if requirement not in content:
                errors.append(f"{relative_path}: missing required text: {requirement}")
        for target in LINK_PATTERN.findall(content):
            if "://" in target:
                continue
            linked_path = (path.parent / target).resolve()
            if not linked_path.is_relative_to(ROOT) or not linked_path.is_file():
                errors.append(f"{relative_path}: broken local Markdown link: {target}")

    if errors:
        raise SystemExit("Operator runbook verification failed:\n- " + "\n- ".join(errors))
    print(f"Operator runbook verification passed for {len(RUNBOOK_REQUIREMENTS)} documents.")


if __name__ == "__main__":
    main()
