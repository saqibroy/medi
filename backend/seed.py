"""Seed script that creates sample scans and annotations for local learning.

Run with `python3 -m backend.seed` after PostgreSQL is available. The script
prints each object it creates so developers can see the shape of records that
the frontend and ML consumers will receive.
"""

from collections import Counter

from .database import Base, SessionLocal, engine, ensure_learning_schema_upgrades
from .models import Annotation, Scan


def seed() -> None:
    """Create three scans and ten realistic annotations with review metadata.

    The sample data intentionally mixes labels, geometry types, confidence, and
    review states so developers can exercise QA, search, statistics, and ML
    export endpoints without hand-entering records first.
    """

    Base.metadata.create_all(bind=engine)
    ensure_learning_schema_upgrades()
    db = SessionLocal()
    try:
        scans = [
            Scan(name="Brain MRI T1", file_path="backend/data/sample_scan/brain_t1.nii.gz", modality="MRI", num_slices=80),
            Scan(name="Chest CT Contrast", file_path="backend/data/sample_scan/chest_ct.nii.gz", modality="CT", num_slices=120),
            Scan(name="Knee MRI Sagittal", file_path="backend/data/sample_scan/knee_mri.nii.gz", modality="MRI", num_slices=64),
        ]
        db.add_all(scans)
        db.flush()

        annotations = [
            Annotation(scan_id=scans[0].id, label="tumour", annotation_type="bounding_box", coordinates={"x": 120, "y": 140, "width": 86, "height": 72}, slice_index=32, created_by="Dr. Rao", confidence_score=0.93, review_status="approved", reviewer="Dr. Patel"),
            Annotation(scan_id=scans[0].id, label="lesion", annotation_type="polygon", coordinates={"points": [[180, 210], [230, 198], [260, 245], [205, 270]]}, slice_index=34, created_by="Dr. Rao", confidence_score=0.81, review_status="pending"),
            Annotation(scan_id=scans[0].id, label="normal", annotation_type="polygon", coordinates={"points": [[40, 60], [90, 72], [80, 130], [35, 118]]}, slice_index=10, created_by="Dr. Kim", confidence_score=0.88, review_status="approved", reviewer="Dr. Patel", notes="Clear normal reference tissue for negative-class examples."),
            Annotation(scan_id=scans[1].id, label="lesion", annotation_type="bounding_box", coordinates={"x": 260, "y": 210, "width": 64, "height": 90}, slice_index=55, created_by="Dr. Kim", confidence_score=0.77, review_status="pending"),
            Annotation(scan_id=scans[1].id, label="nodule", annotation_type="bounding_box", coordinates={"x": 200, "y": 180, "width": 60, "height": 60}, slice_index=57, created_by="Dr. Rao", confidence_score=0.91, review_status="approved", reviewer="Dr. Patel"),
            Annotation(scan_id=scans[1].id, label="healthy_tissue", annotation_type="polygon", coordinates={"points": [[300, 120], [360, 130], [350, 190], [295, 175]]}, slice_index=20, created_by="Dr. Kim", confidence_score=0.96, review_status="approved", reviewer="Dr. Patel"),
            Annotation(scan_id=scans[1].id, label="nodule", annotation_type="bounding_box", coordinates={"x": 132, "y": 260, "width": 42, "height": 38}, slice_index=61, created_by="Dr. Rao", confidence_score=0.64, review_status="rejected", reviewer="Dr. Patel", notes="Rejected during QA because the finding was likely a vessel crossing."),
            Annotation(scan_id=scans[2].id, label="tear", annotation_type="bounding_box", coordinates={"x": 170, "y": 250, "width": 110, "height": 48}, slice_index=22, created_by="Dr. Kim", confidence_score=0.86, review_status="approved", reviewer="Dr. Patel"),
            Annotation(scan_id=scans[2].id, label="healthy_tissue", annotation_type="polygon", coordinates={"points": [[90, 300], [145, 285], [170, 330], [120, 355]]}, slice_index=12, created_by="Dr. Rao", confidence_score=0.98, review_status="pending"),
            Annotation(scan_id=scans[2].id, label="tear", annotation_type="bounding_box", coordinates={"x": 240, "y": 210, "width": 70, "height": 34}, slice_index=27, created_by="Dr. Kim", confidence_score=0.72, review_status="pending"),
        ]
        db.add_all(annotations)
        db.commit()

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
