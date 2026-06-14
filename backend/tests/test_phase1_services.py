"""Service smoke tests for the Phase 1 product foundation."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.database import Base
from backend.models import Annotation, Label, Organization, Project, Scan, User
from backend.security import hash_password, require_role
from backend.services.auth_service import authenticate_user
from backend.services.project_service import export_project_annotations, list_project_labels, list_projects
from fastapi import HTTPException


def build_session() -> Session:
    """Create an isolated in-memory SQLite database for service tests."""

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def seed_product_workspace(db: Session) -> User:
    """Seed the smallest useful product workspace."""

    organization = Organization(name="Test Lab")
    db.add(organization)
    db.flush()
    user = User(
        organization_id=organization.id,
        email="annotator@test.local",
        full_name="Test Annotator",
        password_hash=hash_password("password"),
        role="annotator",
    )
    project = Project(organization_id=organization.id, name="Brain MRI", description="Test project", modality="MRI")
    db.add_all([user, project])
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
        created_by=user.full_name,
        review_status="approved",
    )
    db.add(annotation)
    db.commit()
    return user


def test_authenticate_user_and_list_projects() -> None:
    db = build_session()
    try:
        seed_product_workspace(db)

        token, user = authenticate_user(db, "annotator@test.local", "password")
        projects = list_projects(db, user)

        assert len(token) > 20
        assert user.email == "annotator@test.local"
        assert [project.name for project in projects] == ["Brain MRI"]
    finally:
        db.close()


def test_project_labels_and_export_are_project_scoped() -> None:
    db = build_session()
    try:
        user = seed_product_workspace(db)
        project = list_projects(db, user)[0]

        labels = list_project_labels(db, project.id, user)
        export = export_project_annotations(db, project.id, user)

        assert [label.name for label in labels] == ["tumour"]
        assert export["project_name"] == "Brain MRI"
        assert export["total_annotations"] == 1
        assert export["approved_count"] == 1
    finally:
        db.close()


def test_require_role_allows_expected_roles() -> None:
    db = build_session()
    try:
        user = seed_product_workspace(db)
        user.role = "reviewer"

        assert require_role(user, {"admin", "reviewer"}) is user
    finally:
        db.close()


def test_require_role_rejects_disallowed_roles() -> None:
    db = build_session()
    try:
        user = seed_product_workspace(db)
        user.role = "annotator"

        try:
            require_role(user, {"admin", "reviewer"})
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("Expected HTTPException for disallowed role")
    finally:
        db.close()
