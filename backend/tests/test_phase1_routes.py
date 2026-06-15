"""Route-level smoke tests for the Phase 1 API contract."""

from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import Annotation, Label, Organization, Project, Scan, User
from backend.routers import annotations, auth, projects, scans
from backend.security import hash_password
from backend.services import imaging_service, scan_service
from backend.tests.fixtures.imaging import write_synthetic_dicom, write_synthetic_dicom_zip, write_synthetic_nifti


@pytest.fixture()
def anyio_backend() -> str:
    """Run async route tests on asyncio only."""

    return "asyncio"


def build_test_app(storage_root: Path) -> FastAPI:
    """Build an isolated app with an in-memory SQLite database."""

    scan_service.STORAGE_ROOT = storage_root
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_workspace(db)

    async def override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(scans.router)
    app.include_router(annotations.router)
    app.dependency_overrides[get_db] = override_get_db

    return app


def seed_workspace(db: Session) -> None:
    """Seed two organizations so route tests can prove workspace boundaries."""

    organization = Organization(name="Route Test Lab")
    other_organization = Organization(name="Outside Lab")
    db.add_all([organization, other_organization])
    db.flush()

    users = [
        User(organization_id=organization.id, email="admin@test.local", full_name="Admin User", password_hash=hash_password("password"), role="admin"),
        User(organization_id=organization.id, email="annotator@test.local", full_name="Annotator User", password_hash=hash_password("password"), role="annotator"),
        User(organization_id=organization.id, email="reviewer@test.local", full_name="Reviewer User", password_hash=hash_password("password"), role="reviewer"),
        User(organization_id=other_organization.id, email="outside-admin@test.local", full_name="Outside Admin", password_hash=hash_password("password"), role="admin"),
    ]
    project = Project(organization_id=organization.id, name="Brain MRI", description="Route test project", modality="MRI")
    other_project = Project(organization_id=other_organization.id, name="Outside CT", description="Cross-org test project", modality="CT")
    db.add_all([*users, project, other_project])
    db.flush()

    label = Label(project_id=project.id, name="tumour", color="#ef4444")
    scan = Scan(project_id=project.id, name="Brain MRI T1", file_path="test.nii.gz", modality="MRI", num_slices=10)
    pending_scan = Scan(project_id=project.id, name="Pending MRI", file_path="pending.nii.gz", modality="MRI", num_slices=3, ingestion_status="pending")
    failed_scan = Scan(
        project_id=project.id,
        name="Failed MRI",
        file_path="failed.nii.gz",
        modality="MRI",
        num_slices=3,
        ingestion_status="failed",
        ingestion_error="Parser could not read scan",
    )
    db.add_all([label, scan, pending_scan, failed_scan])
    db.flush()

    annotation = Annotation(
        project_id=project.id,
        scan_id=scan.id,
        label_id=label.id,
        label=label.name,
        annotation_type="bounding_box",
        coordinates={"x": 10, "y": 10, "width": 20, "height": 20},
        slice_index=3,
        created_by="Annotator User",
        review_status="pending",
    )
    db.add(annotation)
    db.commit()


async def login(client: httpx.AsyncClient, email: str) -> str:
    """Return a bearer token for a seeded user."""

    response = await client.post("/auth/login", json={"email": email, "password": "password"})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_scan_response_hides_storage_paths(scan: dict) -> None:
    assert "file_path" not in scan
    assert "storage_key" not in scan


@pytest.mark.anyio
async def test_login_and_me_route(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        token = await login(client, "admin@test.local")

        response = await client.get("/auth/me", headers=auth_headers(token))

        assert response.status_code == 200
        assert response.json()["email"] == "admin@test.local"


@pytest.mark.anyio
async def test_project_creation_is_admin_only(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        payload = {"name": "Thoracic CT", "description": "New test project", "modality": "CT"}

        forbidden = await client.post("/projects", json=payload, headers=auth_headers(annotator_token))
        created = await client.post("/projects", json=payload, headers=auth_headers(admin_token))

        assert forbidden.status_code == 403
        assert created.status_code == 201
        assert created.json()["name"] == "Thoracic CT"


@pytest.mark.anyio
async def test_label_and_scan_creation_are_admin_only(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]

        label_payload = {"name": "lesion", "color": "#f97316", "description": None}
        scan_payload = {"project_id": project_id, "name": "New Brain MRI", "modality": "MRI", "num_slices": 12, "file_name": "route-test.nii.gz"}

        forbidden_label = await client.post(f"/projects/{project_id}/labels", json=label_payload, headers=auth_headers(annotator_token))
        created_label = await client.post(f"/projects/{project_id}/labels", json=label_payload, headers=auth_headers(admin_token))
        forbidden_scan = await client.post("/scans", json=scan_payload, headers=auth_headers(annotator_token))
        created_scan = await client.post("/scans", json=scan_payload, headers=auth_headers(admin_token))

        assert forbidden_label.status_code == 403
        assert created_label.status_code == 201
        assert forbidden_scan.status_code == 403
        assert created_scan.status_code == 201
        assert created_scan.json()["project_id"] == project_id
        assert created_scan.json()["source_format"] == "synthetic"
        assert created_scan.json()["ingestion_status"] == "ready"
        assert created_scan.json()["depth"] == 12
        assert created_scan.json()["imaging_metadata"]["data_safety"] == "synthetic"
        assert created_scan.json()["imaging_metadata"]["deidentification_status"] == "synthetic_no_phi"


@pytest.mark.anyio
async def test_scan_upload_is_admin_only(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(tmp_path / "uploaded.dcm", width=6, height=4)
        data = {"project_id": project_id, "name": "Uploaded MRI", "modality": "MRI"}
        files = {"file": ("uploaded.dcm", fixture_path.read_bytes(), "application/dicom")}

        forbidden = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(annotator_token))
        created = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))

        assert forbidden.status_code == 403
        assert created.status_code == 201
        assert created.json()["name"] == "Uploaded MRI"
        assert created.json()["source_format"] == "dicom"
        assert created.json()["ingestion_status"] == "ready"
        assert created.json()["depth"] == 1
        assert_scan_response_hides_storage_paths(created.json())
        assert (tmp_path / project_id / created.json()["id"] / "original" / "uploaded.dcm").exists()


@pytest.mark.anyio
async def test_nifti_upload_parses_dimensions_and_generates_previews(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_nifti(tmp_path / "upload.nii.gz", width=7, height=5, depth=4, spacing=(0.8, 0.9, 1.6))
        data = {"project_id": project_id, "name": "Parsed NIfTI", "modality": "MRI"}
        files = {"file": ("upload.nii.gz", fixture_path.read_bytes(), "application/gzip")}

        created = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))

        body = created.json()
        assert created.status_code == 201
        assert body["source_format"] == "nifti"
        assert body["ingestion_status"] == "ready"
        assert body["num_slices"] == 4
        assert body["width"] == 7
        assert body["height"] == 5
        assert body["depth"] == 4
        assert body["spacing"] == [0.800000011920929, 0.8999999761581421, 1.600000023841858]
        assert_scan_response_hides_storage_paths(body)
        preview_root = tmp_path / project_id / body["id"] / "derived" / "preview"
        assert sorted(path.name for path in preview_root.glob("*.png")) == ["000000.png", "000001.png", "000002.png", "000003.png"]

        slice_response = await client.get(f"/scans/{body['id']}/slice/2", headers=auth_headers(admin_token))
        metadata_response = await client.get(f"/scans/{body['id']}/metadata", headers=auth_headers(admin_token))
        assert slice_response.status_code == 200
        assert metadata_response.status_code == 200
        assert metadata_response.json()["scan_name"] == "Parsed NIfTI"
        assert metadata_response.json()["source_format"] == "nifti"
        assert metadata_response.json()["depth"] == 4
        assert metadata_response.json()["metadata"]["parser_status"] == "parsed"
        with Image.open(preview_root / "000002.png") as preview_image:
            import base64
            from io import BytesIO

            buffer = BytesIO()
            preview_image.save(buffer, format="PNG")
            assert slice_response.json()["image_base64"] == base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.mark.anyio
async def test_dicom_upload_parses_metadata_and_generates_preview(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(tmp_path / "upload.dcm", width=6, height=4, spacing=(0.7, 0.9), slice_thickness=2.0)
        data = {"project_id": project_id, "name": "Parsed DICOM", "modality": "CT"}
        files = {"file": ("upload.dcm", fixture_path.read_bytes(), "application/dicom")}

        created = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))

        body = created.json()
        assert created.status_code == 201
        assert body["source_format"] == "dicom"
        assert body["ingestion_status"] == "ready"
        assert body["num_slices"] == 1
        assert body["width"] == 6
        assert body["height"] == 4
        assert body["depth"] == 1
        assert body["spacing"] == [0.7, 0.9, 2.0]
        assert body["window_center"] == 40.0
        assert body["window_width"] == 400.0
        assert_scan_response_hides_storage_paths(body)
        preview_root = tmp_path / project_id / body["id"] / "derived" / "preview"
        assert sorted(path.name for path in preview_root.glob("*.png")) == ["000000.png"]

        metadata_response = await client.get(f"/scans/{body['id']}/metadata", headers=auth_headers(admin_token))
        assert metadata_response.status_code == 200
        assert metadata_response.json()["metadata"]["parser_status"] == "parsed"


@pytest.mark.anyio
async def test_dicom_upload_reports_phi_warning_without_raw_values(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(
            tmp_path / "phi-upload.dcm",
            width=6,
            height=4,
            patient_name="Jane^Patient",
            patient_id="MRN-12345",
            accession_number="ACC-999",
        )
        data = {"project_id": project_id, "name": "DICOM With PHI", "modality": "CT"}
        files = {"file": ("phi-upload.dcm", fixture_path.read_bytes(), "application/dicom")}

        created = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))
        metadata_response = await client.get(f"/scans/{created.json()['id']}/metadata", headers=auth_headers(admin_token))

        metadata = metadata_response.json()["metadata"]
        assert created.status_code == 201
        assert metadata["phi_warnings"] == ["AccessionNumber", "PatientName", "PatientID"]
        assert metadata["deidentification_status"] == "phi_warning_detected"
        assert "Jane" not in str(metadata)
        assert "MRN-12345" not in str(metadata)
        assert "ACC-999" not in str(metadata)


@pytest.mark.anyio
async def test_dicom_zip_upload_parses_series_and_generates_previews(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom_zip(tmp_path / "series.zip", width=6, height=4, depth=3, spacing=(0.7, 0.9), slice_thickness=2.0)
        data = {"project_id": project_id, "name": "Parsed DICOM Series", "modality": "CT"}
        files = {"file": ("series.zip", fixture_path.read_bytes(), "application/zip")}

        created = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))

        body = created.json()
        assert created.status_code == 201
        assert body["source_format"] == "dicom_zip"
        assert body["ingestion_status"] == "ready"
        assert body["num_slices"] == 3
        assert body["width"] == 6
        assert body["height"] == 4
        assert body["depth"] == 3
        assert body["spacing"] == [0.7, 0.9, 2.0]
        assert_scan_response_hides_storage_paths(body)
        preview_root = tmp_path / project_id / body["id"] / "derived" / "preview"
        assert sorted(path.name for path in preview_root.glob("*.png")) == ["000000.png", "000001.png", "000002.png"]

        slice_response = await client.get(f"/scans/{body['id']}/slice/1", headers=auth_headers(admin_token))
        metadata_response = await client.get(f"/scans/{body['id']}/metadata", headers=auth_headers(admin_token))
        assert slice_response.status_code == 200
        assert metadata_response.status_code == 200
        assert metadata_response.json()["source_format"] == "dicom_zip"
        assert metadata_response.json()["metadata"]["preview_slice_count"] == 3


@pytest.mark.anyio
async def test_failed_upload_can_be_reprocessed_by_admin(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        data = {"project_id": project_id, "name": "Broken NIfTI", "modality": "MRI"}
        files = {"file": ("broken.nii.gz", b"not a gzip or nifti payload", "application/gzip")}

        created = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))
        body = created.json()
        original_path = tmp_path / project_id / body["id"] / "original" / "broken.nii.gz"
        valid_fixture = write_synthetic_nifti(tmp_path / "valid-retry.nii.gz", width=6, height=5, depth=2)
        original_path.write_bytes(valid_fixture.read_bytes())

        forbidden = await client.post(f"/scans/{body['id']}/reprocess", headers=auth_headers(annotator_token))
        reprocessed = await client.post(f"/scans/{body['id']}/reprocess", headers=auth_headers(admin_token))
        ready_slice = await client.get(f"/scans/{body['id']}/slice/1", headers=auth_headers(admin_token))

        assert created.status_code == 201
        assert body["ingestion_status"] == "failed"
        assert "could not be decompressed" in body["ingestion_error"]
        assert body["imaging_metadata"]["parser_status"] == "failed"
        assert forbidden.status_code == 403
        assert reprocessed.status_code == 200
        assert reprocessed.json()["ingestion_status"] == "ready"
        assert reprocessed.json()["source_format"] == "nifti"
        assert reprocessed.json()["num_slices"] == 2
        assert sorted(path.name for path in (tmp_path / project_id / body["id"] / "derived" / "preview").glob("*.png")) == ["000000.png", "000001.png"]
        assert ready_slice.status_code == 200


@pytest.mark.anyio
async def test_upload_rejects_oversized_file_before_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imaging_service, "MAX_UPLOAD_BYTES", 10)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        data = {"project_id": project_id, "name": "Huge Upload", "modality": "MRI"}
        files = {"file": ("huge.dcm", b"x" * 11, "application/dicom")}

        response = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))

        assert response.status_code == 413
        assert "upload size limit" in response.json()["detail"]


@pytest.mark.anyio
async def test_upload_rejects_unsupported_file_hint(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        data = {"project_id": project_id, "name": "Unsupported Upload", "modality": "MRI"}
        files = {"file": ("notes.txt", b"not imaging", "text/plain")}

        response = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))

        assert response.status_code == 415
        assert "Unsupported scan file type" in response.json()["detail"]


@pytest.mark.anyio
async def test_uploaded_scan_routes_are_organization_scoped(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        outside_admin_token = await login(client, "outside-admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        outside_project_id = (await client.get("/projects", headers=auth_headers(outside_admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(tmp_path / "scoped-upload.dcm", width=6, height=4)

        forbidden_upload = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Cross Org Upload", "modality": "CT"},
            files={"file": ("scoped-upload.dcm", fixture_path.read_bytes(), "application/dicom")},
            headers=auth_headers(outside_admin_token),
        )
        created = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Scoped Upload", "modality": "CT"},
            files={"file": ("scoped-upload.dcm", fixture_path.read_bytes(), "application/dicom")},
            headers=auth_headers(admin_token),
        )
        scan_id = created.json()["id"]

        outside_scan_list = await client.get("/scans", headers=auth_headers(outside_admin_token))
        outside_project_scans = await client.get(f"/projects/{outside_project_id}/scans", headers=auth_headers(outside_admin_token))
        forbidden_project_scans = await client.get(f"/projects/{project_id}/scans", headers=auth_headers(outside_admin_token))
        forbidden_scan = await client.get(f"/scans/{scan_id}", headers=auth_headers(outside_admin_token))
        forbidden_slice = await client.get(f"/scans/{scan_id}/slice/0", headers=auth_headers(outside_admin_token))
        forbidden_metadata = await client.get(f"/scans/{scan_id}/metadata", headers=auth_headers(outside_admin_token))
        forbidden_annotations = await client.get(f"/scans/{scan_id}/annotations", headers=auth_headers(outside_admin_token))
        owner_scan = await client.get(f"/scans/{scan_id}", headers=auth_headers(admin_token))
        owner_scan_list = await client.get("/scans", headers=auth_headers(admin_token))
        owner_slice = await client.get(f"/scans/{scan_id}/slice/0", headers=auth_headers(admin_token))

        assert forbidden_upload.status_code == 404
        assert created.status_code == 201
        assert scan_id not in {scan["id"] for scan in outside_scan_list.json()}
        assert outside_project_scans.status_code == 200
        assert outside_project_scans.json() == []
        assert forbidden_project_scans.status_code == 404
        assert forbidden_scan.status_code == 404
        assert forbidden_slice.status_code == 404
        assert forbidden_metadata.status_code == 404
        assert forbidden_annotations.status_code == 404
        assert_scan_response_hides_storage_paths(owner_scan.json())
        assert all("file_path" not in scan and "storage_key" not in scan for scan in owner_scan_list.json())
        assert owner_slice.status_code == 200


@pytest.mark.anyio
async def test_annotations_for_parsed_upload_stay_in_image_pixel_space(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        label_id = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(tmp_path / "pixel-space.dcm", width=6, height=4)
        upload = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Pixel Space DICOM", "modality": "CT"},
            files={"file": ("pixel-space.dcm", fixture_path.read_bytes(), "application/dicom")},
            headers=auth_headers(admin_token),
        )
        scan = upload.json()
        valid_payload = {
            "project_id": project_id,
            "scan_id": scan["id"],
            "label_id": label_id,
            "label": "tumour",
            "annotation_type": "bounding_box",
            "coordinates": {"x": 1, "y": 1, "width": 3, "height": 2},
            "slice_index": 0,
            "created_by": "Annotator User",
        }
        invalid_payload = {
            **valid_payload,
            "coordinates": {"x": 10, "y": 1, "width": 20, "height": 2},
        }

        created = await client.post("/annotations", json=valid_payload, headers=auth_headers(annotator_token))
        rejected = await client.post("/annotations", json=invalid_payload, headers=auth_headers(annotator_token))
        exported = await client.get(f"/scans/{scan['id']}/annotations", headers=auth_headers(admin_token))

        assert upload.status_code == 201
        assert scan["width"] == 6
        assert scan["height"] == 4
        assert created.status_code == 201
        assert created.json()["coordinates"] == {"x": 1, "y": 1, "width": 3, "height": 2}
        assert rejected.status_code == 400
        assert "image width" in rejected.json()["detail"]
        assert any(annotation["coordinates"] == valid_payload["coordinates"] for annotation in exported.json())


@pytest.mark.anyio
async def test_annotation_update_respects_image_pixel_bounds(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        label_id = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(tmp_path / "editable-pixel-space.dcm", width=8, height=6)
        upload = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Editable DICOM", "modality": "CT"},
            files={"file": ("editable-pixel-space.dcm", fixture_path.read_bytes(), "application/dicom")},
            headers=auth_headers(admin_token),
        )
        scan = upload.json()
        created = await client.post(
            "/annotations",
            json={
                "project_id": project_id,
                "scan_id": scan["id"],
                "label_id": label_id,
                "label": "tumour",
                "annotation_type": "bounding_box",
                "coordinates": {"x": 1, "y": 1, "width": 3, "height": 2},
                "slice_index": 0,
                "created_by": "Annotator User",
            },
            headers=auth_headers(annotator_token),
        )

        moved = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"coordinates": {"x": 3, "y": 2, "width": 4, "height": 3}},
            headers=auth_headers(annotator_token),
        )
        rejected = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"coordinates": {"x": 7, "y": 2, "width": 4, "height": 3}},
            headers=auth_headers(annotator_token),
        )

        assert upload.status_code == 201
        assert created.status_code == 201
        assert moved.status_code == 200
        assert moved.json()["coordinates"] == {"x": 3, "y": 2, "width": 4, "height": 3}
        assert rejected.status_code == 400
        assert "image width" in rejected.json()["detail"]


@pytest.mark.anyio
async def test_annotation_delete_permissions_are_role_scoped(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        outside_admin_token = await login(client, "outside-admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        scan = (await client.get(f"/projects/{project_id}/scans", headers=auth_headers(admin_token))).json()[0]
        annotations_response = await client.get(f"/scans/{scan['id']}/annotations", headers=auth_headers(admin_token))
        annotation_id = annotations_response.json()[0]["id"]

        annotator_delete = await client.delete(f"/annotations/{annotation_id}", headers=auth_headers(annotator_token))
        reviewer_delete = await client.delete(f"/annotations/{annotation_id}", headers=auth_headers(reviewer_token))
        outside_admin_delete = await client.delete(f"/annotations/{annotation_id}", headers=auth_headers(outside_admin_token))
        admin_delete = await client.delete(f"/annotations/{annotation_id}", headers=auth_headers(admin_token))
        remaining = await client.get(f"/scans/{scan['id']}/annotations", headers=auth_headers(admin_token))

        assert annotations_response.status_code == 200
        assert annotator_delete.status_code == 403
        assert reviewer_delete.status_code == 403
        assert outside_admin_delete.status_code == 404
        assert admin_delete.status_code == 204
        assert annotation_id not in {annotation["id"] for annotation in remaining.json()}


@pytest.mark.anyio
async def test_slice_endpoint_returns_useful_errors_for_unavailable_scans(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        scans_response = await client.get("/scans", headers=auth_headers(admin_token))
        scans_by_name = {scan["name"]: scan for scan in scans_response.json()}

        pending_response = await client.get(f"/scans/{scans_by_name['Pending MRI']['id']}/slice/0", headers=auth_headers(admin_token))
        failed_response = await client.get(f"/scans/{scans_by_name['Failed MRI']['id']}/slice/0", headers=auth_headers(admin_token))
        out_of_range_response = await client.get(f"/scans/{scans_by_name['Brain MRI T1']['id']}/slice/99", headers=auth_headers(admin_token))

        assert pending_response.status_code == 409
        assert pending_response.json()["detail"] == "Scan ingestion is not ready yet"
        assert failed_response.status_code == 422
        assert failed_response.json()["detail"] == "Parser could not read scan"
        assert out_of_range_response.status_code == 400
        assert out_of_range_response.json()["detail"] == "Slice index out of range"


@pytest.mark.anyio
async def test_annotation_create_review_and_export_routes(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        reviewer_token = await login(client, "reviewer@test.local")

        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        scan = (await client.get(f"/projects/{project_id}/scans", headers=auth_headers(admin_token))).json()[0]
        label = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]
        annotation_payload = {
            "project_id": project_id,
            "scan_id": scan["id"],
            "label_id": label["id"],
            "label": label["name"],
            "annotation_type": "bounding_box",
            "coordinates": {"x": 40, "y": 50, "width": 25, "height": 30},
            "slice_index": 2,
            "created_by": "Annotator User",
        }

        created = await client.post("/annotations", json=annotation_payload, headers=auth_headers(annotator_token))
        forbidden_review = await client.patch(
            f"/annotations/{created.json()['id']}/review",
            json={"reviewer": "Annotator User", "review_status": "approved", "notes": None},
            headers=auth_headers(annotator_token),
        )
        reviewed = await client.patch(
            f"/annotations/{created.json()['id']}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": "Looks good."},
            headers=auth_headers(reviewer_token),
        )
        exported = await client.get(f"/projects/{project_id}/export", headers=auth_headers(admin_token))

        assert created.status_code == 201
        assert forbidden_review.status_code == 403
        assert reviewed.status_code == 200
        assert reviewed.json()["review_status"] == "approved"
        assert exported.status_code == 200
        assert exported.json()["approved_count"] >= 1
