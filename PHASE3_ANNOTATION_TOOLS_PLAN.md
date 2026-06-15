# Phase 3 Annotation Tools Plan

This plan upgrades Medi from a useful imaging review MVP into a faster,
production-minded annotation workspace. Phase 3 focuses on editing, reviewer
efficiency, richer geometry, and ML export formats.

Status: in progress.

## Current State

- Users can create bounding boxes on the current slice.
- Bounding boxes are stored in parsed image pixel space.
- Labels are project-scoped and color-coded.
- Reviewers can approve or reject annotations.
- Project and scan exports return JSON payloads for approved annotations.
- Polygon and segmentation annotations exist in the API shape, but the frontend
  does not yet provide real drawing/editing tools for them.

## Phase 3 Goal

Annotators should be able to create, edit, review, and export high-quality
image labels quickly enough for real research dataset preparation.

## Annotation Editing

- [x] Select an existing annotation on the viewer.
- [x] Move bounding boxes.
- [x] Resize bounding boxes with handles.
- [x] Delete selected annotations from the viewer.
- [x] Update annotation geometry through the API.
- [x] Preserve project, scan, label, and slice validation on every edit.
- [x] Add route tests for update geometry bounds.
- [x] Add route tests for delete permissions.

## Polygon Tools

- [ ] Add polygon drawing mode.
- [ ] Add point placement and close-polygon behavior.
- [ ] Add vertex drag editing.
- [ ] Validate polygon points are numeric and inside image bounds.
- [ ] Render polygon overlays on the current slice.
- [ ] Export polygon coordinates unchanged in image pixel space.

## Segmentation Workflow

- [ ] Define first segmentation representation: mask PNG, RLE, or brush strokes.
- [ ] Add backend storage plan for segmentation masks.
- [ ] Add brush and eraser controls.
- [ ] Add mask opacity control.
- [ ] Add export path for segmentation training data.
- [ ] Keep segmentation objects de-identified and project-scoped.

## Productivity Controls

- [ ] Add undo and redo for local viewer edits.
- [ ] Add keyboard shortcuts for common actions.
- [ ] Add copy annotation to adjacent slice.
- [ ] Add quick label switching.
- [ ] Add zoom and pan controls for detailed image work.
- [ ] Add clear empty states when no label is selected.

## Review Workflow

- [ ] Add `needs_changes` review status.
- [ ] Add reviewer comments visible to annotators.
- [ ] Add review filter tabs: all, pending, approved, rejected, needs changes.
- [ ] Add annotation assignment/ownership field.
- [ ] Add review activity timestamps to the UI.
- [ ] Add review summary metrics per project and scan.

## Version History And Audit

- [ ] Add annotation version model or audit table.
- [ ] Record geometry, label, status, reviewer, and note changes.
- [ ] Show annotation history in the UI.
- [ ] Preserve who changed what and when.
- [ ] Add tests that updates create history records.

## Export Formats

- [ ] Keep current JSON export as the canonical internal format.
- [ ] Add CSV export for spreadsheet review.
- [ ] Add COCO export for bounding boxes and polygons.
- [ ] Add YOLO export for bounding boxes.
- [ ] Add segmentation export once mask storage is implemented.
- [ ] Add export tests for coordinate conversion and project scoping.

## Frontend Plan

- [ ] Split viewer toolbar into explicit modes: pan, box, polygon, mask, select.
- [ ] Add icon buttons and tooltips for annotation tools.
- [x] Add selected annotation styling.
- [ ] Add keyboard shortcut handling.
- [ ] Add annotation edit panel for label/status/notes.
- [x] Keep canvas dimensions tied to parsed scan dimensions.

## Backend Plan

- [ ] Harden `AnnotationUpdate` validation for every geometry type.
- [ ] Add reusable geometry validators.
- [ ] Add annotation history model and migration.
- [ ] Add export service modules by format.
- [ ] Add permission tests for edit, delete, review, and export workflows.
- [ ] Keep all annotation queries organization-scoped.

## Testing Plan

Backend tests:

- [x] Bounding box updates respect image bounds.
- [ ] Polygon creation rejects out-of-bounds points.
- [x] Annotation deletes are role-scoped.
- [ ] Reviewer-only status changes remain enforced.
- [ ] Export formats include only visible project data.
- [ ] Annotation history records update events.

Frontend/manual checks:

- [ ] Draw, select, move, resize, and delete a bounding box.
- [ ] Draw and edit a polygon.
- [ ] Switch labels without losing draft geometry.
- [ ] Use keyboard shortcuts without triggering browser conflicts.
- [ ] Verify overlays align with parsed image pixels at multiple scan sizes.

## First Implementation Sequence

1. [x] Add selected annotation state to the viewer.
2. [x] Add bounding box select/move/resize.
3. [x] Add API update tests for bounding box geometry.
4. [x] Add viewer delete action with role-aware controls.
5. [ ] Add polygon drawing and rendering.
6. [ ] Add polygon backend validation.
7. [ ] Add annotation history table.
8. [ ] Add COCO and YOLO exports for boxes.
9. [ ] Add review filter tabs and `needs_changes`.
10. [ ] Plan segmentation mask storage before brush tools.

## Phase 3 Exit Criteria

- [ ] Annotators can edit and delete bounding boxes without leaving the viewer.
- [ ] Polygon annotations can be created, rendered, edited, and exported.
- [ ] Geometry validation protects image pixel-space coordinates.
- [ ] Reviewers can filter and manage annotation QA efficiently.
- [ ] At least one common ML export format is available beyond internal JSON.
- [ ] Tests cover edit, delete, review, export, and organization scoping.
