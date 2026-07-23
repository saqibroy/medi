"""Security and reproducibility tests for immutable dataset releases."""

import hashlib
import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError

from backend.models import Annotation, DatasetRelease, DatasetReleaseArtifact, DatasetReleaseEvent
from backend.services.dataset_release_service import sha256_json
from backend.tests.fixtures.imaging import write_synthetic_dicom
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login, make_png_bytes


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _project(projects: list[dict[str, object]], name: str = "Brain MRI") -> dict[str, object]:
    return next(project for project in projects if project["name"] == name)


def _seeded_annotation_id(app: object) -> UUID:
    session_factory = app.state.test_session_factory  # type: ignore[attr-defined]
    with session_factory() as db:
        annotation = db.scalar(select(Annotation).where(Annotation.label == "tumour"))
        assert annotation is not None
        return annotation.id


@pytest.mark.anyio
async def test_release_is_admin_only_tenant_scoped_minimized_and_audited(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        outside_token = await login(client, "outside-admin@test.local")
        project = _project((await client.get("/projects", headers=auth_headers(admin_token))).json())
        annotation_id = _seeded_annotation_id(app)

        reviewed = await client.patch(
            f"/annotations/{annotation_id}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": "Patient Jane Doe is ready."},
            headers=auth_headers(reviewer_token),
        )
        forbidden = await client.post(f"/projects/{project['id']}/releases", headers=auth_headers(annotator_token))
        created = await client.post(f"/projects/{project['id']}/releases", headers=auth_headers(admin_token))

        assert reviewed.status_code == 200
        assert forbidden.status_code == 403
        assert created.status_code == 201
        release = created.json()
        manifest = release["manifest"]
        serialized = json.dumps(manifest, sort_keys=True)
        assert release["version"] == 1
        assert release["status"] == "active"
        assert release["manifest_sha256"] == sha256_json(manifest)
        assert release["content_sha256"] == sha256_json(manifest["dataset"])
        assert len(release["artifacts"]) == 1
        artifact = release["artifacts"][0]
        assert artifact["artifact_type"] == "portable_manifest"
        assert artifact["checksum_sha256"] == release["manifest_sha256"]
        assert artifact["byte_size"] == len(
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        assert manifest["dataset"]["counts"]["approved_annotations"] == 1
        assert manifest["dataset"]["project"] == {"project_id": project["id"], "modality": "MRI"}
        for private_value in (
            "Brain MRI",
            "test.nii.gz",
            "Admin User",
            "Annotator User",
            "Reviewer User",
            "Patient Jane Doe",
            "storage_key",
            "file_path",
        ):
            assert private_value not in serialized

        listed = await client.get(f"/projects/{project['id']}/releases", headers=auth_headers(annotator_token))
        loaded = await client.get(f"/dataset-releases/{release['id']}", headers=auth_headers(admin_token))
        outside = await client.get(f"/dataset-releases/{release['id']}", headers=auth_headers(outside_token))
        downloaded = await client.get(f"/dataset-releases/{release['id']}/artifact", headers=auth_headers(annotator_token))
        outside_download = await client.get(f"/dataset-releases/{release['id']}/artifact", headers=auth_headers(outside_token))
        forbidden_materialize = await client.post(
            f"/dataset-releases/{release['id']}/artifact",
            headers=auth_headers(annotator_token),
        )
        idempotent_materialize = await client.post(
            f"/dataset-releases/{release['id']}/artifact",
            headers=auth_headers(admin_token),
        )
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == release["id"]
        assert listed.json()[0]["artifacts"] == [artifact]
        assert "manifest" not in listed.json()[0]
        assert loaded.json()["manifest"] == manifest
        assert outside.status_code == 404
        assert downloaded.status_code == 200
        assert downloaded.json() == manifest
        assert downloaded.headers["x-content-sha256"] == release["manifest_sha256"]
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert "attachment; filename=" in downloaded.headers["content-disposition"]
        assert outside_download.status_code == 404
        assert forbidden_materialize.status_code == 403
        assert idempotent_materialize.status_code == 200
        assert idempotent_materialize.json()["id"] == artifact["id"]

        for action in (
            "dataset_release.create",
            "dataset_release.list",
            "dataset_release.read",
            "dataset_release_artifact.create",
            "dataset_release_artifact.download",
        ):
            events = await client.get(f"/audit-events?action={action}", headers=auth_headers(admin_token))
            assert events.status_code == 200
            assert any(event["result"] == "succeeded" for event in events.json())
            assert all("manifest" not in json.dumps(event) for event in events.json())


@pytest.mark.anyio
async def test_release_versions_remain_frozen_and_lifecycle_is_append_only(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project = _project((await client.get("/projects", headers=auth_headers(admin_token))).json())
        annotation_id = _seeded_annotation_id(app)
        approved = await client.patch(
            f"/annotations/{annotation_id}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": "First review"},
            headers=auth_headers(reviewer_token),
        )
        first = await client.post(f"/projects/{project['id']}/releases", headers=auth_headers(admin_token))
        first_body = first.json()

        updated = await client.put(
            f"/annotations/{annotation_id}",
            json={"coordinates": {"x": 12, "y": 14, "width": 24, "height": 28}, "notes": "Changed after v1"},
            headers=auth_headers(annotator_token),
        )
        second = await client.post(f"/projects/{project['id']}/releases", headers=auth_headers(admin_token))
        frozen_first = await client.get(f"/dataset-releases/{first_body['id']}", headers=auth_headers(admin_token))

        assert approved.status_code == 200
        assert first.status_code == 201
        assert updated.status_code == 200
        assert second.status_code == 201
        second_body = second.json()
        assert frozen_first.json()["status"] == "superseded"
        assert frozen_first.json()["manifest"] == first_body["manifest"]
        assert frozen_first.json()["manifest_sha256"] == first_body["manifest_sha256"]
        assert second_body["version"] == 2
        assert second_body["supersedes_release_id"] == first_body["id"]
        assert second_body["content_sha256"] != first_body["content_sha256"]
        superseded_download = await client.get(
            f"/dataset-releases/{first_body['id']}/artifact",
            headers=auth_headers(admin_token),
        )
        assert superseded_download.status_code == 200
        assert superseded_download.json() == first_body["manifest"]

        revoked = await client.post(
            f"/dataset-releases/{second_body['id']}/revoke",
            json={"reason_code": "quality_issue"},
            headers=auth_headers(admin_token),
        )
        duplicate = await client.post(
            f"/dataset-releases/{second_body['id']}/revoke",
            json={"reason_code": "quality_issue"},
            headers=auth_headers(admin_token),
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert revoked.json()["manifest"] == second_body["manifest"]
        assert duplicate.status_code == 409
        revoked_download = await client.get(
            f"/dataset-releases/{second_body['id']}/artifact",
            headers=auth_headers(admin_token),
        )
        assert revoked_download.status_code == 410
        audit = await client.get("/audit-events?action=dataset_release.revoke", headers=auth_headers(admin_token))
        assert {event["result"] for event in audit.json()} >= {"succeeded", "failed"}

    session_factory = app.state.test_session_factory
    with session_factory() as db:
        release = db.get(DatasetRelease, UUID(first_body["id"]))
        assert release is not None
        release.version = 99
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()
    with session_factory() as db:
        event = db.scalar(select(DatasetReleaseEvent).where(DatasetReleaseEvent.release_id == UUID(first_body["id"])))
        assert event is not None
        db.delete(event)
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()
    with session_factory() as db:
        artifact = db.scalar(
            select(DatasetReleaseArtifact).where(DatasetReleaseArtifact.release_id == UUID(first_body["id"]))
        )
        assert artifact is not None
        artifact.byte_size += 1
        with pytest.raises(ValueError, match="append-only"):
            db.commit()


@pytest.mark.anyio
async def test_release_artifact_download_fails_closed_after_object_tampering(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        project = _project((await client.get("/projects", headers=auth_headers(admin_token))).json())
        release = await client.post(f"/projects/{project['id']}/releases", headers=auth_headers(admin_token))
        assert release.status_code == 201

        session_factory = app.state.test_session_factory  # type: ignore[attr-defined]
        with session_factory() as db:
            artifact = db.scalar(
                select(DatasetReleaseArtifact).where(
                    DatasetReleaseArtifact.release_id == UUID(release.json()["id"])
                )
            )
            assert artifact is not None
            storage_key = artifact.storage_key
        artifact_path = tmp_path / storage_key
        assert artifact_path.is_file()
        artifact_path.write_bytes(b'{"tampered":true}')

        blocked = await client.get(
            f"/dataset-releases/{release.json()['id']}/artifact",
            headers=auth_headers(admin_token),
        )
        assert blocked.status_code == 409
        assert "integrity verification failed" in blocked.json()["detail"]


@pytest.mark.anyio
async def test_release_captures_deidentified_original_and_mask_object_evidence(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        project = _project((await client.get("/projects", headers=auth_headers(admin_token))).json())
        label = (await client.get(f"/projects/{project['id']}/labels", headers=auth_headers(admin_token))).json()[0]
        fixture_path = write_synthetic_dicom(tmp_path / "private-patient-name.dcm", width=6, height=4)
        dicom_bytes = fixture_path.read_bytes()
        uploaded = await client.post(
            "/scans/upload",
            data={"project_id": project["id"], "name": "Synthetic CT", "modality": "CT"},
            files={"file": ("private-patient-name.dcm", dicom_bytes, "application/dicom")},
            headers=auth_headers(admin_token),
        )
        scan = uploaded.json()
        created = await client.post(
            "/annotations",
            json={
                "project_id": project["id"],
                "scan_id": scan["id"],
                "label_id": label["id"],
                "label": label["name"],
                "annotation_type": "segmentation",
                "coordinates": {"mask_ref": True, "representation": "png_binary"},
                "slice_index": 0,
                "created_by": "Annotator User",
            },
            headers=auth_headers(annotator_token),
        )
        reviewed = await client.patch(
            f"/annotations/{created.json()['id']}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": "Do not export this note"},
            headers=auth_headers(reviewer_token),
        )
        rejected_missing_mask = await client.post(f"/projects/{project['id']}/releases", headers=auth_headers(admin_token))
        mask_png = make_png_bytes(6, 4)
        stored = await client.post(
            f"/annotations/{created.json()['id']}/mask",
            data={"slice_index": "0"},
            files={"file": ("mask.png", mask_png, "image/png")},
            headers=auth_headers(annotator_token),
        )
        released = await client.post(f"/projects/{project['id']}/releases", headers=auth_headers(admin_token))

        assert uploaded.status_code == 201
        assert scan["deidentification_status"] == "passed"
        assert created.status_code == 201
        assert reviewed.status_code == 200
        assert rejected_missing_mask.status_code == 409
        assert "has no mask" in rejected_missing_mask.json()["detail"]
        assert stored.status_code == 201
        assert released.status_code == 201
        dataset = released.json()["manifest"]["dataset"]
        released_scan = next(item for item in dataset["scans"] if item["scan_id"] == scan["id"])
        original = released_scan["original_object"]
        annotation = released_scan["approved_annotations"][0]
        mask = annotation["segmentation_mask"]
        assert original["checksum_sha256"] == hashlib.sha256(dicom_bytes).hexdigest()
        assert original["version_id"].startswith("local-sha256:")
        assert original["byte_size"] == len(dicom_bytes)
        assert mask["checksum_sha256"] == stored.json()["checksum_sha256"]
        assert mask["version_id"].startswith("local-sha256:")
        assert mask["byte_size"] == len(mask_png)
        assert {entry["action"] for entry in annotation["lineage"]} >= {"mask_uploaded", "reviewed"}
        serialized = json.dumps(released.json()["manifest"])
        for private_value in ("private-patient-name.dcm", "Do not export this note", "storage_key", "file_path"):
            assert private_value not in serialized


def test_migration_triggers_reject_release_and_lifecycle_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "dataset-release-triggers.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    organization_id = "1" * 32
    project_id = "2" * 32
    release_id = "3" * 32
    event_id = "4" * 32
    actor_id = "5" * 32
    artifact_id = "6" * 32
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'Release Org')"), {"id": organization_id})
        connection.execute(
            text("INSERT INTO projects (id, organization_id, name, modality) VALUES (:id, :organization_id, 'Release Project', 'MRI')"),
            {"id": project_id, "organization_id": organization_id},
        )
        connection.execute(
            text(
                "INSERT INTO dataset_releases "
                "(id, organization_id, project_id, version, schema_version, content_sha256, manifest_sha256, manifest, "
                "created_by_user_id, created_at) VALUES "
                "(:id, :organization_id, :project_id, 1, 'test-v1', :content_hash, :manifest_hash, '{}', :actor_id, CURRENT_TIMESTAMP)"
            ),
            {
                "id": release_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "content_hash": "a" * 64,
                "manifest_hash": "b" * 64,
                "actor_id": actor_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO dataset_release_events "
                "(id, release_id, organization_id, actor_user_id, action, occurred_at) "
                "VALUES (:id, :release_id, :organization_id, :actor_id, 'created', CURRENT_TIMESTAMP)"
            ),
            {"id": event_id, "release_id": release_id, "organization_id": organization_id, "actor_id": actor_id},
        )
        connection.execute(
            text(
                "INSERT INTO dataset_release_artifacts "
                "(id, release_id, organization_id, project_id, artifact_type, schema_version, media_type, "
                "storage_key, object_version_id, checksum_sha256, byte_size, created_by_user_id, created_at) "
                "VALUES (:id, :release_id, :organization_id, :project_id, 'portable_manifest', 'artifact-v1', "
                "'application/json', 'org/test/release-artifact/test/manifest.json', 'version-1', :checksum, "
                "2, :actor_id, CURRENT_TIMESTAMP)"
            ),
            {
                "id": artifact_id,
                "release_id": release_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "checksum": "c" * 64,
                "actor_id": actor_id,
            },
        )

    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE dataset_releases SET version = 2"))
    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM dataset_release_events"))
    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE dataset_release_artifacts SET byte_size = 3"))
    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM dataset_release_artifacts"))

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version FROM dataset_releases")) == 1
        assert connection.scalar(text("SELECT COUNT(*) FROM dataset_release_events")) == 1
        assert connection.scalar(text("SELECT byte_size FROM dataset_release_artifacts")) == 2
