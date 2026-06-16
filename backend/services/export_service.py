"""ML export format builders for reviewed annotation datasets."""

import csv
import json
from io import StringIO
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Annotation, Label, Scan, SegmentationMask


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
    "mask_available",
    "mask_file_name",
    "mask_width",
    "mask_height",
    "mask_encoding",
    "mask_byte_size",
    "mask_checksum_sha256",
    "mask_api_path",
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


def _mask_file_name(scan: Scan, annotation: Annotation) -> str:
    return f"masks/{scan.id}/{annotation.id}_slice_{annotation.slice_index:06d}.png"


def _mask_api_path(annotation: Annotation) -> str:
    return f"/annotations/{annotation.id}/mask/{annotation.slice_index}"


def _bounding_box(annotation: Annotation) -> tuple[float, float, float, float]:
    coordinates = annotation.coordinates
    return (
        float(coordinates["x"]),
        float(coordinates["y"]),
        float(coordinates["width"]),
        float(coordinates["height"]),
    )


def _polygon_points(annotation: Annotation) -> list[tuple[float, float]]:
    points = annotation.coordinates.get("points", [])
    parsed_points = []
    for point in points:
        if isinstance(point, dict):
            parsed_points.append((float(point["x"]), float(point["y"])))
        else:
            parsed_points.append((float(point[0]), float(point[1])))
    return parsed_points


def _polygon_bbox(points: Sequence[tuple[float, float]]) -> tuple[float, float, float, float]:
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    min_x = min(x_values)
    min_y = min(y_values)
    return min_x, min_y, max(x_values) - min_x, max(y_values) - min_y


def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
    area = 0.0
    for index, current in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += current[0] * next_point[1] - next_point[0] * current[1]
    return abs(area) / 2


def _polygon_segmentation(points: Sequence[tuple[float, float]]) -> list[list[float]]:
    return [[coordinate for point in points for coordinate in point]]


def _approved_coco_annotations(db: Session, scan_ids: Sequence[UUID]) -> list[Annotation]:
    if not scan_ids:
        return []
    statement = (
        select(Annotation)
        .where(
            Annotation.scan_id.in_(scan_ids),
            Annotation.review_status == "approved",
            Annotation.annotation_type.in_(("bounding_box", "polygon")),
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


def _approved_segmentations(db: Session, scan_ids: Sequence[UUID]) -> list[Annotation]:
    if not scan_ids:
        return []
    statement = (
        select(Annotation)
        .where(
            Annotation.scan_id.in_(scan_ids),
            Annotation.review_status == "approved",
            Annotation.annotation_type == "segmentation",
        )
        .order_by(Annotation.scan_id, Annotation.slice_index, Annotation.created_at)
    )
    return list(db.scalars(statement))


def _mask_map(db: Session, annotations: Sequence[Annotation]) -> dict[UUID, SegmentationMask]:
    annotation_ids = [annotation.id for annotation in annotations]
    if not annotation_ids:
        return {}
    statement = select(SegmentationMask).where(SegmentationMask.annotation_id.in_(annotation_ids))
    return {mask.annotation_id: mask for mask in db.scalars(statement)}


def _category_names(db: Session, project_id: UUID | None, annotations: Sequence[Annotation]) -> list[str]:
    label_names = []
    if project_id is not None:
        label_names = list(db.scalars(select(Label.name).where(Label.project_id == project_id).order_by(Label.name)))
    annotation_names = [annotation.label for annotation in annotations]
    return sorted(set(label_names + annotation_names))


def _scan_map(scans: Sequence[Scan]) -> dict[UUID, Scan]:
    return {scan.id: scan for scan in scans}


def build_coco_export(db: Session, scans: Sequence[Scan], project_id: UUID | None = None, scan_id: UUID | None = None) -> dict:
    """Return approved boxes and polygons in a COCO-style JSON payload."""

    annotations = _approved_coco_annotations(db, [scan.id for scan in scans])
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
        segmentation = None
        if annotation.annotation_type == "polygon":
            points = _polygon_points(annotation)
            x, y, width, height = _polygon_bbox(points)
            area = _polygon_area(points)
            segmentation = _polygon_segmentation(points)
        else:
            x, y, width, height = _bounding_box(annotation)
            area = width * height
        coco_annotations.append(
            {
                "id": annotation_index,
                "image_id": images_by_key[image_key]["id"],
                "category_id": category_id_by_name[annotation.label],
                "bbox": [x, y, width, height],
                "area": area,
                "iscrowd": 0,
                "source_annotation_id": annotation.id,
                "annotation_type": annotation.annotation_type,
                "segmentation": segmentation,
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
    mask_by_annotation_id = _mask_map(db, [annotation for annotation in annotations if annotation.annotation_type == "segmentation"])
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    for annotation in annotations:
        scan = scan_by_id[annotation.scan_id]
        image_width, image_height = _image_size(scan)
        mask = mask_by_annotation_id.get(annotation.id)
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
                "mask_available": bool(mask),
                "mask_file_name": _mask_file_name(scan, annotation) if mask else "",
                "mask_width": mask.width if mask else "",
                "mask_height": mask.height if mask else "",
                "mask_encoding": mask.encoding if mask else "",
                "mask_byte_size": mask.byte_size if mask else "",
                "mask_checksum_sha256": mask.checksum_sha256 if mask else "",
                "mask_api_path": _mask_api_path(annotation) if mask else "",
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


def build_segmentation_export(db: Session, scans: Sequence[Scan], project_id: UUID | None = None, scan_id: UUID | None = None) -> dict:
    """Return a manifest for approved segmentation masks and their metadata."""

    annotations = _approved_segmentations(db, [scan.id for scan in scans])
    scan_by_id = _scan_map(scans)
    mask_by_annotation_id = _mask_map(db, annotations)
    masks = []

    for annotation in annotations:
        scan = scan_by_id[annotation.scan_id]
        image_width, image_height = _image_size(scan)
        mask = mask_by_annotation_id.get(annotation.id)
        masks.append(
            {
                "annotation_id": annotation.id,
                "project_id": annotation.project_id,
                "scan_id": annotation.scan_id,
                "scan_name": scan.name,
                "slice_index": annotation.slice_index,
                "label": annotation.label,
                "review_status": annotation.review_status,
                "image_width": image_width,
                "image_height": image_height,
                "mask_available": mask is not None,
                "mask_file_name": _mask_file_name(scan, annotation) if mask else None,
                "mask_api_path": _mask_api_path(annotation) if mask else None,
                "mask_width": mask.width if mask else None,
                "mask_height": mask.height if mask else None,
                "mask_encoding": mask.encoding if mask else None,
                "mask_byte_size": mask.byte_size if mask else None,
                "mask_checksum_sha256": mask.checksum_sha256 if mask else None,
            }
        )

    return {
        "export_format": "segmentation_manifest",
        "project_id": project_id,
        "scan_id": scan_id,
        "export_timestamp": datetime.now(timezone.utc),
        "mask_count": len(masks),
        "available_mask_count": sum(1 for mask in masks if mask["mask_available"]),
        "missing_mask_count": sum(1 for mask in masks if not mask["mask_available"]),
        "masks": masks,
    }
