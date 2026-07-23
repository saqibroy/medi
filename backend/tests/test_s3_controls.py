"""Tests for read-only target-account S3 control verification."""

import json
from pathlib import Path

from scripts.verify_s3_controls import ExpectedControls, verify_bucket


KMS_KEY_ARN = "arn:aws:kms:eu-central-1:123456789012:key/00000000-0000-0000-0000-000000000001"


class FakeControlPlaneClient:
    def __init__(self) -> None:
        self.versioning_status = "Enabled"

    def get_public_access_block(self, **_: object) -> dict:
        return {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        }

    def get_bucket_policy_status(self, **_: object) -> dict:
        return {"PolicyStatus": {"IsPublic": False}}

    def get_bucket_encryption(self, **_: object) -> dict:
        return {
            "ServerSideEncryptionConfiguration": {
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms", "KMSMasterKeyID": KMS_KEY_ARN},
                        "BucketKeyEnabled": True,
                    }
                ]
            }
        }

    def get_bucket_versioning(self, **_: object) -> dict:
        return {"Status": self.versioning_status}

    def get_bucket_ownership_controls(self, **_: object) -> dict:
        return {"OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}}

    def get_bucket_policy(self, **_: object) -> dict:
        return {
            "Policy": json.dumps(
                {
                    "Statement": [
                        {
                            "Effect": "Deny",
                            "Action": "s3:*",
                            "Condition": {"Bool": {"aws:SecureTransport": "false", "aws:PrincipalIsAWSService": "false"}},
                        },
                        {
                            "Effect": "Deny",
                            "Action": "s3:PutObject",
                            "Condition": {"Null": {"s3:x-amz-server-side-encryption-aws-kms-key-id": "true"}},
                        },
                        {
                            "Effect": "Deny",
                            "Action": "s3:PutObject",
                            "Condition": {"StringNotEquals": {"s3:x-amz-server-side-encryption": "aws:kms"}},
                        },
                        {
                            "Effect": "Deny",
                            "Action": "s3:PutObject",
                            "Condition": {"ArnNotEqualsIfExists": {"s3:x-amz-server-side-encryption-aws-kms-key-id": KMS_KEY_ARN}},
                        },
                        {
                            "Effect": "Deny",
                            "Action": "s3:PutObject",
                            "Condition": {"Null": {"s3:RequestObjectTag/medi-data-class": "true"}},
                        },
                        {
                            "Effect": "Deny",
                            "Action": "s3:PutObject",
                            "Condition": {
                                "StringNotEquals": {
                                    "s3:RequestObjectTag/medi-data-class": [
                                        "dataset-release",
                                        "export",
                                        "mask",
                                        "metadata",
                                        "original",
                                        "preview",
                                        "quarantine",
                                        "unclassified",
                                    ]
                                }
                            },
                        },
                        {
                            "Effect": "Deny",
                            "Action": "s3:PutObject",
                            "Condition": {"ForAnyValue:StringNotEquals": {"s3:RequestObjectTagKeys": ["medi-data-class"]}},
                        },
                    ]
                }
            )
        }

    def get_bucket_lifecycle_configuration(self, **_: object) -> dict:
        current = [
            _current_rule("ExpireQuarantine", "quarantine", 30),
            _current_rule("ExpireDerivedPreviews", "preview", 90),
            _current_rule("ExpireExports", "export", 14),
        ]
        noncurrent = [
            _noncurrent_rule("ExpireNoncurrentOriginals", "original", 365),
            _noncurrent_rule("ExpireNoncurrentMasks", "mask", 365),
            _noncurrent_rule("ExpireNoncurrentMetadata", "metadata", 365),
            _noncurrent_rule("ExpireNoncurrentQuarantine", "quarantine", 365),
            _noncurrent_rule("ExpireNoncurrentPreviews", "preview", 365),
            _noncurrent_rule("ExpireNoncurrentExports", "export", 365),
        ]
        return {
            "Rules": [
                *current,
                *noncurrent,
                {
                    "ID": "AbortIncompleteMultipartUploads",
                    "Status": "Enabled",
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                },
            ]
        }


def _current_rule(rule_id: str, data_class: str, days: int) -> dict:
    return {"ID": rule_id, "Status": "Enabled", "Filter": {"Tag": {"Key": "medi-data-class", "Value": data_class}}, "Expiration": {"Days": days}}


def _noncurrent_rule(rule_id: str, data_class: str, days: int) -> dict:
    return {
        "ID": rule_id,
        "Status": "Enabled",
        "Filter": {"Tag": {"Key": "medi-data-class", "Value": data_class}},
        "NoncurrentVersionExpiration": {"NoncurrentDays": days},
    }


def expected_controls() -> ExpectedControls:
    return ExpectedControls(
        kms_key_arn=KMS_KEY_ARN,
        quarantine_expiration_days=30,
        preview_expiration_days=90,
        export_expiration_days=14,
        noncurrent_expiration_days=365,
    )


def test_compliant_bucket_controls_pass_without_reading_objects() -> None:
    results = verify_bucket(FakeControlPlaneClient(), "medi-private", expected_controls())

    assert results
    assert all(result.passed for result in results)
    assert {result.control for result in results} >= {
        "public_access_block",
        "default_kms_encryption",
        "versioning",
        "tls_only_policy",
        "kms_write_policy",
        "data_class_write_policy",
        "lifecycle_quarantine",
        "lifecycle_dataset_release_retained",
        "noncurrent_original",
    }


def test_noncompliant_versioning_fails_closed() -> None:
    client = FakeControlPlaneClient()
    client.versioning_status = "Suspended"

    results = verify_bucket(client, "medi-private", expected_controls())

    versioning = next(result for result in results if result.control == "versioning")
    assert versioning.passed is False
    assert not all(result.passed for result in results)


def test_cloudformation_template_requires_retention_and_excludes_version_purge_from_runtime() -> None:
    template_path = Path(__file__).parents[2] / "infrastructure" / "aws" / "medi-private-storage.json"
    template = json.loads(template_path.read_text(), object_pairs_hook=_unique_object)

    for parameter in (
        "QuarantineExpirationDays",
        "PreviewExpirationDays",
        "ExportExpirationDays",
        "NoncurrentVersionExpirationDays",
    ):
        assert "Default" not in template["Parameters"][parameter]

    bucket = template["Resources"]["StorageBucket"]
    assert bucket["DeletionPolicy"] == "Retain"
    assert bucket["UpdateReplacePolicy"] == "Retain"
    assert bucket["Properties"]["VersioningConfiguration"]["Status"] == "Enabled"
    assert all(bucket["Properties"]["PublicAccessBlockConfiguration"].values())
    lifecycle_rules = bucket["Properties"]["LifecycleConfiguration"]["Rules"]
    tagged_rules = [rule for rule in lifecycle_rules if rule["Id"] != "AbortIncompleteMultipartUploads"]
    assert tagged_rules
    assert all(len(rule["TagFilters"]) == 1 for rule in tagged_rules)
    assert all(rule["TagFilters"][0]["Key"] == "medi-data-class" for rule in tagged_rules)
    assert all("Filter" not in rule for rule in lifecycle_rules)
    assert not any(
        rule["TagFilters"][0]["Value"] == "dataset-release"
        for rule in tagged_rules
    )

    statements = template["Resources"]["ApplicationStoragePolicy"]["Properties"]["PolicyDocument"]["Statement"]
    runtime_actions = {action for statement in statements for action in statement["Action"]}
    assert "s3:DeleteObject" in runtime_actions
    assert "s3:DeleteObjectVersion" not in runtime_actions
    assert "s3:PutBucketPolicy" not in runtime_actions
    assert "kms:ScheduleKeyDeletion" not in runtime_actions


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
