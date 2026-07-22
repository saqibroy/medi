"""Security, approval, retention, hold, purge, and receipt proofs."""

import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError

from backend.models import AnnotationHistory, AnnotationHistoryTombstone, DataRetentionPolicy, Organization, SecurityAuditEvent, User
from backend.security import hash_password
from backend.services import data_lifecycle_service
from backend.services.audit_service import verify_integrity
from backend.services.data_lifecycle_service import execute_deletion_request, verify_deletion_receipt
from backend.services.storage_service import LocalPrivateStorage
from backend.settings import get_settings
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _add_governance_admins(app: object) -> None:
    session_factory = app.state.test_session_factory  # type: ignore[attr-defined]
    with session_factory() as db:
        organization = db.scalar(select(Organization).where(Organization.name == "Route Test Lab"))
        assert organization is not None
        db.add_all(
            [
                User(
                    organization_id=organization.id,
                    email="privacy-admin@test.local",
                    full_name="Privacy Admin",
                    password_hash=hash_password("password"),
                    role="admin",
                ),
                User(
                    organization_id=organization.id,
                    email="deletion-operator@test.local",
                    full_name="Deletion Operator",
                    password_hash=hash_password("password"),
                    role="admin",
                ),
            ]
        )
        db.commit()


def _policy_payload(days: int = 0, reference: str = "POLICY-2026-001") -> dict[str, object]:
    return {
        "approval_reference": reference,
        "original_minimum_days": days,
        "mask_minimum_days": days,
        "metadata_minimum_days": days,
        "dataset_release_minimum_days": days,
        "audit_minimum_days": 365,
        "backup_retention_days": 30,
        "rpo_hours": 4,
        "rto_hours": 8,
    }


@pytest.mark.anyio
async def test_governance_routes_are_admin_tenant_scoped_versioned_and_audited(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    _add_governance_admins(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        privacy_token = await login(client, "privacy-admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        outside_token = await login(client, "outside-admin@test.local")
        project = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]

        forbidden = await client.post(
            "/governance/retention-policies",
            json=_policy_payload(),
            headers=auth_headers(annotator_token),
        )
        first = await client.post(
            "/governance/retention-policies",
            json=_policy_payload(30, "POLICY-2026-001"),
            headers=auth_headers(admin_token),
        )
        second = await client.post(
            "/governance/retention-policies",
            json=_policy_payload(0, "POLICY-2026-002"),
            headers=auth_headers(admin_token),
        )
        outside_policies = await client.get("/governance/retention-policies", headers=auth_headers(outside_token))

        assert forbidden.status_code == 403
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["version"] == 1
        assert second.json()["version"] == 2
        assert outside_policies.json() == []

        hold = await client.post(
            "/governance/legal-holds",
            json={
                "scope_type": "project",
                "scope_id": project["id"],
                "reason_code": "regulatory",
                "approval_reference": "HOLD-2026-001",
            },
            headers=auth_headers(admin_token),
        )
        duplicate = await client.post(
            "/governance/legal-holds",
            json={
                "scope_type": "project",
                "scope_id": project["id"],
                "reason_code": "regulatory",
                "approval_reference": "HOLD-2026-002",
            },
            headers=auth_headers(admin_token),
        )
        same_actor_release = await client.post(
            f"/governance/legal-holds/{hold.json()['id']}/release",
            headers=auth_headers(admin_token),
        )
        outside_release = await client.post(
            f"/governance/legal-holds/{hold.json()['id']}/release",
            headers=auth_headers(outside_token),
        )
        released = await client.post(
            f"/governance/legal-holds/{hold.json()['id']}/release",
            headers=auth_headers(privacy_token),
        )

        assert hold.status_code == 201
        assert hold.json()["status"] == "active"
        assert duplicate.status_code == 409
        assert same_actor_release.status_code == 409
        assert outside_release.status_code == 404
        assert released.status_code == 200
        assert released.json()["status"] == "released"
        assert [event["action"] for event in released.json()["events"]] == ["applied", "released"]

        serialized = json.dumps(released.json())
        assert "Brain MRI" not in serialized
        assert "test.nii.gz" not in serialized
        for action in ("retention_policy.create", "legal_hold.create", "legal_hold.release"):
            audit = await client.get(f"/audit-events?action={action}", headers=auth_headers(admin_token))
            assert any(event["result"] == "succeeded" for event in audit.json())
            assert all("approval_reference" not in event["details"] for event in audit.json())


@pytest.mark.anyio
async def test_deletion_requires_policy_hold_clearance_separate_approval_and_operator(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    _add_governance_admins(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        privacy_token = await login(client, "privacy-admin@test.local")
        project = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]
        project_id = project["id"]

        no_policy = await client.post(
            "/governance/deletion-requests",
            json={
                "scope_type": "project",
                "scope_id": project_id,
                "reason_code": "source_withdrawal",
                "approval_reference": "DELETE-2026-001",
            },
            headers=auth_headers(admin_token),
        )
        assert no_policy.status_code == 409

        retained_policy = await client.post(
            "/governance/retention-policies",
            json=_policy_payload(30, "POLICY-RETENTION-030"),
            headers=auth_headers(admin_token),
        )
        retained_request = await client.post(
            "/governance/deletion-requests",
            json={
                "scope_type": "project",
                "scope_id": project_id,
                "reason_code": "source_withdrawal",
                "approval_reference": "DELETE-RETENTION-BLOCK",
            },
            headers=auth_headers(admin_token),
        )
        retention_blocked = await client.post(
            f"/governance/deletion-requests/{retained_request.json()['id']}/approve",
            headers=auth_headers(privacy_token),
        )
        cancelled_retained = await client.post(
            f"/governance/deletion-requests/{retained_request.json()['id']}/cancel",
            headers=auth_headers(admin_token),
        )
        policy = await client.post(
            "/governance/retention-policies",
            json=_policy_payload(0, "POLICY-EXECUTION-000"),
            headers=auth_headers(admin_token),
        )
        annotation = (await client.get("/annotations", headers=auth_headers(admin_token))).json()[0]
        history_update = await client.put(
            f"/annotations/{annotation['id']}",
            json={"notes": "Synthetic lifecycle detail must be removed"},
            headers=auth_headers(admin_token),
        )
        release = await client.post(f"/projects/{project_id}/releases", headers=auth_headers(admin_token))
        hold = await client.post(
            "/governance/legal-holds",
            json={
                "scope_type": "project",
                "scope_id": project_id,
                "reason_code": "customer_request",
                "approval_reference": "HOLD-DELETE-001",
            },
            headers=auth_headers(admin_token),
        )
        requested = await client.post(
            "/governance/deletion-requests",
            json={
                "scope_type": "project",
                "scope_id": project_id,
                "reason_code": "source_withdrawal",
                "approval_reference": "DELETE-2026-002",
            },
            headers=auth_headers(admin_token),
        )
        same_actor_approval = await client.post(
            f"/governance/deletion-requests/{requested.json()['id']}/approve",
            headers=auth_headers(admin_token),
        )
        held_approval = await client.post(
            f"/governance/deletion-requests/{requested.json()['id']}/approve",
            headers=auth_headers(privacy_token),
        )
        released_hold = await client.post(
            f"/governance/legal-holds/{hold.json()['id']}/release",
            headers=auth_headers(privacy_token),
        )
        approved = await client.post(
            f"/governance/deletion-requests/{requested.json()['id']}/approve",
            headers=auth_headers(privacy_token),
        )

        assert retained_policy.status_code == 201
        assert retention_blocked.status_code == 409
        assert "retention" in retention_blocked.json()["detail"]
        assert cancelled_retained.json()["status"] == "cancelled"
        assert policy.status_code == 201
        assert history_update.status_code == 200
        assert release.status_code == 201
        assert requested.status_code == 201
        assert requested.json()["inventory"]["scans"] == 3
        assert "name" not in requested.json()["inventory"]
        assert same_actor_approval.status_code == 409
        assert held_approval.status_code == 409
        assert released_hold.status_code == 200
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        prefix = f"org/{project['organization_id']}/project/{project_id}"
        LocalPrivateStorage(tmp_path).put_bytes(f"{prefix}/scan/synthetic/original/volume.bin", b"synthetic source")
        LocalPrivateStorage(tmp_path / "segmentation_masks").put_bytes(
            f"{prefix}/scan/synthetic/annotations/synthetic/mask/000000.png",
            b"synthetic mask",
        )

        session_factory = app.state.test_session_factory
        with session_factory() as db:
            operator = db.scalar(select(User).where(User.email == "deletion-operator@test.local"))
            assert operator is not None
            with pytest.raises(Exception, match="operator must differ"):
                requester = db.scalar(select(User).where(User.email == "admin@test.local"))
                assert requester is not None
                execute_deletion_request(
                    db,
                    UUID(requested.json()["id"]),
                    requester.id,
                    requested.json()["id"],
                )
            receipt = execute_deletion_request(
                db,
                UUID(requested.json()["id"]),
                operator.id,
                requested.json()["id"],
            )
            receipt_id = receipt.id
            receipt_hash = receipt.receipt_sha256
            assert verify_deletion_receipt(receipt)
            retained_tombstone = db.scalar(
                select(AnnotationHistoryTombstone).where(
                    AnnotationHistoryTombstone.annotation_id == UUID(annotation["id"])
                )
            )
            assert retained_tombstone is not None
            assert retained_tombstone.deletion_source == "data_lifecycle"
            assert retained_tombstone.history_entry_count == 1
            assert retained_tombstone.action_counts == {"updated": 1}
            assert receipt.deleted_counts["annotation_history_tombstones_retained"] == 1
            assert db.scalar(
                select(AnnotationHistory).where(AnnotationHistory.annotation_id == UUID(annotation["id"]))
            ) is None
            operator_audit = db.scalar(
                select(SecurityAuditEvent).where(
                    SecurityAuditEvent.action == "deletion_request.execute",
                    SecurityAuditEvent.target_id == UUID(requested.json()["id"]),
                )
            )
            assert operator_audit is not None
            assert operator_audit.result == "succeeded"
            assert operator_audit.details == {}
            assert verify_integrity(operator_audit, get_settings().audit_signing_key)

        assert not (tmp_path / "org" / project["organization_id"] / "project" / project_id).exists()
        assert not (tmp_path / "segmentation_masks" / "org" / project["organization_id"] / "project" / project_id).exists()
        projects_after = await client.get("/projects", headers=auth_headers(admin_token))
        assert all(item["id"] != project_id for item in projects_after.json())
        retained_release = await client.get(f"/dataset-releases/{release.json()['id']}", headers=auth_headers(admin_token))
        assert retained_release.json()["status"] == "revoked"
        loaded = await client.get(
            f"/governance/deletion-requests/{requested.json()['id']}",
            headers=auth_headers(admin_token),
        )
        assert loaded.json()["status"] == "verified"
        assert loaded.json()["receipt"]["id"] == str(receipt_id)
        assert loaded.json()["receipt"]["receipt_sha256"] == receipt_hash
        assert loaded.json()["receipt"]["revoked_releases"] == 1
        assert loaded.json()["receipt"]["object_versions_deleted"] == 2
        serialized = json.dumps(loaded.json())
        for private_value in (
            "Brain MRI",
            "test.nii.gz",
            "synthetic source",
            "synthetic mask",
            "Synthetic lifecycle detail must be removed",
            "storage_key",
            "file_path",
        ):
            assert private_value not in serialized


@pytest.mark.anyio
async def test_operator_failure_is_recorded_without_deleting_database_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_test_app(tmp_path)
    _add_governance_admins(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        privacy_token = await login(client, "privacy-admin@test.local")
        project = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]
        scan = (await client.get(f"/projects/{project['id']}/scans", headers=auth_headers(admin_token))).json()[0]
        await client.post("/governance/retention-policies", json=_policy_payload(), headers=auth_headers(admin_token))
        requested = await client.post(
            "/governance/deletion-requests",
            json={
                "scope_type": "scan",
                "scope_id": scan["id"],
                "reason_code": "duplicate_data",
                "approval_reference": "DELETE-FAILURE-001",
            },
            headers=auth_headers(admin_token),
        )
        approved = await client.post(
            f"/governance/deletion-requests/{requested.json()['id']}/approve",
            headers=auth_headers(privacy_token),
        )
        assert approved.status_code == 200

        def fail_purge(*_: object) -> None:
            raise RuntimeError("simulated restricted storage failure")

        monkeypatch.setattr(data_lifecycle_service, "_purge_storage", fail_purge)
        session_factory = app.state.test_session_factory
        with session_factory() as db:
            operator = db.scalar(select(User).where(User.email == "deletion-operator@test.local"))
            assert operator is not None
            with pytest.raises(RuntimeError, match="restricted storage failure"):
                execute_deletion_request(db, UUID(requested.json()["id"]), operator.id, requested.json()["id"])
            operator_audit = db.scalar(
                select(SecurityAuditEvent).where(
                    SecurityAuditEvent.action == "deletion_request.execute",
                    SecurityAuditEvent.target_id == UUID(requested.json()["id"]),
                )
            )
            assert operator_audit is not None
            assert operator_audit.result == "error"
            assert operator_audit.details == {}
            assert verify_integrity(operator_audit, get_settings().audit_signing_key)

        loaded = await client.get(
            f"/governance/deletion-requests/{requested.json()['id']}",
            headers=auth_headers(admin_token),
        )
        scans_after = await client.get(f"/projects/{project['id']}/scans", headers=auth_headers(admin_token))
        assert loaded.json()["status"] == "failed"
        assert any(item["id"] == scan["id"] for item in scans_after.json())
        assert "restricted storage failure" not in loaded.text


def test_governance_orm_and_database_records_are_append_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = build_test_app(tmp_path / "app")
    _add_governance_admins(app)
    session_factory = app.state.test_session_factory
    with session_factory() as db:
        organization = db.scalar(select(Organization).where(Organization.name == "Route Test Lab"))
        admin = db.scalar(select(User).where(User.email == "admin@test.local"))
        assert organization is not None and admin is not None
        policy = DataRetentionPolicy(
            organization_id=organization.id,
            version=1,
            approval_reference="POLICY-IMMUTABLE",
            original_minimum_days=0,
            mask_minimum_days=0,
            metadata_minimum_days=0,
            dataset_release_minimum_days=0,
            audit_minimum_days=365,
            backup_retention_days=30,
            rpo_hours=4,
            rto_hours=8,
            created_by_user_id=admin.id,
            created_at=admin.created_at,
        )
        db.add(policy)
        db.commit()
        policy.version = 2
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()

    database_url = f"sqlite:///{tmp_path / 'governance-trigger.db'}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'Governance Org')"), {"id": "1" * 32})
        connection.execute(
            text(
                "INSERT INTO data_retention_policies "
                "(id, organization_id, version, approval_reference, original_minimum_days, mask_minimum_days, "
                "metadata_minimum_days, dataset_release_minimum_days, audit_minimum_days, backup_retention_days, "
                "rpo_hours, rto_hours, created_by_user_id, created_at) VALUES "
                "(:id, :organization_id, 1, 'POLICY-DB', 0, 0, 0, 0, 365, 30, 4, 8, :actor_id, CURRENT_TIMESTAMP)"
            ),
            {"id": "2" * 32, "organization_id": "1" * 32, "actor_id": "3" * 32},
        )

    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE data_retention_policies SET version = 2"))
    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM data_retention_policies"))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version FROM data_retention_policies")) == 1
