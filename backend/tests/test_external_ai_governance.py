"""External AI default-denial, approval, tenant, audit, and immutability proofs."""

import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError

from backend.models import ExternalAIDataFlowApproval, ExternalAIProviderApproval, Organization, Scan, User
from backend.security import hash_password
from backend.services.external_ai_governance_service import flow_status, provider_status
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login
from scripts.verify_external_ai_egress import verify_repository


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _add_second_admin(app: object) -> None:
    session_factory = app.state.test_session_factory  # type: ignore[attr-defined]
    with session_factory() as db:
        organization = db.scalar(select(Organization).where(Organization.name == "Route Test Lab"))
        assert organization is not None
        db.add(
            User(
                organization_id=organization.id,
                email="ai-governance-admin@test.local",
                full_name="AI Governance Admin",
                password_hash=hash_password("password"),
                role="admin",
            )
        )
        db.commit()


def _provider_payload(reference: str = "AI-PROVIDER-001", model_version: str = "2026-07-16") -> dict[str, object]:
    return {
        "provider_key": "approved-gateway",
        "display_name": "Approved Gateway",
        "model_name": "Synthetic Model",
        "model_version": model_version,
        "purpose_code": "annotation_assistance",
        "endpoint_origin": "https://ai-gateway.example.org",
        "region_code": "eu-central",
        "data_classes": ["label_taxonomy", "deidentified_pixels"],
        "retention_days": 0,
        "training_use_allowed": False,
        "subprocessors": ["SUBPROCESSOR-REGISTRY-001"],
        "transfer_mechanism": "standard_contractual_clauses",
        "contract_owner_reference": "CONTRACT-OWNER-001",
        "approval_reference": reference,
    }


@pytest.mark.anyio
async def test_external_ai_registry_is_admin_only_tenant_scoped_versioned_and_audited(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    _add_second_admin(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        second_admin_token = await login(client, "ai-governance-admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        outside_token = await login(client, "outside-admin@test.local")

        status_response = await client.get("/governance/external-ai/status", headers=auth_headers(admin_token))
        forbidden = await client.post(
            "/governance/external-ai/providers",
            json=_provider_payload(),
            headers=auth_headers(annotator_token),
        )
        raw_dicom = await client.post(
            "/governance/external-ai/providers",
            json={**_provider_payload(), "data_classes": ["raw_dicom"]},
            headers=auth_headers(admin_token),
        )
        training = await client.post(
            "/governance/external-ai/providers",
            json={**_provider_payload(), "training_use_allowed": True},
            headers=auth_headers(admin_token),
        )
        first = await client.post(
            "/governance/external-ai/providers",
            json=_provider_payload(),
            headers=auth_headers(admin_token),
        )
        second = await client.post(
            "/governance/external-ai/providers",
            json=_provider_payload("AI-PROVIDER-002", "2026-08-01"),
            headers=auth_headers(admin_token),
        )
        outside_list = await client.get("/governance/external-ai/providers", headers=auth_headers(outside_token))
        same_actor_revoke = await client.post(
            f"/governance/external-ai/providers/{first.json()['id']}/revoke",
            headers=auth_headers(admin_token),
        )
        revoked = await client.post(
            f"/governance/external-ai/providers/{first.json()['id']}/revoke",
            headers=auth_headers(second_admin_token),
        )

        assert status_response.status_code == 200
        assert status_response.json() == {
            "enabled": False,
            "allowed_origins": [],
            "provider_network_call_implemented": False,
            "permanently_prohibited_data_classes": [
                "direct_identifiers",
                "free_text_clinical_notes",
                "raw_dicom",
                "raw_dicom_metadata",
            ],
        }
        assert forbidden.status_code == 403
        assert raw_dicom.status_code == 422
        assert training.status_code == 422
        assert first.status_code == 201 and first.json()["version"] == 1
        assert second.status_code == 201 and second.json()["version"] == 2
        assert outside_list.json() == []
        assert same_actor_revoke.status_code == 409
        assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"

        serialized = json.dumps(revoked.json())
        assert "Brain MRI" not in serialized
        assert "test.nii.gz" not in serialized
        for action in ("external_ai.status", "external_ai.provider_create", "external_ai.provider_revoke"):
            audit = await client.get(f"/audit-events?action={action}", headers=auth_headers(admin_token))
            assert any(event["result"] == "succeeded" for event in audit.json())
            assert all("approval_reference" not in event["details"] for event in audit.json())


@pytest.mark.anyio
async def test_external_ai_egress_requires_every_gate_and_never_calls_a_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_test_app(tmp_path)
    _add_second_admin(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        second_admin_token = await login(client, "ai-governance-admin@test.local")
        project = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]
        provider = await client.post(
            "/governance/external-ai/providers",
            json=_provider_payload(),
            headers=auth_headers(admin_token),
        )
        flow = await client.post(
            "/governance/external-ai/data-flows",
            json={
                "project_id": project["id"],
                "provider_approval_id": provider.json()["id"],
                "purpose_code": "annotation_assistance",
                "data_classes": ["label_taxonomy", "deidentified_pixels"],
                "approval_reference": "AI-FLOW-001",
            },
            headers=auth_headers(admin_token),
        )
        duplicate = await client.post(
            "/governance/external-ai/data-flows",
            json={
                "project_id": project["id"],
                "provider_approval_id": provider.json()["id"],
                "purpose_code": "annotation_assistance",
                "data_classes": ["label_taxonomy"],
                "approval_reference": "AI-FLOW-002",
            },
            headers=auth_headers(admin_token),
        )
        default_denied = await client.post(
            "/governance/external-ai/evaluate",
            json={
                "data_flow_id": flow.json()["id"],
                "purpose_code": "annotation_assistance",
                "requested_data_classes": ["label_taxonomy"],
            },
            headers=auth_headers(admin_token),
        )

        assert provider.status_code == 201
        assert flow.status_code == 201
        assert duplicate.status_code == 409
        assert default_denied.json()["result"] == "denied"
        assert default_denied.json()["reason_code"] == "feature_disabled"

        monkeypatch.setenv("EXTERNAL_AI_ENABLED", "true")
        monkeypatch.setenv("EXTERNAL_AI_ALLOWED_ORIGINS", "https://ai-gateway.example.org")
        allowed = await client.post(
            "/governance/external-ai/evaluate",
            json={
                "data_flow_id": flow.json()["id"],
                "purpose_code": "annotation_assistance",
                "requested_data_classes": ["label_taxonomy"],
            },
            headers=auth_headers(admin_token),
        )
        wrong_purpose = await client.post(
            "/governance/external-ai/evaluate",
            json={
                "data_flow_id": flow.json()["id"],
                "purpose_code": "quality_assurance",
                "requested_data_classes": ["label_taxonomy"],
            },
            headers=auth_headers(admin_token),
        )

        assert allowed.json()["result"] == "allowed"
        assert allowed.json()["reason_code"] == "authorized"
        assert wrong_purpose.json()["reason_code"] == "purpose_not_approved"

        session_factory = app.state.test_session_factory
        with session_factory() as db:
            scan = db.scalar(select(Scan).where(Scan.project_id == UUID(project["id"])))
            assert scan is not None
            scan.source_format = "nifti"
            scan.ingestion_status = "quarantined"
            scan.deidentification_status = "quarantined"
            db.commit()

        unsafe_dataset = await client.post(
            "/governance/external-ai/evaluate",
            json={
                "data_flow_id": flow.json()["id"],
                "purpose_code": "annotation_assistance",
                "requested_data_classes": ["deidentified_pixels"],
            },
            headers=auth_headers(admin_token),
        )
        assert unsafe_dataset.json()["reason_code"] == "dataset_not_deidentified"

        monkeypatch.setenv("EXTERNAL_AI_ALLOWED_ORIGINS", "https://different-gateway.example.org")
        wrong_origin = await client.post(
            "/governance/external-ai/evaluate",
            json={
                "data_flow_id": flow.json()["id"],
                "purpose_code": "annotation_assistance",
                "requested_data_classes": ["label_taxonomy"],
            },
            headers=auth_headers(admin_token),
        )
        assert wrong_origin.json()["reason_code"] == "origin_not_allowlisted"

        same_actor_revoke = await client.post(
            f"/governance/external-ai/data-flows/{flow.json()['id']}/revoke",
            headers=auth_headers(admin_token),
        )
        revoked = await client.post(
            f"/governance/external-ai/data-flows/{flow.json()['id']}/revoke",
            headers=auth_headers(second_admin_token),
        )
        monkeypatch.setenv("EXTERNAL_AI_ALLOWED_ORIGINS", "https://ai-gateway.example.org")
        revoked_denied = await client.post(
            "/governance/external-ai/evaluate",
            json={
                "data_flow_id": flow.json()["id"],
                "purpose_code": "annotation_assistance",
                "requested_data_classes": ["label_taxonomy"],
            },
            headers=auth_headers(admin_token),
        )
        outside_decisions = await client.get(
            "/governance/external-ai/decisions", headers=auth_headers(await login(client, "outside-admin@test.local"))
        )

        assert same_actor_revoke.status_code == 409
        assert revoked.json()["status"] == "revoked"
        assert revoked_denied.json()["reason_code"] == "flow_revoked"
        assert outside_decisions.json() == []

        decisions = await client.get("/governance/external-ai/decisions", headers=auth_headers(admin_token))
        assert len(decisions.json()) == 6
        serialized = json.dumps(decisions.json())
        for private_value in ("Brain MRI", "test.nii.gz", "coordinates", "notes", "patient"):
            assert private_value not in serialized
        audit = await client.get("/audit-events?action=external_ai.egress_evaluate", headers=auth_headers(admin_token))
        assert any(event["details"].get("decision_result") == "allowed" for event in audit.json())
        assert any(event["details"].get("reason_code") == "feature_disabled" for event in audit.json())


def test_external_ai_records_are_orm_and_database_append_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = build_test_app(tmp_path / "app")
    session_factory = app.state.test_session_factory
    with session_factory() as db:
        organization = db.scalar(select(Organization).where(Organization.name == "Route Test Lab"))
        admin = db.scalar(select(User).where(User.email == "admin@test.local"))
        assert organization is not None and admin is not None
        provider = ExternalAIProviderApproval(
            organization_id=organization.id,
            provider_key="immutable-provider",
            version=1,
            display_name="Immutable Provider",
            model_name="Synthetic Model",
            model_version="v1",
            purpose_code="research_inference",
            endpoint_origin="https://gateway.example.org",
            region_code="eu-central",
            data_classes=["label_taxonomy"],
            retention_days=0,
            training_use_allowed=False,
            subprocessors=[],
            transfer_mechanism="not_applicable",
            contract_owner_reference="OWNER-001",
            approval_reference="APPROVAL-001",
            created_by_user_id=admin.id,
            created_at=admin.created_at,
        )
        db.add(provider)
        db.commit()
        provider.version = 2
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()

    database_url = f"sqlite:///{tmp_path / 'external-ai-trigger.db'}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'AI Governance Org')"), {"id": "1" * 32})
        connection.execute(
            text(
                "INSERT INTO external_ai_provider_approvals "
                "(id, organization_id, provider_key, version, display_name, model_name, model_version, purpose_code, "
                "endpoint_origin, region_code, data_classes, retention_days, training_use_allowed, subprocessors, "
                "transfer_mechanism, contract_owner_reference, approval_reference, created_by_user_id, created_at) VALUES "
                "(:id, :organization_id, 'db-provider', 1, 'DB Provider', 'Synthetic Model', 'v1', 'research_inference', "
                "'https://gateway.example.org', 'eu-central', '[\"label_taxonomy\"]', 0, 0, '[]', 'not_applicable', "
                "'OWNER-DB', 'APPROVAL-DB', :actor_id, CURRENT_TIMESTAMP)"
            ),
            {"id": "2" * 32, "organization_id": "1" * 32, "actor_id": "3" * 32},
        )

    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE external_ai_provider_approvals SET version = 2"))
    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM external_ai_provider_approvals"))


def test_static_external_ai_policy_rejects_runtime_network_clients(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    assert verify_repository(root) == []

    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "unsafe.py").write_text("import httpx\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("EXTERNAL_AI_ENABLED=false\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        "EXTERNAL_AI_ENABLED: ${EXTERNAL_AI_ENABLED:-false}\n", encoding="utf-8"
    )
    (tmp_path / "backend" / "settings.py").write_text(
        'values.get("EXTERNAL_AI_ENABLED", "false")\n', encoding="utf-8"
    )
    errors = verify_repository(tmp_path)
    assert any("restricted runtime import httpx" in error for error in errors)


def test_missing_approval_events_fail_closed() -> None:
    assert provider_status([]) == "unapproved"
    flow = ExternalAIDataFlowApproval(expires_at=None)
    assert flow_status(flow, []) == "unapproved"
