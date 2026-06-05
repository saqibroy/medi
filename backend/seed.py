"""Seed script that creates sample scans and annotations for local learning.

Run with `python3 -m backend.seed` after PostgreSQL is available. The script
prints each object it creates so developers can see the shape of records that
the frontend and ML consumers will receive.
"""

from .database import Base, SessionLocal, engine
from .models import Annotation, Scan


def seed() -> None:
    """Create three scans and five annotations with varied labels and geometry."""

    Base.metadata.create_all(bind=engine)
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
            Annotation(scan_id=scans[0].id, label="tumour", annotation_type="bounding_box", coordinates={"x": 120, "y": 140, "width": 86, "height": 72}, slice_index=32, created_by="Dr. Rao"),
            Annotation(scan_id=scans[0].id, label="normal", annotation_type="polygon", coordinates={"points": [[40, 60], [90, 72], [80, 130]]}, slice_index=10, created_by="Dr. Kim"),
            Annotation(scan_id=scans[1].id, label="lesion", annotation_type="bounding_box", coordinates={"x": 260, "y": 210, "width": 64, "height": 90}, slice_index=55, created_by="Dr. Singh"),
            Annotation(scan_id=scans[1].id, label="nodule", annotation_type="segmentation", coordinates={"mask_id": "local-mask-001", "bounds": [200, 180, 260, 240]}, slice_index=57, created_by="Dr. Avery"),
            Annotation(scan_id=scans[2].id, label="tear", annotation_type="bounding_box", coordinates={"x": 170, "y": 250, "width": 110, "height": 48}, slice_index=22, created_by="Dr. Chen"),
        ]
        db.add_all(annotations)
        db.commit()

        print("Created scans:")
        for scan in scans:
            print(f"- {scan.id} | {scan.name} | {scan.modality} | {scan.num_slices} slices")
        print("Created annotations:")
        for annotation in annotations:
            print(f"- {annotation.id} | scan={annotation.scan_id} | {annotation.label} | {annotation.coordinates}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
