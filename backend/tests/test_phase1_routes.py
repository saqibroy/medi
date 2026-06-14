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
from backend.services import scan_service
from backend.tests.fixtures.imaging import write_synthetic_nifti


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
    """Seed one organization with all three roles and a ready annotation."""

    organization = Organization(name="Route Test Lab")
    db.add(organization)
    db.flush()

    users = [
        User(organization_id=organization.id, email="admin@test.local", full_name="Admin User", password_hash=hash_password("password"), role="admin"),
        User(organization_id=organization.id, email="annotator@test.local", full_name="Annotator User", password_hash=hash_password("password"), role="annotator"),
        User(organization_id=organization.id, email="reviewer@test.local", full_name="Reviewer User", password_hash=hash_password("password"), role="reviewer"),
    ]
    project = Project(organization_id=organization.id, name="Brain MRI", description="Route test project", modality="MRI")
    db.add_all([*users, project])
    db.flush()

    label = Label(project_id=project.id, name="tumour", color="#ef4444")
    scan = Scan(project_id=project.id, name="Brain MRI T1", file_path="test.nii.gz", modality="MRI", num_slices=10)
    db.add_all([label, scan])
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


@pytest.mark.anyio
async def test_scan_upload_is_admin_only(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_test_app(tmp_path)), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        project_id = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]["id"]
        data = {"project_id": project_id, "name": "Uploaded MRI", "modality": "MRI"}
        files = {"file": ("uploaded.bin", b"fake scan bytes", "application/octet-stream")}

        forbidden = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(annotator_token))
        created = await client.post("/scans/upload", data=data, files=files, headers=auth_headers(admin_token))

        assert forbidden.status_code == 403
        assert created.status_code == 201
        assert created.json()["name"] == "Uploaded MRI"
        assert created.json()["source_format"] == "unknown"
        assert created.json()["ingestion_status"] == "ready"
        assert created.json()["depth"] == 1
        assert Path(created.json()["file_path"]).exists()


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
        preview_root = Path(body["storage_key"]) / "derived" / "preview"
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
