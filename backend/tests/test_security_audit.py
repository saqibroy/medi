"""Security and data-minimization proofs for the append-only audit ledger."""

import json
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError

from backend.models import SecurityAuditEvent
from backend.services.audit_service import verify_integrity
from backend.settings import DEVELOPMENT_AUDIT_SIGNING_KEY
from backend.tests.fixtures.imaging import write_synthetic_dicom
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_audit_api_is_admin_only_tenant_scoped_and_data_minimized(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        failed_login = await client.post(
            "/auth/login",
            json={"email": "unknown-patient@example.test", "password": "never-store-this-password"},
        )
        assert failed_login.status_code == 401

        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        outside_token = await login(client, "outside-admin@test.local")

        forbidden_create = await client.post(
            "/projects",
            json={"name": "Forbidden project", "description": "private free text", "modality": "MRI"},
            headers=auth_headers(annotator_token),
        )
        assert forbidden_create.status_code == 403

        created = await client.post(
            "/projects",
            json={"name": "Audited project", "description": "patient-related free text", "modality": "CT"},
            headers=auth_headers(admin_token),
        )
        assert created.status_code == 201

        non_admin_list = await client.get("/audit-events", headers=auth_headers(annotator_token))
        assert non_admin_list.status_code == 403

        admin_list = await client.get("/audit-events", headers=auth_headers(admin_token))
        assert admin_list.status_code == 200
        events = admin_list.json()
        actions_and_results = {(event["action"], event["result"]) for event in events}
        assert ("auth.login", "succeeded") in actions_and_results
        assert ("project.create", "succeeded") in actions_and_results
        assert ("project.create", "denied") in actions_and_results
        assert ("audit.list", "denied") in actions_and_results
        assert all(event["organization_id"] == events[0]["organization_id"] for event in events)
        assert all(event["request_id"] for event in events)
        assert all(len(event["integrity_hash"]) == 64 for event in events)

        serialized = json.dumps(events)
        for forbidden_value in (
            "unknown-patient@example.test",
            "never-store-this-password",
            "admin@test.local",
            "patient-related free text",
            "private free text",
        ):
            assert forbidden_value not in serialized

        outside_list = await client.get("/audit-events", headers=auth_headers(outside_token))
        assert outside_list.status_code == 200
        outside_events = outside_list.json()
        assert outside_events
        assert {event["organization_id"] for event in outside_events}.isdisjoint(
            {event["organization_id"] for event in events}
        )

    with app.state.test_session_factory() as db:
        event = db.scalar(select(SecurityAuditEvent).where(SecurityAuditEvent.action == "project.create", SecurityAuditEvent.result == "succeeded"))
        assert event is not None
        assert verify_integrity(event, DEVELOPMENT_AUDIT_SIGNING_KEY)
        event.action = "tampered"
        assert not verify_integrity(event, DEVELOPMENT_AUDIT_SIGNING_KEY)
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()

        event = db.scalar(select(SecurityAuditEvent).limit(1))
        assert event is not None
        db.delete(event)
        with pytest.raises(ValueError, match="append-only"):
            db.commit()


@pytest.mark.anyio
async def test_priority_imaging_export_and_annotation_paths_emit_safe_events(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        token = await login(client, "admin@test.local")
        headers = auth_headers(token)
        project_id = (await client.get("/projects", headers=headers)).json()[0]["id"]
        scan = (await client.get(f"/projects/{project_id}/scans", headers=headers)).json()[0]
        label = (await client.get(f"/projects/{project_id}/labels", headers=headers)).json()[0]

        slice_read = await client.get(f"/scans/{scan['id']}/slice/0", headers=headers)
        export = await client.get(f"/projects/{project_id}/export/coco", headers=headers)
        assert slice_read.status_code == 200
        assert export.status_code == 200

        annotation = await client.post(
            "/annotations",
            json={
                "project_id": project_id,
                "scan_id": scan["id"],
                "label_id": label["id"],
                "label": label["name"],
                "annotation_type": "bounding_box",
                "coordinates": {"x": 1, "y": 1, "width": 2, "height": 2},
                "slice_index": 0,
                "created_by": "Audit Admin",
            },
            headers=headers,
        )
        annotation_id = annotation.json()["id"]
        assert annotation.status_code == 201
        assert (await client.put(f"/annotations/{annotation_id}", json={"confidence_score": 0.9}, headers=headers)).status_code == 200
        assert (
            await client.patch(
                f"/annotations/{annotation_id}/review",
                json={"reviewer": "Audit Admin", "review_status": "approved", "notes": "must not enter audit"},
                headers=headers,
            )
        ).status_code == 200
        assert (await client.delete(f"/annotations/{annotation_id}", headers=headers)).status_code == 204

        dicom_path = write_synthetic_dicom(
            tmp_path / "sensitive-name.dcm",
            patient_name="Private^Patient",
            patient_id="PRIVATE-MRN-42",
        )
        uploaded = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Quarantined CT", "modality": "CT"},
            files={"file": ("PRIVATE-MRN-42.dcm", dicom_path.read_bytes(), "application/dicom")},
            headers=headers,
        )
        assert uploaded.status_code == 201
        assert uploaded.json()["deidentification_status"] == "quarantined"

        events_response = await client.get("/audit-events?limit=100", headers=headers)
        assert events_response.status_code == 200
        events = events_response.json()
        actions = {event["action"] for event in events}
        assert {
            "scan.slice_read",
            "project.export",
            "annotation.create",
            "annotation.update",
            "annotation.review",
            "annotation.delete",
            "scan.upload",
        }.issubset(actions)

        upload_event = next(event for event in events if event["action"] == "scan.upload")
        assert upload_event["target_id"] == uploaded.json()["id"]
        assert upload_event["details"] == {
            "source_format": "dicom",
            "ingestion_status": "quarantined",
            "deidentification_status": "quarantined",
            "deidentification_profile_version": "medi-deid-screening-v1",
        }
        serialized = json.dumps(events)
        assert "Private^Patient" not in serialized
        assert "PRIVATE-MRN-42" not in serialized
        assert "must not enter audit" not in serialized


def test_migration_database_triggers_reject_update_and_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "audit-trigger.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'Audit Org')"), {"id": "1" * 32})
        connection.execute(
            text(
                "INSERT INTO security_audit_events "
                "(id, organization_id, action, result, details, integrity_hash, occurred_at) "
                "VALUES (:id, :organization_id, 'test.event', 'succeeded', '{}', :hash, CURRENT_TIMESTAMP)"
            ),
            {"id": "2" * 32, "organization_id": "1" * 32, "hash": "a" * 64},
        )

    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE security_audit_events SET action = 'rewritten'"))

    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM security_audit_events"))

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM security_audit_events")) == 1
