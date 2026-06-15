"""Seed script that creates synthetic sample scans and annotations.

Run `alembic upgrade head` first, then run this with `python3 -m backend.seed`
after PostgreSQL is available. The script prints each object it creates so
developers can see the shape of records that the frontend and ML consumers will
receive. The seeded scan records are synthetic placeholders, not patient data.
"""

from collections import Counter

from sqlalchemy import select

from .database import SessionLocal
from .models import Annotation, Label, Organization, Project, Scan, User
from .security import hash_password
from .services.imaging_service import build_initial_scan_profile


def seed() -> None:
    """Create three synthetic scans and realistic annotations with review metadata.

    The sample data intentionally mixes labels, geometry types, confidence, and
    review states so developers can exercise QA, search, statistics, and ML
    export endpoints without hand-entering records first. No seeded scan points
    to real patient imaging.
    """

    db = SessionLocal()
    try:
        existing_demo_user = db.scalar(select(User).where(User.email == "admin@medi.local"))
        if existing_demo_user is not None:
            print("Demo data already exists.")
            print("Demo login:")
            print("- admin@medi.local / password")
            print("- annotator@medi.local / password")
            print("- reviewer@medi.local / password")
            return

        organization = Organization(name="Medi Research Lab")
        db.add(organization)
        db.flush()

        users = [
            User(organization_id=organization.id, email="admin@medi.local", full_name="Amina Shah", password_hash=hash_password("password"), role="admin"),
            User(organization_id=organization.id, email="annotator@medi.local", full_name="Dr. Rao", password_hash=hash_password("password"), role="annotator"),
            User(organization_id=organization.id, email="reviewer@medi.local", full_name="Dr. Patel", password_hash=hash_password("password"), role="reviewer"),
        ]
        db.add_all(users)

        neuro_project = Project(
            organization_id=organization.id,
            name="Neuro Oncology Research",
            description="Synthetic MRI labeling project for tumour and lesion model development.",
            modality="MRI",
        )
        thoracic_project = Project(
            organization_id=organization.id,
            name="Thoracic CT Nodule Review",
            description="Synthetic CT project used to validate nodule annotation and QA workflows.",
            modality="CT",
        )
        db.add_all([neuro_project, thoracic_project])
        db.flush()

        labels = [
            Label(project_id=neuro_project.id, name="tumour", color="#ef4444", description="Primary tumour region."),
            Label(project_id=neuro_project.id, name="lesion", color="#f59e0b", description="Suspicious lesion requiring review."),
            Label(project_id=neuro_project.id, name="normal", color="#22c55e", description="Normal reference tissue."),
            Label(project_id=thoracic_project.id, name="nodule", color="#ec4899", description="Pulmonary nodule candidate."),
            Label(project_id=thoracic_project.id, name="lesion", color="#f97316", description="Thoracic lesion candidate."),
            Label(project_id=thoracic_project.id, name="healthy_tissue", color="#10b981", description="Healthy tissue reference region."),
        ]
        db.add_all(labels)
        db.flush()
        label_by_project_and_name = {(label.project_id, label.name): label for label in labels}

        brain_scan_path = "backend/data/sample_scan/brain_t1.nii.gz"
        chest_scan_path = "backend/data/sample_scan/chest_ct.nii.gz"
        knee_scan_path = "backend/data/sample_scan/knee_mri.nii.gz"
        scans = [
            Scan(
                project_id=neuro_project.id,
                name="Brain MRI T1",
                file_path=brain_scan_path,
                modality="MRI",
                num_slices=80,
                **build_initial_scan_profile("synthetic", "MRI", 80, brain_scan_path),
            ),
            Scan(
                project_id=thoracic_project.id,
                name="Chest CT Contrast",
                file_path=chest_scan_path,
                modality="CT",
                num_slices=120,
                **build_initial_scan_profile("synthetic", "CT", 120, chest_scan_path),
            ),
            Scan(
                project_id=neuro_project.id,
                name="Knee MRI Sagittal",
                file_path=knee_scan_path,
                modality="MRI",
                num_slices=64,
                **build_initial_scan_profile("synthetic", "MRI", 64, knee_scan_path),
            ),
        ]
        db.add_all(scans)
        db.flush()

        annotations = [
            Annotation(project_id=scans[0].project_id, scan_id=scans[0].id, label_id=label_by_project_and_name[(neuro_project.id, "tumour")].id, label="tumour", annotation_type="bounding_box", coordinates={"x": 120, "y": 140, "width": 86, "height": 72}, slice_index=32, created_by="Dr. Rao", confidence_score=0.93, review_status="approved", reviewer="Dr. Patel", reviewed_by_user_id=users[2].id),
            Annotation(project_id=scans[0].project_id, scan_id=scans[0].id, label_id=label_by_project_and_name[(neuro_project.id, "lesion")].id, label="lesion", annotation_type="polygon", coordinates={"points": [[180, 210], [230, 198], [260, 245], [205, 270]]}, slice_index=34, created_by="Dr. Rao", confidence_score=0.81, review_status="pending"),
            Annotation(project_id=scans[0].project_id, scan_id=scans[0].id, label_id=label_by_project_and_name[(neuro_project.id, "normal")].id, label="normal", annotation_type="polygon", coordinates={"points": [[40, 60], [90, 72], [80, 130], [35, 118]]}, slice_index=10, created_by="Dr. Rao", confidence_score=0.88, review_status="approved", reviewer="Dr. Patel", reviewed_by_user_id=users[2].id, notes="Clear normal reference tissue for negative-class examples."),
            Annotation(project_id=scans[1].project_id, scan_id=scans[1].id, label_id=label_by_project_and_name[(thoracic_project.id, "lesion")].id, label="lesion", annotation_type="bounding_box", coordinates={"x": 260, "y": 210, "width": 64, "height": 90}, slice_index=55, created_by="Dr. Rao", confidence_score=0.77, review_status="pending"),
            Annotation(project_id=scans[1].project_id, scan_id=scans[1].id, label_id=label_by_project_and_name[(thoracic_project.id, "nodule")].id, label="nodule", annotation_type="bounding_box", coordinates={"x": 200, "y": 180, "width": 60, "height": 60}, slice_index=57, created_by="Dr. Rao", confidence_score=0.91, review_status="approved", reviewer="Dr. Patel", reviewed_by_user_id=users[2].id),
            Annotation(project_id=scans[1].project_id, scan_id=scans[1].id, label_id=label_by_project_and_name[(thoracic_project.id, "healthy_tissue")].id, label="healthy_tissue", annotation_type="polygon", coordinates={"points": [[300, 120], [360, 130], [350, 190], [295, 175]]}, slice_index=20, created_by="Dr. Rao", confidence_score=0.96, review_status="approved", reviewer="Dr. Patel", reviewed_by_user_id=users[2].id),
            Annotation(project_id=scans[1].project_id, scan_id=scans[1].id, label_id=label_by_project_and_name[(thoracic_project.id, "nodule")].id, label="nodule", annotation_type="bounding_box", coordinates={"x": 132, "y": 260, "width": 42, "height": 38}, slice_index=61, created_by="Dr. Rao", confidence_score=0.64, review_status="rejected", reviewer="Dr. Patel", reviewed_by_user_id=users[2].id, notes="Rejected during QA because the finding was likely a vessel crossing."),
        ]
        db.add_all(annotations)
        db.commit()

        print("Demo login:")
        print("- admin@medi.local / password")
        print("- annotator@medi.local / password")
        print("- reviewer@medi.local / password")
        print("Created projects:")
        for project in [neuro_project, thoracic_project]:
            print(f"- {project.id} | {project.name} | {project.modality}")
        print("Created scans:")
        for scan in scans:
            print(f"- {scan.id} | {scan.name} | {scan.modality} | {scan.num_slices} slices")
        print("Created annotations:")
        for annotation in annotations:
            print(f"- {annotation.id} | scan={annotation.scan_id} | {annotation.label} | {annotation.review_status} | confidence={annotation.confidence_score}")

        status_counts = Counter(annotation.review_status for annotation in annotations)
        label_counts = Counter(annotation.label for annotation in annotations)
        print("Annotation review status distribution:")
        for status_name in ("pending", "approved", "rejected"):
            print(f"- {status_name}: {status_counts.get(status_name, 0)}")
        print("Annotation label distribution:")
        for label, count in sorted(label_counts.items()):
            print(f"- {label}: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
