# Medical Image Quarantine And De-identification Profile

Status: `medi-deid-screening-v1` implemented and regression tested. Formal
deployment validation, organization-specific intake policy, UID
pseudonymization, and validated OCR/defacing remain open production gates.

This document defines Medi's first enforceable intake boundary for uploaded
DICOM and NIfTI data. It is a conservative metadata-screening profile for the
research product; it is not evidence that a dataset is legally anonymous and it
does not replace a deployment-specific DPIA, data-processing agreement, or
clinical de-identification validation.

## Threat Model

Patient or research-subject identifiers can enter through:

- standard DICOM patient, accession, physician, and institution tags;
- private DICOM elements and free-text values;
- the DICOM `BurnedInAnnotation` declaration or text embedded in pixels;
- NIfTI descriptive, auxiliary-file, and intent-name header fields;
- uploaded filenames and archive member paths;
- linked sidecars, annotations, logs, exports, or external AI services.

The v1 gate assumes authenticated administrators upload data that is intended
to be de-identified. It detects known unsafe metadata and fails closed where the
supported parser can make a deterministic decision. It cannot detect every
identifier, perform OCR, deface head MRI, validate UID pseudonymization, or
prove anonymization against linked datasets.

## Quarantine Flow

1. Validate size, MIME hint, supported container, and tenant/project access.
2. Replace the client filename with a neutral format-derived object name.
3. Write the original only under
   `org/{org}/project/{project}/scan/{scan}/quarantine/original/...`.
4. Parse into a temporary directory and evaluate
   `medi-deid-screening-v1`; do not expose temporary previews.
5. If the profile passes, copy the original to the approved `original/` prefix,
   remove the quarantine copy, store derived previews, and mark the scan ready.
6. If the profile finds a risk, keep only the quarantined original, discard
   previews, and mark the scan quarantined with safe evidence containing tag or
   field names but never their values.
7. If parsing fails, keep the original quarantined and mark ingestion failed.

Quarantined scans may appear in authorized scan lists and metadata panels so an
administrator can see the safe intake result. Slice pixels, signed URLs,
annotations, masks, and every scan/project export must exclude or reject them.

## Version 1 Decision Rules

DICOM and DICOM ZIP pass only when:

- no populated known PHI-bearing tag is detected;
- no populated private data element is detected;
- `BurnedInAnnotation` is explicitly `NO`;
- archive members use safe relative `.dcm` paths with neutral numeric,
  `IM...`, or `slice-...` names; and
- parsing and image limits pass.

NIfTI passes only when the supported NIfTI-1 parser succeeds and the
`descrip`, `aux_file`, and `intent_name` text fields are empty. Filename values
are never retained in object keys or public responses.

The decision record stores the profile version, status, timestamp, and safe
risk identifiers. It never stores the detected value.

## Human Review And Remediation

A quarantined object is not released by changing a database flag. An operator
must inspect and de-identify it in an approved isolated tool, verify burned-in
pixel text and defacing requirements when applicable, then upload the remediated
copy as a new intake. The original remains subject to the deployment retention
and deletion policy.

Before supporting identifiable or pseudonymized data, a deployment still needs
a reviewed DICOM profile, private-tag policy, UID strategy, validated pixel/OCR
workflow, human-review procedure, immutable audit trail, and deletion evidence.

## External AI Boundary

No intake byte, metadata value, preview, annotation, or risk evidence is sent to
an external AI API by this profile. Any future external processor remains
deny-by-default and requires an explicitly approved provider, purpose, data
classification, transfer basis, retention policy, and audit trail.
