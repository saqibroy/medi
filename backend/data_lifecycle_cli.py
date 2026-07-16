"""Separately enabled operator entrypoint for approved deletion execution."""

from __future__ import annotations

import argparse
import json
from uuid import UUID

from .database import SessionLocal
from .services.data_lifecycle_service import execute_deletion_request
from .settings import get_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute an approved Medi data deletion request")
    parser.add_argument("--request-id", type=UUID, required=True)
    parser.add_argument("--operator-user-id", type=UUID, required=True)
    parser.add_argument("--confirm-request-id", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = get_settings()
    if not settings.data_deletion_operator_enabled:
        print("Deletion operator is disabled; enable it only in the approved operator environment.")
        return 2

    with SessionLocal() as db:
        try:
            receipt = execute_deletion_request(
                db,
                request_id=args.request_id,
                operator_user_id=args.operator_user_id,
                confirmation=args.confirm_request_id,
            )
            print(
                json.dumps(
                    {
                        "request_id": str(receipt.request_id),
                        "receipt_id": str(receipt.id),
                        "receipt_sha256": receipt.receipt_sha256,
                        "completed_at": receipt.completed_at.isoformat(),
                    },
                    sort_keys=True,
                )
            )
            return 0
        except Exception:
            print("Deletion execution failed; inspect restricted operator logs and the append-only request state.")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
