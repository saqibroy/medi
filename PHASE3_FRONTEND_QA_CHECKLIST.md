# Phase 3 Frontend QA Checklist

Use this checklist before closing Phase 3. It verifies the annotation viewer as
a user-facing workflow, not just as compiled TypeScript.

Status: complete. Last executed July 16, 2026.

Post-exit regression on July 23, 2026: the dataset-release panel gained retained
artifact checksum, download, revocation, and legacy-materialization states. Its
TypeScript/Vite production build and backend authorization/lifecycle contract
tests pass; the original viewer QA evidence below remains unchanged.

## Setup

Run the app with seeded demo data:

```bash
docker compose up --build
```

Open:

- Frontend: `http://localhost:8080`
- API docs: `http://localhost:8000/docs`

Fallback local setup:

```bash
DATABASE_URL=sqlite:///./local-dev.db alembic upgrade head
DATABASE_URL=sqlite:///./local-dev.db python3 -m backend.seed
DATABASE_URL=sqlite:///./local-dev.db uvicorn backend.main:app --reload
cd frontend
npm run dev -- --host 127.0.0.1
```

Use seeded users:

- Admin: `admin@medi.local` / `password`
- Annotator: `annotator@medi.local` / `password`
- Reviewer: `reviewer@medi.local` / `password`

Test browsers and sizes:

- Desktop: 1440 x 900
- Small laptop/tablet width: 1024 x 768
- Narrow/mobile sanity check: 390 x 844

Record evidence with a short note and screenshot name for each completed check.

## QA Matrix

| Check | Account | View | Status | Evidence |
| --- | --- | --- | --- | --- |
| Bounding box draw/select/move/resize/delete | Admin | 1440 x 900 | Pass | Created, moved, resized, undo/redo verified at exact API coordinates, then deleted. `bounding-box-workflow.png` |
| Polygon draw and vertex edit | Annotator | 1440 x 900 | Pass | Polygon creation and persisted vertex edit verified through the API. `polygon-workflow.png` |
| Label switching preserves draft geometry | Annotator | 1440 x 900 | Pass | Draft survived label change and saved with the completion-time label. `label-switch-draft.png` |
| Keyboard shortcuts avoid browser conflicts | Annotator | 1440 x 900 | Pass | Tool/label shortcuts passed and focused-input events were not intercepted. `keyboard-shortcuts.png` |
| Overlay alignment at multiple image sizes | Admin | 1440 x 900, 1024 x 768, 390 x 844 | Pass | Visual alignment confirmed; 50/100/200/400% scaling and pan verified. `overlay-*.png` |

## Automated Browser Pass

With the backend and frontend running against disposable seeded data, execute:

```bash
node scripts/phase3_browser_qa.mjs
```

Optional environment variables: `APP_URL`, `API_URL`, `CHROME_BIN`,
`CHROME_DEBUG_PORT`, and `SCREENSHOT_DIR`. The default evidence directory is
`/tmp/medi_phase3_frontend_qa`.

July 16, 2026 evidence:

- Google Chrome 139 headless, seeded SQLite database, frontend at
  `http://127.0.0.1:5173`, backend at `http://127.0.0.1:8000`.
- Bounding box final coordinates after move, resize, undo, and redo were
  `x=185`, `y=180`, `width=140`, `height=105`; deletion was then verified.
- Polygon creation, persisted vertex editing, and label-at-completion behavior
  passed through UI gestures plus API assertions.
- Canvas display widths were 256, 512, 1024, and 2048 pixels at 50%, 100%,
  200%, and 400%; pan changed viewport scroll position.
- Desktop, tablet, and narrow screenshots were visually inspected. Overlays
  remained anchored, browser runtime errors were zero, and page-level
  horizontal overflow was absent.
- No parsed DICOM/NIfTI upload was present in the disposable browser dataset;
  parsed-image bounds remain covered by the backend imaging fixture tests.

## Bounding Box Workflow

1. Log in as `admin@medi.local`.
2. Select `Neuro Oncology Research`.
3. Select `Brain MRI T1`.
4. Choose label `tumour`.
5. Select the Box tool.
6. Draw a box on a slice without an existing seeded box.
7. Select the new box with the Select tool.
8. Drag the box body to move it.
9. Drag each visible corner handle to resize it.
10. Use `Ctrl+Z` and `Ctrl+Y` to undo and redo one geometry edit.
11. Delete the selected box.

Expected result:

- The box appears where drawn and remains aligned to the image after save.
- Selection styling and handles appear only on the selected box.
- Move and resize update the saved annotation without shifting the image.
- Undo and redo restore the previous and next geometry.
- Admin delete removes the overlay and list item.

## Polygon Workflow

1. Log in as `annotator@medi.local`.
2. Select a project and scan with labels.
3. Choose label `lesion`.
4. Select the Polygon tool.
5. Click at least four points.
6. Finish by clicking the first point or pressing `Enter`.
7. Select the polygon.
8. Drag one vertex.
9. Switch slices away and back.

Expected result:

- Polygon draft follows the pointer before completion.
- Finished polygon appears in the annotation list.
- Vertex edits save and remain after slice navigation.
- Polygon cannot be completed with fewer than three points.

## Label Switching During Draft

1. Log in as `annotator@medi.local`.
2. Select the Polygon tool.
3. Start a polygon draft with two points.
4. Change the selected label.
5. Add more points and finish the polygon.

Expected result:

- The draft geometry stays visible while the label changes.
- The saved annotation uses the label selected at completion time.
- The draft is cleared only after save, cancel, scan change, slice change, or tool change.

## Keyboard Shortcuts

Run these while focus is on the viewer, then again while focus is in a text
input to make sure typing is not hijacked.

- `V`: Select tool.
- `H`: Pan tool.
- `B`: Box tool.
- `P`: Polygon tool.
- `M`: Mask tool.
- `[` and `]`: previous/next label.
- `ArrowLeft` and `ArrowRight`: previous/next slice.
- `Enter`: finish polygon with at least three points.
- `Escape`: cancel draft and clear selection.
- `Delete` or `Backspace`: delete selected annotation when the role allows it.
- `Ctrl+Z` / `Ctrl+Y`: undo/redo viewer geometry or mask edits.

Expected result:

- Shortcuts work only outside inputs/selects/textareas.
- Browser navigation, page scrolling, and form typing are not broken.
- Disabled role actions do not mutate annotations.

## Overlay Alignment

1. Test one synthetic seeded scan.
2. Test one uploaded or parsed DICOM/NIfTI scan if available.
3. Draw a box near each image edge.
4. Draw a polygon near each image edge.
5. Zoom to 50%, 100%, 200%, and 400%.
6. Pan around the zoomed image.
7. Move between desktop, tablet, and narrow/mobile widths.

Expected result:

- Saved coordinates stay in original image pixel space.
- Overlays remain anchored to the same anatomy while zooming and panning.
- Handles, tooltips, buttons, and annotation controls do not overlap incoherently.
- Text in toolbar controls does not overflow on narrow widths.

## Exit Decision

Phase 3 frontend QA can be marked complete only when all QA Matrix rows are
`Pass` with evidence notes. Any failure should create a follow-up item in
`PHASE3_ANNOTATION_TOOLS_PLAN.md` before Phase 4 starts.
