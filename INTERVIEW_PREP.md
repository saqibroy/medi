# Interview Prep

## What Marius Will Show You

A production medical annotation platform will look bigger and stricter than this learning repo. It will usually have authentication and role-based authorization so radiologists, reviewers, ML engineers, and admins see different actions. It will load real DICOM objects from PACS, WADO-RS, or cloud storage rather than simulated PNG slices. Images and masks may live in S3, GCS, Azure Blob Storage, or a hospital imaging archive, while relational tables store metadata, annotation state, review status, and audit trails.

Production systems also use database migrations instead of `create_all`, background jobs for conversion and export, stronger test coverage, observability, security review, and careful handling of PHI. This repo keeps those ideas visible in small, commented code paths so you can explain the real concepts without needing enterprise infrastructure on your laptop.

## Questions You Should Be Able To Answer

1. What is the difference between a scan and an annotation?
   A scan is the imaging study or volume metadata. An annotation is a label and geometry tied to one scan and usually one slice.

2. Why does the backend validate `slice_index`?
   It prevents annotations from pointing outside the available image volume, which would break viewers and corrupt training data.

3. Why are coordinates stored as JSON?
   Different annotation types need different shapes: boxes use `x/y/width/height`, polygons use point arrays, and masks may reference mask files.

4. Why should ML export include only approved annotations?
   Approved labels passed QA, while pending labels are not trusted yet and rejected labels are known bad examples for training.

5. What does `confidence_score` mean?
   It captures how certain a radiologist is, and ML teams can use it to weight examples or inspect uncertain cases.

6. Why is review implemented as `PATCH`?
   Review changes only a few fields on an annotation, so partial update semantics are clearer than replacing the whole object.

7. What would change with real DICOM loading?
   The viewer would load DICOM imageIds through Cornerstone loaders, decode pixel data, apply windowing, and read metadata from DICOM tags.

8. Why do project managers need annotation statistics?
   Counts by label, type, status, slice, and radiologist reveal progress, class imbalance, QA backlog, and coverage gaps.

9. What is the purpose of service modules?
   Routers translate HTTP, while services own business rules, validation, database queries, and reusable workflow logic.

10. What would you improve before production?
    Add auth, migrations, tests, real storage, audit logging, PHI safeguards, pagination, background exports, and monitoring.

## How To Read An Unfamiliar Codebase

1. Start with the entry point. In this repo that is `backend/main.py` for FastAPI and `frontend/src/App.tsx` for React.
2. Trace one endpoint end to end. For example, follow `GET /scans/{scan_id}/export` from router to service to model to frontend API client.
3. Read the data models. `backend/models.py`, `backend/schemas.py`, and `frontend/src/types` explain the core contract.
4. Understand the data flow before touching component code. Identify where data is fetched, where state lives, and which component renders it.
5. Make the smallest change that fits the existing pattern, then run the relevant backend and frontend checks.

## Key Concepts To Know

DICOM is the standard format for medical imaging. It contains both pixel data and metadata such as patient identifiers, study dates, modality, spacing, orientation, and windowing settings.

Annotation types describe geometry. A bounding box is a rectangle around a finding, a polygon traces an irregular region, and a segmentation mask labels pixels or voxels directly.

The radiologist to ML pipeline usually goes from image ingestion to annotation, QA review, export, dataset versioning, model training, model evaluation, and clinical review.

Review workflows exist because medical labels are high-impact data. A second reviewer can approve trustworthy labels, reject mistakes, or leave uncertain work pending.

Windowing means mapping raw pixel intensities to visible grayscale. CT and MRI values often need different window center and level settings before anatomy is readable.

A segmentation mask is denser than a bounding box. A box says where an object roughly is, while a mask says which exact pixels or voxels belong to the structure.

## Cornerstone3D Concepts

RenderingEngine is Cornerstone3D's rendering manager. It owns viewports and underlying canvas or WebGL resources, so React code should destroy it on unmount.

Viewports are rendering targets. A STACK viewport navigates 2D image slices, while a VOLUME viewport loads a 3D volume and can render reconstructed planes or 3D views.

ImageIds are loader-specific strings that tell Cornerstone where to get pixels. A DICOM WADO URI might look like `wadouri:https://server/wado?studyUID=...`.

Tool registration connects interaction tools to a viewer. A production app registers tools such as bounding boxes, length measurements, pan, zoom, and window-level controls, then activates them for specific mouse or keyboard inputs.

STACK is simpler and common for slice-by-slice annotation. VOLUME is more powerful for 3D navigation, multiplanar reconstruction, and volumetric workflows, but it has heavier loading and memory considerations.
