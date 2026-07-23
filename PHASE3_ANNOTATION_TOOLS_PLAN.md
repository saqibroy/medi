# Phase 3 Annotation Tools Plan

This plan upgrades Medi from a useful imaging review MVP into a faster,
production-minded annotation workspace. Phase 3 focuses on editing, reviewer
efficiency, richer geometry, and ML export formats.

Status: complete.

Frontend QA protocol: `PHASE3_FRONTEND_QA_CHECKLIST.md`.

## Current State

- Users can create bounding boxes on the current slice.
- Bounding boxes are stored in parsed image pixel space.
- Labels are project-scoped and color-coded.
- Reviewers can approve or reject annotations.
- Project and scan exports return JSON payloads for approved annotations.
- Polygon annotations can be drawn, edited, validated, rendered, and exported in
  the internal JSON shape. Segmentation annotations now have local brush tools
  plus frontend save/load/delete behavior backed by PNG mask persistence.

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

- [x] Add polygon drawing mode.
- [x] Add point placement and close-polygon behavior.
- [x] Add vertex drag editing.
- [x] Validate polygon points are numeric and inside image bounds.
- [x] Render polygon overlays on the current slice.
- [x] Export polygon coordinates unchanged in image pixel space.

## Segmentation Workflow

- [x] Define first segmentation representation: mask PNG, RLE, or brush strokes.
- [x] Add backend storage plan for segmentation masks.
- [x] Add brush and eraser controls.
- [x] Add mask opacity control.
- [x] Add backend segmentation mask metadata, storage, and API endpoints.
- [x] Add frontend mask save/load behavior through the API.
- [x] Add export path for segmentation training data.
- [x] Add local undo/redo snapshots for mask brush edits.
- [x] Keep segmentation objects de-identified and project-scoped.

## Productivity Controls

- [x] Add undo and redo for local viewer edits.
- [x] Add keyboard shortcuts for common actions.
- [x] Add copy annotation to adjacent slice.
- [x] Add quick label switching.
- [x] Add zoom and pan controls for detailed image work.
- [x] Add clear empty states when no label is selected.

## Review Workflow

- [x] Add `needs_changes` review status.
- [x] Add reviewer comments visible to annotators.
- [x] Add review filter tabs: all, pending, approved, rejected, needs changes.
- [x] Add annotation assignment/ownership field.
- [x] Add review activity timestamps to the UI.
- [x] Add review summary metrics per project and scan.

## Version History And Audit

- [x] Add annotation version model or audit table.
- [x] Record geometry, label, status, reviewer, and note changes.
- [x] Show annotation history in the UI.
- [x] Preserve who changed what and when.
- [x] Add tests that updates create history records.

## Export Formats

- [x] Keep current JSON export as the canonical internal format.
- [x] Add CSV export for spreadsheet review.
- [x] Add COCO export for bounding boxes.
- [x] Add COCO export for polygons.
- [x] Add YOLO export for bounding boxes.
- [x] Add segmentation export once mask storage is implemented.
- [x] Add export tests for coordinate conversion and project scoping.

## Frontend Plan

- [x] Split viewer toolbar into explicit modes: pan, box, polygon, mask, select.
- [x] Add icon buttons and tooltips for annotation tools.
- [x] Add selected annotation styling.
- [x] Add keyboard shortcut handling.
- [x] Add annotation edit panel for label/status/notes.
- [x] Keep canvas dimensions tied to parsed scan dimensions.

## Backend Plan

- [x] Harden `AnnotationUpdate` validation for every geometry type.
- [x] Add reusable geometry validators.
- [x] Add annotation history model and migration.
- [x] Add export service modules by format.
- [x] Add segmentation mask model, migration, local storage service, and routes.
- [x] Add permission tests for edit, delete, review, and export workflows.
- [x] Keep all annotation queries organization-scoped.

## Testing Plan

Backend tests:

- [x] Bounding box updates respect image bounds.
- [x] Polygon creation rejects out-of-bounds points.
- [x] Annotation deletes are role-scoped.
- [x] Reviewer-only status changes remain enforced.
- [x] Export formats include only visible project data.
- [x] Annotation history records update events.
- [x] Segmentation mask routes validate dimensions, organization scope, deletes,
  and audit history.

Frontend/manual checks:

- [x] Add a repeatable Phase 3 frontend QA checklist with setup, steps,
  expected results, and evidence fields.
- [x] Draw, select, move, resize, and delete a bounding box.
- [x] Draw and edit a polygon.
- [x] Switch labels without losing draft geometry.
- [x] Use keyboard shortcuts without triggering browser conflicts.
- [x] Verify overlay alignment at multiple viewport sizes and zoom levels;
  parsed-image bounds remain covered by backend imaging fixture tests.

## First Implementation Sequence

1. [x] Add selected annotation state to the viewer.
2. [x] Add bounding box select/move/resize.
3. [x] Add API update tests for bounding box geometry.
4. [x] Add viewer delete action with role-aware controls.
5. [x] Add polygon drawing and rendering.
6. [x] Add polygon backend validation.
7. [x] Add polygon vertex drag editing.
8. [x] Add annotation history table.
9. [x] Add COCO and YOLO exports for boxes.
10. [x] Add review filter tabs and `needs_changes`.
11. [x] Add CSV export for spreadsheet review.
12. [x] Add keyboard shortcuts for common annotation actions.
13. [x] Plan segmentation mask storage before brush tools.
14. [x] Add undo and redo for local viewer edits.
15. [x] Add brush and eraser controls for segmentation masks.
16. [x] Add mask opacity control.
17. [x] Add backend segmentation mask model and API endpoints.
18. [x] Add frontend mask save/load behavior through the API.
19. [x] Add segmentation export path for training data.
20. [x] Add local undo/redo snapshots for mask brush edits.
21. [x] Add COCO export for polygon annotations.
22. [x] Add annotation edit panel for label/status/notes.
23. [x] Add review summary metrics per project and scan.
24. [x] Add annotation assignment/ownership field.
25. [x] Add zoom and pan controls for detailed image work.
26. [x] Add copy annotation to adjacent slice.
27. [x] Add clear empty states when no label is selected.
28. [x] Harden `AnnotationUpdate` validation for every geometry type.
29. [x] Add reusable geometry validators.
30. [x] Add permission tests for edit, delete, review, and export workflows.
31. [x] Keep all annotation queries organization-scoped.
32. [x] Split viewer toolbar into explicit modes: pan, box, polygon, mask, select.
33. [x] Add icon buttons and tooltips for annotation tools.
34. [x] Add Phase 3 frontend QA checklist.
35. [x] Execute Phase 3 frontend QA checklist and record evidence.
36. [x] Add exhaustive object-route authorization coverage and prevent
    cross-organization project, label, or assignee references from leaking
    existence or reparenting an annotation away from its scan.
37. [x] Retain an immutable, value-free lineage tombstone when annotation
    deletion removes raw revision history and sensitive edit values.
38. [x] Add retained dataset-release artifact status, checksum, verified
    download, revocation state, and legacy-materialization controls to the
    release panel without changing mutable annotation export behavior.

## Phase 3 Exit Criteria

- [x] Annotators can edit and delete bounding boxes without leaving the viewer.
- [x] Polygon annotations can be created, rendered, edited, and exported.
- [x] Geometry validation protects image pixel-space coordinates.
- [x] Reviewers can filter and manage annotation QA efficiently.
- [x] At least one common ML export format is available beyond internal JSON.
- [x] Tests cover edit, delete, review, export, and organization scoping.
