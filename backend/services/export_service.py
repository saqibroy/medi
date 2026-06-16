"""ML export format builders for reviewed annotation datasets."""

import csv
import json
from io import StringIO
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, Label, Scan


CSV_COLUMNS = [
    "annotation_id",
    "project_id",
    "scan_id",
    "scan_name",
    "slice_index",
    "label",
    "annotation_type",
    "review_status",
    "created_by",
    "reviewer",
    "confidence_score",
    "notes",
    "coordinates_json",
    "image_width",
    "image_height",
    "created_at",
    "updated_at",
    "reviewed_at",
]


def _image_size(scan: Scan) -> tuple[int, int]:
    return scan.width or 512, scan.height or 512


def _slice_file_name(scan: Scan, slice_index: int) -> str:
    safe_name = "".join(character if character.isalnum() or character in ("-", "_") else "_" for character in scan.name).strip("_")
    return f"{safe_name or 'scan'}_{scan.id}_slice_{slice_index:06d}.png"


def _bounding_box(annotation: Annotation) -> tuple[float, float, float, float]:
    coordinates = annotation.coordinates
    return (
        float(coordinates["x"]),
        float(coordinates["y"]),
        float(coordinates["width"]),
        float(coordinates["height"]),
    )


def _approved_bounding_boxes(db: Session, scan_ids: Sequence[UUID]) -> list[Annotation]:
    if not scan_ids:
        return []
    statement = (
        select(Annotation)
        .where(
            Annotation.scan_id.in_(scan_ids),
            Annotation.review_status == "approved",
            Annotation.annotation_type == "bounding_box",
        )
        .order_by(Annotation.scan_id, Annotation.slice_index, Annotation.created_at)
    )
    return list(db.scalars(statement))


def _annotations_for_review(db: Session, scan_ids: Sequence[UUID]) -> list[Annotation]:
    if not scan_ids:
        return []
    statement = (
        select(Annotation)
        .where(Annotation.scan_id.in_(scan_ids))
        .order_by(Annotation.scan_id, Annotation.slice_index, Annotation.created_at)
    )
    return list(db.scalars(statement))


def _category_names(db: Session, project_id: UUID | None, annotations: Sequence[Annotation]) -> list[str]:
    label_names = []
    if project_id is not None:
        label_names = list(db.scalars(select(Label.name).where(Label.project_id == project_id).order_by(Label.name)))
    annotation_names = [annotation.label for annotation in annotations]
    return sorted(set(label_names + annotation_names))


def _scan_map(scans: Sequence[Scan]) -> dict[UUID, Scan]:
    return {scan.id: scan for scan in scans}


def build_coco_export(db: Session, scans: Sequence[Scan], project_id: UUID | None = None, scan_id: UUID | None = None) -> dict:
    """Return approved bounding boxes in a COCO-style JSON payload."""

    annotations = _approved_bounding_boxes(db, [scan.id for scan in scans])
    category_names = _category_names(db, project_id, annotations)
    category_id_by_name = {name: index + 1 for index, name in enumerate(category_names)}
    images_by_key: dict[tuple[UUID, int], dict] = {}
    scan_by_id = _scan_map(scans)
    coco_annotations = []

    for annotation_index, annotation in enumerate(annotations, start=1):
        scan = scan_by_id[annotation.scan_id]
        image_key = (scan.id, annotation.slice_index)
        if image_key not in images_by_key:
            width, height = _image_size(scan)
            images_by_key[image_key] = {
                "id": len(images_by_key) + 1,
                "file_name": _slice_file_name(scan, annotation.slice_index),
                "width": width,
                "height": height,
                "scan_id": scan.id,
                "slice_index": annotation.slice_index,
            }
        x, y, width, height = _bounding_box(annotation)
        coco_annotations.append(
            {
                "id": annotation_index,
                "image_id": images_by_key[image_key]["id"],
                "category_id": category_id_by_name[annotation.label],
                "bbox": [x, y, width, height],
                "area": width * height,
                "iscrowd": 0,
                "source_annotation_id": annotation.id,
            }
        )

    return {
        "export_format": "coco",
        "project_id": project_id,
        "scan_id": scan_id,
        "export_timestamp": datetime.now(timezone.utc),
        "images": list(images_by_key.values()),
        "annotations": coco_annotations,
        "categories": [{"id": category_id, "name": name} for name, category_id in category_id_by_name.items()],
    }


def build_yolo_export(db: Session, scans: Sequence[Scan], project_id: UUID | None = None, scan_id: UUID | None = None) -> dict:
    """Return approved bounding boxes as YOLO class names and label files."""

    annotations = _approved_bounding_boxes(db, [scan.id for scan in scans])
    class_names = _category_names(db, project_id, annotations)
    class_index_by_name = {name: index for index, name in enumerate(class_names)}
    scan_by_id = _scan_map(scans)
    lines_by_key: dict[tuple[UUID, int], list[str]] = {}

    for annotation in annotations:
        scan = scan_by_id[annotation.scan_id]
        image_width, image_height = _image_size(scan)
        x, y, width, height = _bounding_box(annotation)
        x_center = (x + width / 2) / image_width
        y_center = (y + height / 2) / image_height
        normalized_width = width / image_width
        normalized_height = height / image_height
        lines_by_key.setdefault((scan.id, annotation.slice_index), []).append(
            f"{class_index_by_name[annotation.label]} {x_center:.6f} {y_center:.6f} {normalized_width:.6f} {normalized_height:.6f}"
        )

    files = []
    for scan_id_key, slice_index in sorted(lines_by_key, key=lambda key: (str(key[0]), key[1])):
        scan = scan_by_id[scan_id_key]
        image_width, image_height = _image_size(scan)
        files.append(
            {
                "file_name": _slice_file_name(scan, slice_index).replace(".png", ".txt"),
                "scan_id": scan.id,
                "slice_index": slice_index,
                "image_width": image_width,
                "image_height": image_height,
                "content": "\n".join(lines_by_key[(scan_id_key, slice_index)]),
            }
        )

    return {
        "export_format": "yolo",
        "project_id": project_id,
        "scan_id": scan_id,
        "export_timestamp": datetime.now(timezone.utc),
        "classes": class_names,
        "files": files,
    }


def build_csv_export(db: Session, scans: Sequence[Scan], project_id: UUID | None = None, scan_id: UUID | None = None) -> dict:
    """Return all scoped annotations as a flat CSV string for spreadsheet review."""

    annotations = _annotations_for_review(db, [scan.id for scan in scans])
    scan_by_id = _scan_map(scans)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    for annotation in annotations:
        scan = scan_by_id[annotation.scan_id]
        image_width, image_height = _image_size(scan)
        writer.writerow(
            {
                "annotation_id": annotation.id,
                "project_id": annotation.project_id,
                "scan_id": annotation.scan_id,
                "scan_name": scan.name,
                "slice_index": annotation.slice_index,
                "label": annotation.label,
                "annotation_type": annotation.annotation_type,
                "review_status": annotation.review_status,
                "created_by": annotation.created_by,
                "reviewer": annotation.reviewer,
                "confidence_score": annotation.confidence_score,
                "notes": annotation.notes,
                "coordinates_json": json.dumps(annotation.coordinates, sort_keys=True),
                "image_width": image_width,
                "image_height": image_height,
                "created_at": annotation.created_at.isoformat() if annotation.created_at is not None else "",
                "updated_at": annotation.updated_at.isoformat() if annotation.updated_at is not None else "",
                "reviewed_at": annotation.reviewed_at.isoformat() if annotation.reviewed_at is not None else "",
            }
        )

    return {
        "export_format": "csv",
        "project_id": project_id,
        "scan_id": scan_id,
        "export_timestamp": datetime.now(timezone.utc),
        "file_name": f"{project_id or scan_id or 'annotations'}_annotations.csv",
        "row_count": len(annotations),
        "content": buffer.getvalue(),
    }
