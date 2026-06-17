"""Route-level smoke tests for the Phase 1 API contract."""

import base64
from collections.abc import Generator
from io import BytesIO
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
from backend.routers import annotations, auth, projects, scans, users
from backend.security import hash_password
from backend.services import imaging_service, scan_service, segmentation_mask_service
from backend.tests.fixtures.imaging import write_synthetic_dicom, write_synthetic_dicom_zip, write_synthetic_nifti


@pytest.fixture()
def anyio_backend() -> str:
    """Run async route tests on asyncio only."""

    return "asyncio"


def build_test_app(storage_root: Path) -> FastAPI:
    """Build an isolated app with an in-memory SQLite database."""

    scan_service.STORAGE_ROOT = storage_root
    segmentation_mask_service.MASK_STORAGE_ROOT = storage_root / "segmentation_masks"
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
    app.include_router(users.router)
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


def make_png_bytes(width: int, height: int, color: int = 255) -> bytes:
    buffer = BytesIO()
    Image.new("L", (width, height), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


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
async def test_annotation_update_validates_geometry_shape_by_type(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        label_id = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(tmp_path / "geometry-shape.dcm", width=8, height=6)
        upload = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Geometry Shape DICOM", "modality": "CT"},
            files={"file": ("geometry-shape.dcm", fixture_path.read_bytes(), "application/dicom")},
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

        rejected_box_shape = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"coordinates": {"x": 2, "y": 2, "width": True, "height": 2}},
            headers=auth_headers(annotator_token),
        )
        rejected_type_change = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"annotation_type": "segmentation"},
            headers=auth_headers(annotator_token),
        )
        changed_to_segmentation = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"annotation_type": "segmentation", "coordinates": {"mask_ref": True, "representation": "png_binary"}},
            headers=auth_headers(annotator_token),
        )
        rejected_segmentation_shape = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"coordinates": {"mask_ref": False, "representation": "png_binary"}},
            headers=auth_headers(annotator_token),
        )
        rejected_segmentation_representation = await client.post(
            "/annotations",
            json={
                "project_id": project_id,
                "scan_id": scan["id"],
                "label_id": label_id,
                "label": "tumour",
                "annotation_type": "segmentation",
                "coordinates": {"mask_ref": True, "representation": "rle"},
                "slice_index": 0,
                "created_by": "Annotator User",
            },
            headers=auth_headers(annotator_token),
        )

        assert upload.status_code == 201
        assert created.status_code == 201
        assert rejected_box_shape.status_code == 400
        assert "numeric x, y, width, and height" in rejected_box_shape.json()["detail"]
        assert rejected_type_change.status_code == 400
        assert "mask_ref true" in rejected_type_change.json()["detail"]
        assert changed_to_segmentation.status_code == 200
        assert changed_to_segmentation.json()["annotation_type"] == "segmentation"
        assert rejected_segmentation_shape.status_code == 400
        assert "mask_ref true" in rejected_segmentation_shape.json()["detail"]
        assert rejected_segmentation_representation.status_code == 400
        assert "png_binary" in rejected_segmentation_representation.json()["detail"]


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
async def test_annotation_edit_review_and_export_permissions_are_role_scoped(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        outside_admin_token = await login(client, "outside-admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        scan = (await client.get(f"/projects/{project_id}/scans", headers=auth_headers(admin_token))).json()[0]
        annotation_id = (await client.get(f"/scans/{scan['id']}/annotations", headers=auth_headers(admin_token))).json()[0]["id"]

        annotator_update = await client.put(f"/annotations/{annotation_id}", json={"notes": "Ready for QA."}, headers=auth_headers(annotator_token))
        admin_update = await client.put(f"/annotations/{annotation_id}", json={"notes": "Admin QA note."}, headers=auth_headers(admin_token))
        reviewer_update = await client.put(f"/annotations/{annotation_id}", json={"notes": "Reviewer edit attempt."}, headers=auth_headers(reviewer_token))
        outside_update = await client.put(f"/annotations/{annotation_id}", json={"notes": "Outside edit attempt."}, headers=auth_headers(outside_admin_token))
        annotator_review = await client.patch(
            f"/annotations/{annotation_id}/review",
            json={"reviewer": "Annotator User", "review_status": "approved", "notes": None},
            headers=auth_headers(annotator_token),
        )
        reviewer_review = await client.patch(
            f"/annotations/{annotation_id}/review",
            json={"reviewer": "Reviewer User", "review_status": "needs_changes", "notes": "Needs another pass."},
            headers=auth_headers(reviewer_token),
        )
        admin_review = await client.patch(
            f"/annotations/{annotation_id}/review",
            json={"reviewer": "Admin User", "review_status": "approved", "notes": "Approved by admin."},
            headers=auth_headers(admin_token),
        )
        outside_review = await client.patch(
            f"/annotations/{annotation_id}/review",
            json={"reviewer": "Outside Admin", "review_status": "approved", "notes": None},
            headers=auth_headers(outside_admin_token),
        )

        annotator_project_export = await client.get(f"/projects/{project_id}/export", headers=auth_headers(annotator_token))
        reviewer_project_coco = await client.get(f"/projects/{project_id}/export/coco", headers=auth_headers(reviewer_token))
        annotator_project_csv = await client.get(f"/projects/{project_id}/export/csv", headers=auth_headers(annotator_token))
        reviewer_project_yolo = await client.get(f"/projects/{project_id}/export/yolo", headers=auth_headers(reviewer_token))
        annotator_scan_export = await client.get(f"/scans/{scan['id']}/export", headers=auth_headers(annotator_token))
        reviewer_scan_csv = await client.get(f"/scans/{scan['id']}/export/csv", headers=auth_headers(reviewer_token))
        outside_project_export = await client.get(f"/projects/{project_id}/export", headers=auth_headers(outside_admin_token))
        outside_scan_export = await client.get(f"/scans/{scan['id']}/export", headers=auth_headers(outside_admin_token))

        assert annotator_update.status_code == 200
        assert admin_update.status_code == 200
        assert reviewer_update.status_code == 403
        assert outside_update.status_code == 404
        assert annotator_review.status_code == 403
        assert reviewer_review.status_code == 200
        assert admin_review.status_code == 200
        assert outside_review.status_code == 404
        assert annotator_project_export.status_code == 200
        assert reviewer_project_coco.status_code == 200
        assert annotator_project_csv.status_code == 200
        assert reviewer_project_yolo.status_code == 200
        assert annotator_scan_export.status_code == 200
        assert reviewer_scan_csv.status_code == 200
        assert outside_project_export.status_code == 404
        assert outside_scan_export.status_code == 404


@pytest.mark.anyio
async def test_polygon_annotations_validate_image_pixel_bounds(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        label_id = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]["id"]
        fixture_path = write_synthetic_dicom(tmp_path / "polygon-space.dcm", width=6, height=4)
        upload = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Polygon Space DICOM", "modality": "CT"},
            files={"file": ("polygon-space.dcm", fixture_path.read_bytes(), "application/dicom")},
            headers=auth_headers(admin_token),
        )
        scan = upload.json()
        valid_payload = {
            "project_id": project_id,
            "scan_id": scan["id"],
            "label_id": label_id,
            "label": "tumour",
            "annotation_type": "polygon",
            "coordinates": {"points": [{"x": 1, "y": 1}, {"x": 4, "y": 1}, {"x": 3, "y": 3}]},
            "slice_index": 0,
            "created_by": "Annotator User",
        }
        out_of_bounds_payload = {
            **valid_payload,
            "coordinates": {"points": [{"x": 1, "y": 1}, {"x": 7, "y": 1}, {"x": 3, "y": 3}]},
        }
        too_few_points_payload = {
            **valid_payload,
            "coordinates": {"points": [{"x": 1, "y": 1}, {"x": 4, "y": 1}]},
        }

        created = await client.post("/annotations", json=valid_payload, headers=auth_headers(annotator_token))
        moved = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"coordinates": {"points": [{"x": 2, "y": 1}, {"x": 5, "y": 1}, {"x": 3, "y": 3}]}},
            headers=auth_headers(annotator_token),
        )
        rejected_update = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"coordinates": {"points": [{"x": 2, "y": 1}, {"x": 5, "y": 5}, {"x": 3, "y": 3}]}},
            headers=auth_headers(annotator_token),
        )
        rejected_bounds = await client.post("/annotations", json=out_of_bounds_payload, headers=auth_headers(annotator_token))
        rejected_shape = await client.post("/annotations", json=too_few_points_payload, headers=auth_headers(annotator_token))
        exported = await client.get(f"/scans/{scan['id']}/annotations", headers=auth_headers(admin_token))

        assert upload.status_code == 201
        assert created.status_code == 201
        assert created.json()["coordinates"] == valid_payload["coordinates"]
        assert moved.status_code == 200
        assert moved.json()["coordinates"] == {"points": [{"x": 2, "y": 1}, {"x": 5, "y": 1}, {"x": 3, "y": 3}]}
        assert rejected_update.status_code == 400
        assert "image height" in rejected_update.json()["detail"]
        assert rejected_bounds.status_code == 400
        assert "image width" in rejected_bounds.json()["detail"]
        assert rejected_shape.status_code == 400
        assert "at least three points" in rejected_shape.json()["detail"]
        assert any(annotation["coordinates"] == moved.json()["coordinates"] for annotation in exported.json())


@pytest.mark.anyio
async def test_annotation_history_records_update_and_review_events(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        outside_admin_token = await login(client, "outside-admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        scan = (await client.get(f"/projects/{project_id}/scans", headers=auth_headers(admin_token))).json()[0]
        label = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]
        created = await client.post(
            "/annotations",
            json={
                "project_id": project_id,
                "scan_id": scan["id"],
                "label_id": label["id"],
                "label": label["name"],
                "annotation_type": "bounding_box",
                "coordinates": {"x": 20, "y": 20, "width": 30, "height": 30},
                "slice_index": 1,
                "created_by": "Annotator User",
            },
            headers=auth_headers(annotator_token),
        )

        updated = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"coordinates": {"x": 24, "y": 22, "width": 35, "height": 32}, "notes": "Adjusted geometry."},
            headers=auth_headers(annotator_token),
        )
        reviewed = await client.patch(
            f"/annotations/{created.json()['id']}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": "Ready for export."},
            headers=auth_headers(reviewer_token),
        )
        history = await client.get(f"/annotations/{created.json()['id']}/history", headers=auth_headers(admin_token))
        forbidden_history = await client.get(f"/annotations/{created.json()['id']}/history", headers=auth_headers(outside_admin_token))

        assert created.status_code == 201
        assert updated.status_code == 200
        assert updated.json()["updated_by_user_id"] is not None
        assert reviewed.status_code == 200
        assert reviewed.json()["reviewed_by_user_id"] is not None
        assert history.status_code == 200
        assert forbidden_history.status_code == 404
        assert [entry["action"] for entry in history.json()] == ["updated", "reviewed"]
        assert history.json()[0]["changed_by_user_id"] == updated.json()["updated_by_user_id"]
        assert history.json()[0]["changed_fields"] == ["coordinates", "notes"]
        assert history.json()[0]["previous_values"]["coordinates"] == {"x": 20, "y": 20, "width": 30, "height": 30}
        assert history.json()[0]["new_values"]["coordinates"] == {"x": 24, "y": 22, "width": 35, "height": 32}
        assert history.json()[1]["changed_by_user_id"] == reviewed.json()["reviewed_by_user_id"]
        assert "review_status" in history.json()[1]["changed_fields"]
        assert history.json()[1]["previous_values"]["review_status"] == "pending"
        assert history.json()[1]["new_values"]["review_status"] == "approved"


@pytest.mark.anyio
async def test_segmentation_mask_routes_store_validate_scope_and_audit(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        reviewer_token = await login(client, "reviewer@test.local")
        outside_admin_token = await login(client, "outside-admin@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        label = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]
        fixture_path = write_synthetic_dicom(tmp_path / "mask-source.dcm", width=6, height=4)
        upload = await client.post(
            "/scans/upload",
            data={"project_id": project_id, "name": "Segmentation Source", "modality": "CT"},
            files={"file": ("mask-source.dcm", fixture_path.read_bytes(), "application/dicom")},
            headers=auth_headers(admin_token),
        )
        scan = upload.json()
        created = await client.post(
            "/annotations",
            json={
                "project_id": project_id,
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

        mask_png = make_png_bytes(6, 4)
        bad_size_png = make_png_bytes(5, 4)
        stored = await client.post(
            f"/annotations/{created.json()['id']}/mask",
            data={"slice_index": "0"},
            files={"file": ("mask.png", mask_png, "image/png")},
            headers=auth_headers(annotator_token),
        )
        reviewed = await client.patch(
            f"/annotations/{created.json()['id']}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": "Mask ready for training."},
            headers=auth_headers(reviewer_token),
        )
        loaded = await client.get(f"/annotations/{created.json()['id']}/mask/0", headers=auth_headers(admin_token))
        outside_loaded = await client.get(f"/annotations/{created.json()['id']}/mask/0", headers=auth_headers(outside_admin_token))
        project_segmentation = await client.get(f"/projects/{project_id}/export/segmentation", headers=auth_headers(admin_token))
        scan_segmentation = await client.get(f"/scans/{scan['id']}/export/segmentation", headers=auth_headers(admin_token))
        project_csv = await client.get(f"/projects/{project_id}/export/csv", headers=auth_headers(admin_token))
        forbidden_segmentation = await client.get(f"/projects/{project_id}/export/segmentation", headers=auth_headers(outside_admin_token))
        rejected_dimensions = await client.post(
            f"/annotations/{created.json()['id']}/mask",
            data={"slice_index": "0"},
            files={"file": ("mask.png", bad_size_png, "image/png")},
            headers=auth_headers(annotator_token),
        )
        history_after_upload = await client.get(f"/annotations/{created.json()['id']}/history", headers=auth_headers(admin_token))
        mask_files_after_upload = list((tmp_path / "segmentation_masks").rglob("000000.png"))
        deleted = await client.delete(f"/annotations/{created.json()['id']}/mask/0", headers=auth_headers(annotator_token))
        missing_after_delete = await client.get(f"/annotations/{created.json()['id']}/mask/0", headers=auth_headers(admin_token))
        history_after_delete = await client.get(f"/annotations/{created.json()['id']}/history", headers=auth_headers(admin_token))

        assert upload.status_code == 201
        assert created.status_code == 201
        assert stored.status_code == 201
        assert reviewed.status_code == 200
        assert "storage_key" not in stored.json()
        assert stored.json()["annotation_id"] == created.json()["id"]
        assert stored.json()["width"] == 6
        assert stored.json()["height"] == 4
        assert stored.json()["encoding"] == "png_binary"
        assert stored.json()["byte_size"] == len(mask_png)
        assert loaded.status_code == 200
        assert loaded.json()["mask_base64"] == base64.b64encode(mask_png).decode("ascii")
        assert loaded.json()["checksum_sha256"] == stored.json()["checksum_sha256"]
        assert outside_loaded.status_code == 404
        assert project_segmentation.status_code == 200
        assert project_segmentation.json()["export_format"] == "segmentation_manifest"
        assert project_segmentation.json()["mask_count"] == 1
        assert project_segmentation.json()["available_mask_count"] == 1
        assert project_segmentation.json()["masks"][0]["annotation_id"] == created.json()["id"]
        assert project_segmentation.json()["masks"][0]["mask_available"] is True
        assert project_segmentation.json()["masks"][0]["mask_api_path"] == f"/annotations/{created.json()['id']}/mask/0"
        assert project_segmentation.json()["masks"][0]["mask_file_name"].endswith(f"{created.json()['id']}_slice_000000.png")
        assert project_segmentation.json()["masks"][0]["mask_checksum_sha256"] == stored.json()["checksum_sha256"]
        assert "storage_key" not in project_segmentation.json()["masks"][0]
        assert scan_segmentation.status_code == 200
        assert scan_segmentation.json()["masks"] == project_segmentation.json()["masks"]
        assert project_csv.status_code == 200
        assert "mask_available,mask_file_name,mask_width,mask_height,mask_encoding,mask_byte_size,mask_checksum_sha256,mask_api_path" in project_csv.json()["content"]
        assert f"/annotations/{created.json()['id']}/mask/0" in project_csv.json()["content"]
        assert stored.json()["checksum_sha256"] in project_csv.json()["content"]
        assert forbidden_segmentation.status_code == 404
        assert rejected_dimensions.status_code == 400
        assert "dimensions" in rejected_dimensions.json()["detail"]
        assert history_after_upload.status_code == 200
        assert [entry["action"] for entry in history_after_upload.json()] == ["mask_uploaded", "reviewed"]
        assert history_after_upload.json()[0]["changed_fields"] == ["segmentation_mask"]
        assert mask_files_after_upload
        assert deleted.status_code == 204
        assert missing_after_delete.status_code == 404
        assert history_after_delete.status_code == 200
        assert [entry["action"] for entry in history_after_delete.json()] == ["mask_uploaded", "reviewed", "mask_deleted"]
        assert not list((tmp_path / "segmentation_masks").rglob("000000.png"))


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
        outside_admin_token = await login(client, "outside-admin@test.local")

        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        workspace_users = await client.get("/users", headers=auth_headers(admin_token))
        outside_users = await client.get("/users", headers=auth_headers(outside_admin_token))
        scan = (await client.get(f"/projects/{project_id}/scans", headers=auth_headers(admin_token))).json()[0]
        label = (await client.get(f"/projects/{project_id}/labels", headers=auth_headers(admin_token))).json()[0]
        user_by_email = {user["email"]: user for user in workspace_users.json()}
        outside_user_id = outside_users.json()[0]["id"]
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
        polygon_payload = {
            **annotation_payload,
            "annotation_type": "polygon",
            "coordinates": {"points": [{"x": 10, "y": 10}, {"x": 20, "y": 10}, {"x": 15, "y": 20}]},
        }
        approved_polygon_payload = {
            **annotation_payload,
            "annotation_type": "polygon",
            "coordinates": {"points": [{"x": 100, "y": 100}, {"x": 110, "y": 100}, {"x": 110, "y": 110}, {"x": 100, "y": 110}]},
        }

        created = await client.post("/annotations", json=annotation_payload, headers=auth_headers(annotator_token))
        reassigned = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"assigned_to_user_id": user_by_email["reviewer@test.local"]["id"]},
            headers=auth_headers(annotator_token),
        )
        rejected_assignment = await client.put(
            f"/annotations/{created.json()['id']}",
            json={"assigned_to_user_id": outside_user_id},
            headers=auth_headers(annotator_token),
        )
        polygon = await client.post("/annotations", json=polygon_payload, headers=auth_headers(annotator_token))
        approved_polygon = await client.post("/annotations", json=approved_polygon_payload, headers=auth_headers(annotator_token))
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
        reviewed_polygon = await client.patch(
            f"/annotations/{polygon.json()['id']}/review",
            json={"reviewer": "Reviewer User", "review_status": "needs_changes", "notes": "Polygon needs another contour pass."},
            headers=auth_headers(reviewer_token),
        )
        reviewed_approved_polygon = await client.patch(
            f"/annotations/{approved_polygon.json()['id']}/review",
            json={"reviewer": "Reviewer User", "review_status": "approved", "notes": "Polygon ready for COCO export."},
            headers=auth_headers(reviewer_token),
        )
        exported = await client.get(f"/projects/{project_id}/export", headers=auth_headers(admin_token))
        project_stats = await client.get(f"/projects/{project_id}/stats", headers=auth_headers(admin_token))
        scan_stats = await client.get(f"/scans/{scan['id']}/stats", headers=auth_headers(admin_token))
        needs_changes_search = await client.get("/annotations/search?review_status=needs_changes", headers=auth_headers(admin_token))
        project_coco = await client.get(f"/projects/{project_id}/export/coco", headers=auth_headers(admin_token))
        project_csv = await client.get(f"/projects/{project_id}/export/csv", headers=auth_headers(admin_token))
        project_yolo = await client.get(f"/projects/{project_id}/export/yolo", headers=auth_headers(admin_token))
        scan_coco = await client.get(f"/scans/{scan['id']}/export/coco", headers=auth_headers(admin_token))
        scan_csv = await client.get(f"/scans/{scan['id']}/export/csv", headers=auth_headers(admin_token))
        scan_yolo = await client.get(f"/scans/{scan['id']}/export/yolo", headers=auth_headers(admin_token))
        forbidden_coco = await client.get(f"/projects/{project_id}/export/coco", headers=auth_headers(outside_admin_token))
        forbidden_csv = await client.get(f"/projects/{project_id}/export/csv", headers=auth_headers(outside_admin_token))
        forbidden_stats = await client.get(f"/projects/{project_id}/stats", headers=auth_headers(outside_admin_token))
        forbidden_yolo = await client.get(f"/scans/{scan['id']}/export/yolo", headers=auth_headers(outside_admin_token))

        assert created.status_code == 201
        assert workspace_users.status_code == 200
        assert {user["email"] for user in workspace_users.json()} == {"admin@test.local", "annotator@test.local", "reviewer@test.local"}
        assert created.json()["assigned_to_user_id"] == user_by_email["annotator@test.local"]["id"]
        assert reassigned.status_code == 200
        assert reassigned.json()["assigned_to_user_id"] == user_by_email["reviewer@test.local"]["id"]
        assert rejected_assignment.status_code == 400
        assert polygon.status_code == 201
        assert approved_polygon.status_code == 201
        assert forbidden_review.status_code == 403
        assert reviewed.status_code == 200
        assert reviewed_polygon.status_code == 200
        assert reviewed_approved_polygon.status_code == 200
        assert reviewed.json()["review_status"] == "approved"
        assert reviewed_polygon.json()["review_status"] == "needs_changes"
        assert reviewed_approved_polygon.json()["review_status"] == "approved"
        assert exported.status_code == 200
        assert exported.json()["approved_count"] >= 1
        assert project_stats.status_code == 200
        assert project_stats.json()["total_annotations"] == 4
        assert project_stats.json()["approved_count"] == 2
        assert project_stats.json()["pending_count"] == 1
        assert project_stats.json()["needs_changes_count"] == 1
        assert project_stats.json()["review_completion_rate"] == 0.75
        assert project_stats.json()["scan_count"] == 3
        assert project_stats.json()["label_count"] == 1
        assert scan_stats.status_code == 200
        assert scan_stats.json()["annotations_by_status"] == {"pending": 1, "approved": 2, "rejected": 0, "needs_changes": 1}
        assert scan_stats.json()["radiologists_involved"] == ["Annotator User"]
        assert all(annotation["review_status"] == "approved" for scan_export in exported.json()["scans"] for annotation in scan_export["annotations"])
        assert needs_changes_search.status_code == 200
        assert polygon.json()["id"] in {annotation["id"] for annotation in needs_changes_search.json()}
        assert project_coco.status_code == 200
        assert project_coco.json()["export_format"] == "coco"
        assert len(project_coco.json()["annotations"]) == 2
        coco_by_source = {annotation["source_annotation_id"]: annotation for annotation in project_coco.json()["annotations"]}
        assert coco_by_source[created.json()["id"]]["annotation_type"] == "bounding_box"
        assert coco_by_source[created.json()["id"]]["bbox"] == [40.0, 50.0, 25.0, 30.0]
        assert coco_by_source[created.json()["id"]]["area"] == 750.0
        assert coco_by_source[created.json()["id"]]["segmentation"] is None
        assert coco_by_source[approved_polygon.json()["id"]]["annotation_type"] == "polygon"
        assert coco_by_source[approved_polygon.json()["id"]]["bbox"] == [100.0, 100.0, 10.0, 10.0]
        assert coco_by_source[approved_polygon.json()["id"]]["area"] == 100.0
        assert coco_by_source[approved_polygon.json()["id"]]["segmentation"] == [[100.0, 100.0, 110.0, 100.0, 110.0, 110.0, 100.0, 110.0]]
        assert project_coco.json()["images"][0]["slice_index"] == 2
        assert project_coco.json()["categories"] == [{"id": 1, "name": label["name"]}]
        assert project_csv.status_code == 200
        assert project_csv.json()["export_format"] == "csv"
        assert project_csv.json()["row_count"] >= 3
        assert "annotation_id,project_id,scan_id,scan_name,slice_index,label" in project_csv.json()["content"]
        assert created.json()["id"] in project_csv.json()["content"]
        assert polygon.json()["id"] in project_csv.json()["content"]
        assert "needs_changes" in project_csv.json()["content"]
        assert '"{""points"": [{""x"": 10, ""y"": 10}, {""x"": 20, ""y"": 10}, {""x"": 15, ""y"": 20}]}"' in project_csv.json()["content"]
        assert project_yolo.status_code == 200
        assert project_yolo.json()["export_format"] == "yolo"
        assert project_yolo.json()["classes"] == [label["name"]]
        assert len(project_yolo.json()["files"]) == 1
        assert project_yolo.json()["files"][0]["content"] == "0 0.102539 0.126953 0.048828 0.058594"
        assert scan_coco.status_code == 200
        assert scan_coco.json()["annotations"] == project_coco.json()["annotations"]
        assert scan_csv.status_code == 200
        assert scan_csv.json()["content"] == project_csv.json()["content"]
        assert scan_yolo.status_code == 200
        assert scan_yolo.json()["files"] == project_yolo.json()["files"]
        assert forbidden_coco.status_code == 404
        assert forbidden_csv.status_code == 404
        assert forbidden_stats.status_code == 404
        assert forbidden_yolo.status_code == 404
