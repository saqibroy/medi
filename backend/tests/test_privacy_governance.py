"""Privacy processing evidence, rights workflow, and minimization proofs."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError

from backend.models import (
    DataDeletionEvent,
    DataDeletionReceipt,
    DataDeletionRequest,
    Organization,
    PrivacyProcessingRecord,
    PrivacyRequest,
    SecurityAuditEvent,
    User,
)
from backend.security import hash_password
from backend.services.audit_service import verify_integrity
from backend.settings import get_settings
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _add_privacy_admins(app: object) -> None:
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
                    email="privacy-operator@test.local",
                    full_name="Privacy Operator",
                    password_hash=hash_password("password"),
                    role="admin",
                ),
            ]
        )
        db.commit()


def _policy_payload(reference: str = "PRIVACY-POLICY-001") -> dict[str, object]:
    return {
        "approval_reference": reference,
        "original_minimum_days": 0,
        "mask_minimum_days": 0,
        "metadata_minimum_days": 0,
        "dataset_release_minimum_days": 0,
        "audit_minimum_days": 365,
        "backup_retention_days": 30,
        "rpo_hours": 4,
        "rto_hours": 8,
    }


def _processing_payload(policy_id: str, approval: str = "ROPA-APPROVAL-001") -> dict[str, object]:
    return {
        "activity_key": "research-annotation",
        "organization_role": "processor",
        "purpose_code": "research_dataset_annotation",
        "lawful_basis": "contract",
        "health_data_processed": True,
        "article9_condition": "research_statistics",
        "data_subject_categories": ["research_participants"],
        "personal_data_categories": ["pseudonymized_medical_images", "annotation_data"],
        "recipient_categories": ["authorized_workspace_users", "controller_staff"],
        "processor_references": ["PROCESSOR-DPA-001"],
        "processing_locations": ["eu-central-1"],
        "transfer_mechanism": "not_applicable",
        "transfer_safeguard_reference": None,
        "retention_policy_id": policy_id,
        "security_measure_references": ["SECURITY-BASELINE-001", "STORAGE-CONTROLS-001"],
        "dpia_required": True,
        "dpia_outcome": "approved",
        "dpia_reference": "DPIA-001",
        "dpo_review_reference": "DPO-REVIEW-001",
        "approval_reference": approval,
    }


@pytest.mark.anyio
async def test_processing_records_are_admin_tenant_scoped_versioned_and_audited(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    _add_privacy_admins(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        privacy_token = await login(client, "privacy-admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        outside_token = await login(client, "outside-admin@test.local")
        policy = await client.post(
            "/governance/retention-policies",
            json=_policy_payload(),
            headers=auth_headers(admin_token),
        )
        payload = _processing_payload(policy.json()["id"])

        forbidden = await client.post(
            "/governance/privacy/processing-records",
            json=payload,
            headers=auth_headers(annotator_token),
        )
        invalid_health = await client.post(
            "/governance/privacy/processing-records",
            json={**payload, "health_data_processed": False},
            headers=auth_headers(admin_token),
        )
        first = await client.post(
            "/governance/privacy/processing-records",
            json=payload,
            headers=auth_headers(admin_token),
        )
        second = await client.post(
            "/governance/privacy/processing-records",
            json={**payload, "approval_reference": "ROPA-APPROVAL-002"},
            headers=auth_headers(admin_token),
        )
        listed = await client.get("/governance/privacy/processing-records", headers=auth_headers(admin_token))
        outside = await client.get("/governance/privacy/processing-records", headers=auth_headers(outside_token))
        self_revoke = await client.post(
            f"/governance/privacy/processing-records/{second.json()['id']}/revoke",
            headers=auth_headers(admin_token),
        )
        revoked = await client.post(
            f"/governance/privacy/processing-records/{second.json()['id']}/revoke",
            headers=auth_headers(privacy_token),
        )
        consultation = await client.post(
            "/governance/privacy/processing-records",
            json={
                **payload,
                "activity_key": "new-high-risk-processing",
                "dpia_outcome": "consultation_required",
                "approval_reference": "ROPA-CONSULT-001",
            },
            headers=auth_headers(admin_token),
        )

        assert policy.status_code == 201
        assert forbidden.status_code == 403
        assert invalid_health.status_code == 422
        assert first.status_code == 201 and first.json()["version"] == 1
        assert second.status_code == 201 and second.json()["version"] == 2
        by_id = {item["id"]: item for item in listed.json()}
        assert by_id[first.json()["id"]]["status"] == "superseded"
        assert by_id[second.json()["id"]]["status"] == "active"
        assert outside.json() == []
        assert self_revoke.status_code == 409
        assert revoked.json()["status"] == "revoked"
        assert consultation.json()["status"] == "consultation_required"

        session_factory = app.state.test_session_factory
        with session_factory() as db:
            audit = db.scalar(
                select(SecurityAuditEvent)
                .where(SecurityAuditEvent.action == "privacy.processing_record_create")
                .order_by(SecurityAuditEvent.occurred_at.desc())
            )
            assert audit is not None
            assert set(audit.details) == {"policy_version", "purpose_code", "workflow_status"}
            assert "DPIA-001" not in json.dumps(audit.details)
            assert "ROPA-APPROVAL" not in json.dumps(audit.details)
            assert verify_integrity(audit, get_settings().audit_signing_key)


@pytest.mark.anyio
async def test_privacy_request_identity_deadline_and_fulfillment_workflow_is_minimized(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    _add_privacy_admins(app)
    raw_subject_reference = "SYNTHETIC-SUBJECT-REFERENCE-001"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        privacy_token = await login(client, "privacy-admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        outside_token = await login(client, "outside-admin@test.local")
        project = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]
        payload = {
            "case_reference": "PRIVACY-CASE-001",
            "external_subject_reference": raw_subject_reference,
            "request_type": "access",
            "scope_type": "project",
            "scope_id": project["id"],
        }
        created = await client.post("/governance/privacy/requests", json=payload, headers=auth_headers(admin_token))
        self_verify = await client.post(
            f"/governance/privacy/requests/{created.json()['id']}/verify-identity",
            json={"evidence_reference": "IDENTITY-001"},
            headers=auth_headers(admin_token),
        )
        verified = await client.post(
            f"/governance/privacy/requests/{created.json()['id']}/verify-identity",
            json={"evidence_reference": "IDENTITY-001"},
            headers=auth_headers(privacy_token),
        )
        accepted = await client.post(
            f"/governance/privacy/requests/{created.json()['id']}/accept",
            json={"evidence_reference": "RIGHTS-REVIEW-001"},
            headers=auth_headers(admin_token),
        )
        wrong_outcome = await client.post(
            f"/governance/privacy/requests/{created.json()['id']}/fulfill",
            json={"evidence_reference": "DELIVERY-001", "outcome_code": "record_corrected"},
            headers=auth_headers(privacy_token),
        )
        fulfilled = await client.post(
            f"/governance/privacy/requests/{created.json()['id']}/fulfill",
            json={"evidence_reference": "DELIVERY-001", "outcome_code": "secure_delivery"},
            headers=auth_headers(privacy_token),
        )

        extension_case = await client.post(
            "/governance/privacy/requests",
            json={**payload, "case_reference": "PRIVACY-CASE-002", "request_type": "rectification"},
            headers=auth_headers(admin_token),
        )
        extended = await client.post(
            f"/governance/privacy/requests/{extension_case.json()['id']}/extend",
            json={"evidence_reference": "EXTENSION-001", "reason_code": "complexity"},
            headers=auth_headers(admin_token),
        )
        repeated_extension = await client.post(
            f"/governance/privacy/requests/{extension_case.json()['id']}/extend",
            json={"evidence_reference": "EXTENSION-002", "reason_code": "request_volume"},
            headers=auth_headers(admin_token),
        )
        denied_case = await client.post(
            "/governance/privacy/requests",
            json={**payload, "case_reference": "PRIVACY-CASE-003", "request_type": "objection"},
            headers=auth_headers(admin_token),
        )
        denied = await client.post(
            f"/governance/privacy/requests/{denied_case.json()['id']}/deny",
            json={"evidence_reference": "IDENTITY-REJECTED-001", "reason_code": "identity_not_verified"},
            headers=auth_headers(privacy_token),
        )
        forbidden = await client.get("/governance/privacy/requests", headers=auth_headers(annotator_token))
        outside = await client.get("/governance/privacy/requests", headers=auth_headers(outside_token))

        body = created.json()
        assert created.status_code == 201
        assert raw_subject_reference not in created.text
        assert "subject_reference_digest" not in body
        assert body["subject_reference_token"].startswith("sha256:")
        assert datetime.fromisoformat(body["response_due_at"]) > datetime.fromisoformat(body["received_at"])
        assert self_verify.status_code == 409
        assert verified.json()["status"] == "identity_verified"
        assert accepted.json()["status"] == "accepted"
        assert wrong_outcome.status_code == 422
        assert fulfilled.json()["status"] == "fulfilled"
        assert fulfilled.json()["deadline_status"] == "completed_on_time"
        assert datetime.fromisoformat(extended.json()["effective_due_at"]) > datetime.fromisoformat(
            extended.json()["response_due_at"]
        )
        assert repeated_extension.status_code == 409
        assert denied.json()["status"] == "denied"
        assert forbidden.status_code == 403
        assert outside.json() == []

        session_factory = app.state.test_session_factory
        with session_factory() as db:
            stored = db.get(PrivacyRequest, UUID(body["id"]))
            assert stored is not None
            assert stored.subject_reference_digest != raw_subject_reference
            assert len(stored.subject_reference_digest) == 64
            audit_rows = list(
                db.scalars(select(SecurityAuditEvent).where(SecurityAuditEvent.action.like("privacy.request_%")))
            )
            serialized_audits = json.dumps([row.details for row in audit_rows])
            assert raw_subject_reference not in serialized_audits
            assert "IDENTITY-001" not in serialized_audits
            assert all(verify_integrity(row, get_settings().audit_signing_key) for row in audit_rows)


@pytest.mark.anyio
async def test_erasure_fulfillment_requires_matching_executed_deletion_receipt(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    _add_privacy_admins(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        privacy_token = await login(client, "privacy-admin@test.local")
        project = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]
        await client.post(
            "/governance/retention-policies",
            json=_policy_payload(),
            headers=auth_headers(admin_token),
        )
        privacy_request = await client.post(
            "/governance/privacy/requests",
            json={
                "case_reference": "ERASURE-CASE-001",
                "external_subject_reference": "SYNTHETIC-ERASURE-SUBJECT",
                "request_type": "erasure",
                "scope_type": "project",
                "scope_id": project["id"],
            },
            headers=auth_headers(admin_token),
        )
        deletion = await client.post(
            "/governance/deletion-requests",
            json={
                "scope_type": "project",
                "scope_id": project["id"],
                "reason_code": "erasure_request",
                "approval_reference": "ERASURE-DELETE-001",
            },
            headers=auth_headers(admin_token),
        )
        await client.post(
            f"/governance/privacy/requests/{privacy_request.json()['id']}/verify-identity",
            json={"evidence_reference": "ERASURE-IDENTITY-001"},
            headers=auth_headers(privacy_token),
        )
        accepted = await client.post(
            f"/governance/privacy/requests/{privacy_request.json()['id']}/accept",
            json={
                "evidence_reference": "ERASURE-REVIEW-001",
                "linked_deletion_request_id": deletion.json()["id"],
            },
            headers=auth_headers(admin_token),
        )
        premature = await client.post(
            f"/governance/privacy/requests/{privacy_request.json()['id']}/fulfill",
            json={"evidence_reference": "ERASURE-RECEIPT-001", "outcome_code": "erasure_verified"},
            headers=auth_headers(privacy_token),
        )
        assert accepted.json()["status"] == "accepted"
        assert premature.status_code == 409

        session_factory = app.state.test_session_factory
        with session_factory() as db:
            deletion_row = db.get(DataDeletionRequest, UUID(deletion.json()["id"]))
            approver = db.scalar(select(User).where(User.email == "privacy-admin@test.local"))
            operator = db.scalar(select(User).where(User.email == "privacy-operator@test.local"))
            assert deletion_row is not None and approver is not None and operator is not None
            completed_at = datetime.now(timezone.utc)
            db.add(
                DataDeletionEvent(
                    request_id=deletion_row.id,
                    organization_id=deletion_row.organization_id,
                    action="executed",
                    actor_user_id=operator.id,
                    occurred_at=completed_at,
                )
            )
            db.add(
                DataDeletionReceipt(
                    request_id=deletion_row.id,
                    organization_id=deletion_row.organization_id,
                    scope_type=deletion_row.scope_type,
                    scope_id=deletion_row.scope_id,
                    deleted_counts={"synthetic_records": 1},
                    object_versions_deleted=1,
                    delete_markers_deleted=0,
                    revoked_releases=0,
                    backup_disposition="expires_per_policy",
                    backup_expires_at=None,
                    approved_by_user_id=approver.id,
                    operator_user_id=operator.id,
                    receipt_sha256="f" * 64,
                    completed_at=completed_at,
                )
            )
            db.commit()

        fulfilled = await client.post(
            f"/governance/privacy/requests/{privacy_request.json()['id']}/fulfill",
            json={"evidence_reference": "ERASURE-RECEIPT-001", "outcome_code": "erasure_verified"},
            headers=auth_headers(privacy_token),
        )
        assert fulfilled.status_code == 200
        assert fulfilled.json()["status"] == "fulfilled"
        assert fulfilled.json()["events"][-1]["linked_deletion_request_id"] == deletion.json()["id"]


def test_privacy_records_are_orm_and_database_append_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = build_test_app(tmp_path / "app")
    _add_privacy_admins(app)
    session_factory = app.state.test_session_factory
    with session_factory() as db:
        organization = db.scalar(select(Organization).where(Organization.name == "Route Test Lab"))
        admin = db.scalar(select(User).where(User.email == "admin@test.local"))
        policy = db.scalar(select(DataDeletionRequest))
        assert organization is not None and admin is not None and policy is None
        request = PrivacyRequest(
            organization_id=organization.id,
            case_reference="IMMUTABLE-CASE-001",
            subject_reference_digest="a" * 64,
            request_type="access",
            scope_type="organization",
            scope_id=organization.id,
            received_at=datetime.now(timezone.utc),
            response_due_at=datetime.now(timezone.utc),
            created_by_user_id=admin.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(request)
        db.commit()
        request.case_reference = "CHANGED"
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()

    database_url = f"sqlite:///{tmp_path / 'privacy-trigger.db'}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'Privacy Org')"), {"id": "1" * 32})
        connection.execute(
            text(
                "INSERT INTO privacy_requests "
                "(id, organization_id, case_reference, subject_reference_digest, request_type, scope_type, scope_id, "
                "received_at, response_due_at, created_by_user_id, created_at) VALUES "
                "(:id, :organization_id, 'CASE-DB-001', :digest, 'access', 'organization', :scope_id, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :actor_id, CURRENT_TIMESTAMP)"
            ),
            {
                "id": "2" * 32,
                "organization_id": "1" * 32,
                "scope_id": "1" * 32,
                "digest": "d" * 64,
                "actor_id": "3" * 32,
            },
        )

    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE privacy_requests SET case_reference = 'CHANGED'"))
    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM privacy_requests"))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT case_reference FROM privacy_requests")) == "CASE-DB-001"
