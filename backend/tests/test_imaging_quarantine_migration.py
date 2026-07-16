"""Data-safety checks for the imaging quarantine migration."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def test_legacy_uploads_are_quarantined_and_rollback_stays_closed(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "legacy-scans.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", "backend/migrations")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "20260716_0007")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'Research Org')"), {"id": "1" * 32})
        connection.execute(
            text("INSERT INTO projects (id, organization_id, name, modality) VALUES (:id, :organization_id, 'Study', 'CT')"),
            {"id": "2" * 32, "organization_id": "1" * 32},
        )
        for scan_id, source_format in (("3" * 32, "dicom"), ("4" * 32, "synthetic")):
            connection.execute(
                text(
                    "INSERT INTO scans "
                    "(id, project_id, name, file_path, modality, num_slices, source_format, ingestion_status) "
                    "VALUES (:id, :project_id, :name, :file_path, 'CT', 1, :source_format, 'ready')"
                ),
                {
                    "id": scan_id,
                    "project_id": "2" * 32,
                    "name": source_format,
                    "file_path": f"legacy/{source_format}",
                    "source_format": source_format,
                },
            )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        decisions = {
            row.source_format: (row.ingestion_status, row.deidentification_status)
            for row in connection.execute(
                text("SELECT source_format, ingestion_status, deidentification_status FROM scans")
            )
        }
    assert decisions["dicom"] == ("quarantined", "legacy_unverified")
    assert decisions["synthetic"] == ("ready", "synthetic")

    command.downgrade(config, "20260716_0007")
    with engine.connect() as connection:
        legacy_status = connection.scalar(text("SELECT ingestion_status FROM scans WHERE source_format = 'dicom'"))
    assert legacy_status == "failed"
