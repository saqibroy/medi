#!/usr/bin/env python3
"""Read-only verification of Medi's required S3 control-plane settings."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable

import boto3


@dataclass(frozen=True)
class ExpectedControls:
    kms_key_arn: str
    quarantine_expiration_days: int
    preview_expiration_days: int
    export_expiration_days: int
    noncurrent_expiration_days: int


@dataclass(frozen=True)
class ControlResult:
    control: str
    passed: bool
    detail: str


def verify_bucket(client: object, bucket: str, expected: ExpectedControls) -> list[ControlResult]:
    """Inspect bucket settings without reading object keys or object data."""

    results: list[ControlResult] = []

    public_access = _safe_call(results, "public_access_block", lambda: client.get_public_access_block(Bucket=bucket))
    if public_access is not None:
        configuration = public_access.get("PublicAccessBlockConfiguration", {})
        required = ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets")
        _append(results, "public_access_block", all(configuration.get(key) is True for key in required), "all four public-access settings enabled")

    policy_status = _safe_call(results, "bucket_policy_public_status", lambda: client.get_bucket_policy_status(Bucket=bucket))
    if policy_status is not None:
        _append(results, "bucket_policy_public_status", policy_status.get("PolicyStatus", {}).get("IsPublic") is False, "bucket policy is not public")

    encryption = _safe_call(results, "default_kms_encryption", lambda: client.get_bucket_encryption(Bucket=bucket))
    if encryption is not None:
        rules = encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
        matching_rule = next(
            (
                rule
                for rule in rules
                if rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm") == "aws:kms"
                and rule.get("ApplyServerSideEncryptionByDefault", {}).get("KMSMasterKeyID") == expected.kms_key_arn
                and rule.get("BucketKeyEnabled") is True
            ),
            None,
        )
        _append(results, "default_kms_encryption", matching_rule is not None, "approved KMS key and S3 Bucket Key enabled")

    versioning = _safe_call(results, "versioning", lambda: client.get_bucket_versioning(Bucket=bucket))
    if versioning is not None:
        _append(results, "versioning", versioning.get("Status") == "Enabled", "bucket versioning enabled")

    ownership = _safe_call(results, "object_ownership", lambda: client.get_bucket_ownership_controls(Bucket=bucket))
    if ownership is not None:
        rules = ownership.get("OwnershipControls", {}).get("Rules", [])
        _append(
            results,
            "object_ownership",
            any(rule.get("ObjectOwnership") == "BucketOwnerEnforced" for rule in rules),
            "ACLs disabled with BucketOwnerEnforced",
        )

    policy_response = _safe_call(results, "bucket_policy", lambda: client.get_bucket_policy(Bucket=bucket))
    if policy_response is not None:
        try:
            policy = json.loads(policy_response.get("Policy", "{}"))
        except (TypeError, json.JSONDecodeError):
            _append(results, "bucket_policy", False, "policy document is valid JSON")
        else:
            statements = policy.get("Statement", [])
            _append(results, "tls_only_policy", _has_tls_deny(statements), "explicit deny for insecure non-service requests")
            _append(results, "kms_write_policy", _has_kms_write_denies(statements, expected.kms_key_arn), "missing, wrong algorithm, and wrong KMS key writes denied")
            _append(results, "data_class_write_policy", _has_data_class_denies(statements), "missing, unknown, and extra object tags denied")

    lifecycle_response = _safe_call(results, "lifecycle", lambda: client.get_bucket_lifecycle_configuration(Bucket=bucket))
    if lifecycle_response is not None:
        lifecycle_rules = {rule.get("ID"): rule for rule in lifecycle_response.get("Rules", [])}
        expected_current = {
            "ExpireQuarantine": ("quarantine", expected.quarantine_expiration_days),
            "ExpireDerivedPreviews": ("preview", expected.preview_expiration_days),
            "ExpireExports": ("export", expected.export_expiration_days),
        }
        for rule_id, (data_class, days) in expected_current.items():
            rule = lifecycle_rules.get(rule_id, {})
            passed = _enabled_tag_rule(rule, data_class) and rule.get("Expiration", {}).get("Days") == days
            _append(results, f"lifecycle_{data_class}", passed, f"{data_class} current versions expire after approved {days} days")

        for data_class, rule_id in (
            ("original", "ExpireNoncurrentOriginals"),
            ("mask", "ExpireNoncurrentMasks"),
            ("metadata", "ExpireNoncurrentMetadata"),
            ("quarantine", "ExpireNoncurrentQuarantine"),
            ("preview", "ExpireNoncurrentPreviews"),
            ("export", "ExpireNoncurrentExports"),
        ):
            rule = lifecycle_rules.get(rule_id, {})
            passed = (
                _enabled_tag_rule(rule, data_class)
                and rule.get("NoncurrentVersionExpiration", {}).get("NoncurrentDays") == expected.noncurrent_expiration_days
            )
            _append(results, f"noncurrent_{data_class}", passed, f"{data_class} noncurrent versions expire after approved {expected.noncurrent_expiration_days} days")

        release_rules = [
            rule
            for rule in lifecycle_rules.values()
            if _enabled_tag_rule(rule, "dataset-release")
            and ("Expiration" in rule or "NoncurrentVersionExpiration" in rule)
        ]
        _append(
            results,
            "lifecycle_dataset_release_retained",
            not release_rules,
            "dataset-release current and noncurrent versions have no automatic expiration",
        )

        abort_rule = lifecycle_rules.get("AbortIncompleteMultipartUploads", {})
        abort_days = abort_rule.get("AbortIncompleteMultipartUpload", {}).get("DaysAfterInitiation")
        _append(results, "incomplete_multipart_uploads", abort_rule.get("Status") == "Enabled" and abort_days == 7, "incomplete multipart uploads aborted after 7 days")

    return results


def _safe_call(
    results: list[ControlResult],
    control: str,
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        return operation()
    except Exception as error:  # Boto exceptions vary by missing control/API.
        code = getattr(error, "response", {}).get("Error", {}).get("Code")
        safe_error = str(code) if code else type(error).__name__
        results.append(ControlResult(control=control, passed=False, detail=f"control could not be read: {safe_error}"))
        return None


def _append(results: list[ControlResult], control: str, passed: bool, detail: str) -> None:
    results.append(ControlResult(control=control, passed=passed, detail=detail))


def _enabled_tag_rule(rule: dict[str, Any], data_class: str) -> bool:
    tag = rule.get("Filter", {}).get("Tag", {})
    return rule.get("Status") == "Enabled" and tag == {"Key": "medi-data-class", "Value": data_class}


def _has_tls_deny(statements: list[dict[str, Any]]) -> bool:
    for statement in statements:
        condition = statement.get("Condition", {}).get("Bool", {})
        if (
            statement.get("Effect") == "Deny"
            and statement.get("Action") == "s3:*"
            and str(condition.get("aws:SecureTransport")).lower() == "false"
            and str(condition.get("aws:PrincipalIsAWSService")).lower() == "false"
        ):
            return True
    return False


def _has_kms_write_denies(statements: list[dict[str, Any]], kms_key_arn: str) -> bool:
    missing_key = False
    wrong_algorithm = False
    wrong_key = False
    for statement in statements:
        if statement.get("Effect") != "Deny" or statement.get("Action") != "s3:PutObject":
            continue
        condition = statement.get("Condition", {})
        missing_key = missing_key or str(condition.get("Null", {}).get("s3:x-amz-server-side-encryption-aws-kms-key-id")).lower() == "true"
        wrong_algorithm = wrong_algorithm or condition.get("StringNotEquals", {}).get("s3:x-amz-server-side-encryption") == "aws:kms"
        wrong_key = wrong_key or condition.get("ArnNotEqualsIfExists", {}).get("s3:x-amz-server-side-encryption-aws-kms-key-id") == kms_key_arn
    return missing_key and wrong_algorithm and wrong_key


def _has_data_class_denies(statements: list[dict[str, Any]]) -> bool:
    missing_tag = False
    allowed_values = False
    extra_keys = False
    expected_values = {"dataset-release", "export", "mask", "metadata", "original", "preview", "quarantine", "unclassified"}
    for statement in statements:
        if statement.get("Effect") != "Deny" or statement.get("Action") != "s3:PutObject":
            continue
        condition = statement.get("Condition", {})
        missing_tag = missing_tag or str(condition.get("Null", {}).get("s3:RequestObjectTag/medi-data-class")).lower() == "true"
        configured_values = condition.get("StringNotEquals", {}).get("s3:RequestObjectTag/medi-data-class", [])
        allowed_values = allowed_values or set(configured_values) == expected_values
        configured_keys = condition.get("ForAnyValue:StringNotEquals", {}).get("s3:RequestObjectTagKeys", [])
        extra_keys = extra_keys or configured_keys == ["medi-data-class"]
    return missing_tag and allowed_values and extra_keys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--kms-key-arn", required=True)
    parser.add_argument("--quarantine-expiration-days", type=int, required=True)
    parser.add_argument("--preview-expiration-days", type=int, required=True)
    parser.add_argument("--export-expiration-days", type=int, required=True)
    parser.add_argument("--noncurrent-expiration-days", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    expected = ExpectedControls(
        kms_key_arn=arguments.kms_key_arn,
        quarantine_expiration_days=arguments.quarantine_expiration_days,
        preview_expiration_days=arguments.preview_expiration_days,
        export_expiration_days=arguments.export_expiration_days,
        noncurrent_expiration_days=arguments.noncurrent_expiration_days,
    )
    client = boto3.client("s3", region_name=arguments.region)
    results = verify_bucket(client, arguments.bucket, expected)
    print(json.dumps({"bucket": arguments.bucket, "passed": all(result.passed for result in results), "controls": [asdict(result) for result in results]}, indent=2))
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
