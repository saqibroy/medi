"""Reusable annotation geometry validators.

These rules keep all annotation shapes in scan image-pixel space. They are kept
outside annotation CRUD so future import jobs, background workers, or batch
validators can share the same checks.
"""

from math import isfinite

from fastapi import HTTPException, status

from ..models import Scan


def _finite_number(value: object, detail: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return float(value)


def _coordinate_number(coordinates: dict, field_name: str) -> float:
    return _finite_number(coordinates.get(field_name), "Bounding box coordinates must include numeric x, y, width, and height")


def validate_bounding_box_geometry(scan: Scan, coordinates: dict) -> None:
    """Validate image-space bounding box coordinates for one scan."""

    x = _coordinate_number(coordinates, "x")
    y = _coordinate_number(coordinates, "y")
    width = _coordinate_number(coordinates, "width")
    height = _coordinate_number(coordinates, "height")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bounding box must have positive image-space dimensions")
    if scan.width is not None and x + width > scan.width:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bounding box exceeds scan image width")
    if scan.height is not None and y + height > scan.height:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bounding box exceeds scan image height")


def validate_polygon_geometry(scan: Scan, coordinates: dict) -> None:
    """Validate image-space polygon points for one scan."""

    points = coordinates.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon coordinates must include at least three points")

    for point in points:
        if not isinstance(point, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon points must be objects with numeric x and y values")
        x = _finite_number(point.get("x"), "Polygon points must be objects with numeric x and y values")
        y = _finite_number(point.get("y"), "Polygon points must be objects with numeric x and y values")
        if x < 0 or y < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon points must be inside image pixel space")
        if scan.width is not None and x > scan.width:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon point exceeds scan image width")
        if scan.height is not None and y > scan.height:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Polygon point exceeds scan image height")


def validate_segmentation_geometry(coordinates: dict) -> None:
    """Validate the lightweight segmentation annotation JSON shape."""

    if coordinates.get("mask_ref") is not True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Segmentation coordinates must include mask_ref true")
    if coordinates.get("representation") != "png_binary":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Segmentation coordinates must use png_binary representation")


def validate_annotation_geometry(scan: Scan, annotation_type: str, coordinates: dict, slice_index: int) -> None:
    """Validate an annotation's geometry against scan bounds and type shape."""

    if slice_index >= scan.num_slices:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slice index out of range")
    if annotation_type == "bounding_box":
        validate_bounding_box_geometry(scan, coordinates)
        return
    if annotation_type == "polygon":
        validate_polygon_geometry(scan, coordinates)
        return
    if annotation_type == "segmentation":
        validate_segmentation_geometry(coordinates)
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported annotation type")
