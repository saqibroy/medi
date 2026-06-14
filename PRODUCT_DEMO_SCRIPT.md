# Medi Product Demo Script

This script is for a 7-10 minute demo of the current Medi research MVP. It uses
the seeded synthetic workspace and avoids clinical claims.

## Demo Goal

Show that Medi helps a small research or AI team organize de-identified imaging
annotation work from project setup through review and ML export.

Core message:

> Medi gives research teams a project workspace for medical image annotation,
> reviewer QA, and clean export without building an internal labeling tool.

## Setup

Run the app with Docker Compose:

```bash
docker compose up --build
```

Open:

- Frontend: `http://localhost:8080`
- Backend docs: `http://localhost:8000/docs`

Demo users:

- Admin: `admin@medi.local` / `password`
- Annotator: `annotator@medi.local` / `password`
- Reviewer: `reviewer@medi.local` / `password`

Seeded story:

- Workspace: `Medi Research Lab`
- MRI project: `Neuro Oncology Research`
- CT project: `Thoracic CT Nodule Review`
- Labels include `tumour`, `lesion`, `normal`, `nodule`, and `healthy_tissue`
- Review states include approved, pending, and rejected annotations

## Talk Track

### 1. Position The Product

Say:

> Medi is a research-focused medical image annotation workspace. The first use
> case is de-identified dataset preparation for AI teams, labs, and education
> programs. It is not a diagnostic product and it is not clinical decision
> support.

Show:

- Login page.
- Sign in as `admin@medi.local`.

Point out:

- The product opens directly into the workbench, not a marketing page.
- The demo data is synthetic.

### 2. Show Project-Based Organization

Show:

- Project selector in the left panel.
- `Neuro Oncology Research`.
- `Thoracic CT Nodule Review`.
- Workspace stats for scans, labels, approved annotations, and pending
  annotations.

Say:

> The main business object is a project. That is where scans, labels,
> annotations, review status, and export all come together.

Buyer value:

- Teams can separate datasets by modality, research question, or customer.
- Labels are project-specific, so one team can have tumour labels while another
  has nodule labels.

### 3. Show Labels And Admin Control

Show:

- Label manager.
- Color swatches.
- Create/edit controls as admin.

Say:

> Admins define the taxonomy for the project before annotation starts. This
> keeps the export consistent and avoids every annotator inventing their own
> label names.

Optional action:

- Create a temporary label named `edema`.
- Delete it after showing that label management works.

Buyer value:

- Project-scoped label control.
- Fewer inconsistent downstream ML classes.

### 4. Show Scan Selection And Viewer

Show:

- Scan list.
- Select `Brain MRI T1` or `Chest CT Contrast`.
- Move the slice navigator.

Say:

> Phase 1 validates the workflow with generated preview slices. Phase 2 adds
> real DICOM and NIfTI parsing so slice count, spacing, metadata, and pixels come
> from uploaded imaging files.

Buyer value:

- The current product flow is usable for workflow validation.
- The roadmap is honest about real imaging support.

### 5. Create An Annotation

Show:

- Select a label.
- Use bounding box mode.
- Draw a box on the viewer.
- Confirm the annotation appears in the right panel.

Say:

> Annotators work in image pixel coordinates. Each annotation is tied to a
> project, scan, slice, label, creator, and review status.

Buyer value:

- Clean provenance for ML data.
- Annotation records are ready for audit and export.

### 6. Show Reviewer Workflow

Show:

- Existing approved, pending, and rejected annotations in the annotation list.
- Sign out.
- Sign in as `reviewer@medi.local`.
- Approve or reject a pending annotation if available.

Say:

> Review status prevents raw labels from going straight into training data.
> Reviewers can approve or reject annotations before export.

Buyer value:

- Better dataset quality.
- Clear separation between annotation and QA.

### 7. Show Role Enforcement

Show:

- Sign in as `annotator@medi.local`.
- Point out admin-only controls are hidden or disabled.

Say:

> Admins manage projects and labels. Annotators create labels on images.
> Reviewers handle QA. The workflow is simple today, but the ownership model is
> already in place.

Buyer value:

- Safer team workflow.
- Lower risk of accidental project setup changes.

### 8. Show ML Export

Show:

- Sign back in as admin if needed.
- Use ML Export panel.
- Export project dataset.
- Show totals, approved count, pending count, and JSON payload.

Say:

> Export includes approved labels for ML training and keeps pending work visible
> so a project manager knows what still needs QA.

Buyer value:

- ML teams get structured data.
- Managers can see quality state before training.

### 9. Close With Roadmap And Pricing

Say:

> The next product step is real DICOM/NIfTI ingestion, then stronger annotation
> tools like editable boxes, polygons, masks, and richer export formats. The
> recommended first commercial offer is Team Research at $399 per month, with a
> paid concierge pilot for teams that want onboarding.

Reference:

- `PHASE2_IMAGING_PLAN.md`
- `BUSINESS_PRICING_MODEL.md`

## Questions To Ask Prospects

- What imaging format do you need first: DICOM series, NIfTI, or both?
- How many studies are in the first dataset?
- Who annotates, and who reviews?
- What export format does your ML pipeline need?
- Is your data already de-identified?
- Do you need software only, or annotation labor too?
- What would make this worth paying for this month?

## Demo Success Criteria

A strong demo produces at least one of these:

- A prospect asks to upload their own de-identified sample dataset.
- A prospect confirms the export shape matches their ML workflow.
- A prospect names a missing feature that blocks payment.
- A prospect agrees to a paid pilot.

## Known Demo Limitations

Be direct about these:

- Uploaded files are stored but not parsed into real image pixels yet.
- The viewer currently renders generated preview slices.
- DICOM/NIfTI ingestion is planned in Phase 2.
- The product is for research workflows, not diagnosis.
- Compliance controls such as audit logs, SSO, and formal HIPAA readiness are
  later roadmap items.
