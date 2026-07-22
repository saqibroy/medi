"""Retention, minimization, integrity, and immutability proofs for history tombstones."""

import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DatabaseError

from backend.models import Annotation, AnnotationHistory, AnnotationHistoryTombstone, Project
from backend.services.annotation_history_tombstone_service import verify_tombstone_integrity
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_annotation_delete_retains_only_minimized_immutable_lineage_evidence(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        annotation = (await client.get("/annotations", headers=auth_headers(admin_token))).json()[0]
        annotation_id = annotation["id"]
        sensitive_note = "Synthetic subject detail must be deleted"
        sensitive_review = "Synthetic review detail must be deleted"

        updated = await client.put(
            f"/annotations/{annotation_id}",
            json={"coordinates": {"x": 12, "y": 12, "width": 22, "height": 22}, "notes": sensitive_note},
            headers=auth_headers(admin_token),
        )
        reviewed = await client.patch(
            f"/annotations/{annotation_id}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": sensitive_review},
            headers=auth_headers(reviewer_token),
        )
        release = await client.post(
            f"/projects/{annotation['project_id']}/releases",
            headers=auth_headers(admin_token),
        )
        deleted = await client.delete(f"/annotations/{annotation_id}", headers=auth_headers(admin_token))
        retained_release = await client.get(
            f"/dataset-releases/{release.json()['id']}",
            headers=auth_headers(admin_token),
        )
        no_history = await client.post(
            "/annotations",
            json={
                "project_id": annotation["project_id"],
                "scan_id": annotation["scan_id"],
                "label_id": annotation["label_id"],
                "label": annotation["label"],
                "annotation_type": "bounding_box",
                "coordinates": {"x": 50, "y": 50, "width": 10, "height": 10},
                "slice_index": 1,
                "created_by": "Admin User",
            },
            headers=auth_headers(admin_token),
        )
        no_history_deleted = await client.delete(
            f"/annotations/{no_history.json()['id']}",
            headers=auth_headers(admin_token),
        )

        assert updated.status_code == 200
        assert reviewed.status_code == 200
        assert release.status_code == 201
        assert deleted.status_code == 204
        assert retained_release.status_code == 200
        assert retained_release.json()["manifest"] == release.json()["manifest"]
        assert no_history.status_code == 201
        assert no_history_deleted.status_code == 204

    with app.state.test_session_factory() as db:
        assert db.get(Annotation, UUID(annotation_id)) is None
        assert list(db.scalars(select(AnnotationHistory).where(AnnotationHistory.annotation_id == UUID(annotation_id)))) == []
        tombstone = db.scalar(
            select(AnnotationHistoryTombstone).where(AnnotationHistoryTombstone.annotation_id == UUID(annotation_id))
        )
        assert tombstone is not None
        project = db.get(Project, UUID(annotation["project_id"]))
        assert project is not None
        assert tombstone.organization_id == project.organization_id
        assert tombstone.project_id == UUID(annotation["project_id"])
        assert tombstone.scan_id == UUID(annotation["scan_id"])
        assert tombstone.deleted_by_user_id is not None
        assert tombstone.deletion_source == "annotation_api"
        assert tombstone.history_entry_count == 2
        assert tombstone.action_counts == {"reviewed": 1, "updated": 1}
        assert set(tombstone.changed_fields) >= {"coordinates", "notes", "review_status", "reviewer"}
        assert len(tombstone.history_lineage_hash) == 64
        assert len(tombstone.integrity_hash) == 64
        assert verify_tombstone_integrity(tombstone)
        empty_tombstone = db.scalar(
            select(AnnotationHistoryTombstone).where(
                AnnotationHistoryTombstone.annotation_id == UUID(no_history.json()["id"])
            )
        )
        assert empty_tombstone is not None
        assert empty_tombstone.history_entry_count == 0
        assert empty_tombstone.action_counts == {}
        assert empty_tombstone.changed_fields == []
        assert empty_tombstone.first_history_at is None
        assert empty_tombstone.last_history_at is None
        assert verify_tombstone_integrity(empty_tombstone)

        minimized = json.dumps(
            {
                "organization_id": str(tombstone.organization_id),
                "project_id": str(tombstone.project_id),
                "scan_id": str(tombstone.scan_id),
                "annotation_id": str(tombstone.annotation_id),
                "action_counts": tombstone.action_counts,
                "changed_fields": tombstone.changed_fields,
                "history_lineage_hash": tombstone.history_lineage_hash,
                "integrity_hash": tombstone.integrity_hash,
            }
        )
        assert not hasattr(tombstone, "previous_values")
        assert not hasattr(tombstone, "new_values")
        for forbidden in (sensitive_note, sensitive_review, "Reviewer User"):
            assert forbidden not in minimized

        tombstone.action_counts = {"rewritten": 99}
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()
        tombstone = db.scalar(select(AnnotationHistoryTombstone).where(AnnotationHistoryTombstone.annotation_id == UUID(annotation_id)))
        assert tombstone is not None
        db.delete(tombstone)
        with pytest.raises(ValueError, match="append-only"):
            db.commit()


def test_migration_triggers_reject_tombstone_update_and_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "annotation-history-tombstone-triggers.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    organization_id = "1" * 32
    tombstone_id = "2" * 32
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'Tombstone Org')"), {"id": organization_id})
        connection.execute(
            text(
                "INSERT INTO annotation_history_tombstones "
                "(id, organization_id, project_id, scan_id, annotation_id, deletion_source, history_entry_count, "
                "action_counts, changed_fields, history_lineage_hash, integrity_hash, deleted_at) VALUES "
                "(:id, :organization_id, :project_id, :scan_id, :annotation_id, 'annotation_api', 1, "
                "'{\"updated\": 1}', '[\"notes\"]', :lineage_hash, :integrity_hash, CURRENT_TIMESTAMP)"
            ),
            {
                "id": tombstone_id,
                "organization_id": organization_id,
                "project_id": "3" * 32,
                "scan_id": "4" * 32,
                "annotation_id": "5" * 32,
                "lineage_hash": "a" * 64,
                "integrity_hash": "b" * 64,
            },
        )

    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("UPDATE annotation_history_tombstones SET history_entry_count = 2"))
    with pytest.raises(DatabaseError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM annotation_history_tombstones"))

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM annotation_history_tombstones")) == 1
