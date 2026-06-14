# Medi Business Pricing Model

This pricing model is for the first research MVP, not for hospital production or
clinical decision support. Medi should sell de-identified annotation workflow,
review, and ML-ready export for research teams.

Status: proposed.

## Pricing Position

Medi should start as a focused research workspace:

> Project-based medical image annotation and review for small AI and research
> teams that need clean exports without buying a heavy enterprise platform.

Do not sell:

- Diagnosis.
- Treatment recommendations.
- Clinical workflow replacement.
- HIPAA-ready hospital deployment before the controls exist.
- Unlimited storage or unlimited annotation labor.

Sell:

- Faster project setup.
- Project-scoped labels.
- Review and approval workflow.
- Clean export for ML training.
- Traceability: who labeled what, when, and with what review status.

## Early Customer Segments

Best first buyers:

- University labs with grant-funded imaging projects.
- Medical AI startups preparing proof-of-concept datasets.
- Small annotation teams working with de-identified scans.
- Education programs teaching imaging annotation.

Avoid as first buyers:

- Hospitals that require full procurement, BAA, SOC 2, SSO, audit retention, and
  production EHR/PACS integrations.
- Teams expecting Medi to provide radiologist annotation labor.
- Teams handling identifiable patient data before security/compliance controls
  are mature.

## Recommended Tiers

### Starter Research

Price: `$99/month` per workspace.

Designed for:

- Individual researchers.
- Student teams.
- Demo projects.
- Early pilots.

Includes:

- 1 workspace.
- Up to 3 users.
- Up to 5 projects.
- Up to 250 uploaded studies.
- Basic labels, review statuses, and JSON export.
- Community/email support.

Why this tier exists:

It lowers adoption friction and gives Medi a paid entry point without promising
enterprise capabilities.

### Team Research

Price: `$399/month` per workspace.

Designed for:

- Small labs.
- Small medical AI teams.
- Annotation teams with reviewers.

Includes:

- Up to 10 users.
- Up to 25 projects.
- Up to 2,000 uploaded studies.
- Project and scan export.
- Reviewer workflow.
- Priority email support.
- Basic onboarding call.

Why this tier exists:

This should be the default target plan. It maps to a team that has real dataset
work but does not yet need enterprise procurement.

### Growth Research

Price: `$999/month` per workspace.

Designed for:

- Funded labs.
- Startups building multiple datasets.
- Teams that need more storage, projects, and support.

Includes:

- Up to 30 users.
- Up to 100 projects.
- Up to 10,000 uploaded studies.
- Advanced exports as they become available.
- Import support for DICOM/NIfTI workflows.
- Priority support and monthly success check-in.

Why this tier exists:

It creates room for serious research usage before jumping to enterprise sales.

### Enterprise Research

Price: custom annual contract.

Start around: `$15,000/year`.

Designed for:

- Larger AI teams.
- Multi-lab research groups.
- Organizations that need deployment review and procurement.

Includes:

- Custom user and storage limits.
- SSO when implemented.
- Audit logs when implemented.
- Dedicated deployment support.
- Custom data retention.
- Private cloud or self-hosting discussion.

Why this tier exists:

Some customers need procurement and guarantees. Keep it quote-based because
security, storage, support, and deployment expectations vary widely.

## Usage Guardrails

Do not make the first pricing model purely per-user. Imaging workloads create
real storage and processing costs, so pricing should combine workspace tier,
study limits, and paid overages.

Suggested overages:

- Extra user: `$20/user/month`.
- Extra 1,000 uploaded studies: `$100/month`.
- Extra 100 GB managed storage: `$50/month`.
- Assisted onboarding: `$500` one-time.
- Custom export format: quote-based.

## Free Trial

Offer a 14-day trial for Starter and Team.

Trial limits:

- 2 users.
- 2 projects.
- 50 studies.
- Watermarked or limited export is optional, but avoid making the trial feel
  broken. A useful trial sells better than a frustrating one.

Trial goal:

The user should upload sample data, create labels, annotate, review, and export
within one session.

## First Revenue Experiment

Run this before building complex billing:

1. Create a short demo script using the synthetic project data.
2. Offer Team Research at `$399/month` to 10 target labs/startups.
3. Offer a concierge pilot: setup help plus 30 days of usage for `$500`.
4. Track:
   - Did they understand the value in the first demo?
   - Did they have de-identified data ready?
   - Did they need DICOM/NIfTI before paying?
   - Did they ask for annotation labor or only software?
   - Did export format decide the sale?
5. If 2 of 10 agree to a paid pilot, keep building the research workflow.

## Landing Page Copy

Headline:

> Medical image annotation for research datasets.

Subhead:

> Create projects, define labels, review annotations, and export approved data
> for ML training without building an internal labeling tool from scratch.

Primary CTA:

> Start research pilot

Secondary CTA:

> View demo workspace

Trust language:

- Designed for de-identified research data.
- Not for diagnosis or clinical decision support.
- Synthetic demo data included.

## Pricing Page Copy

Starter Research:

> For individual researchers validating a workflow.

Team Research:

> For labs and startups preparing reviewed ML datasets.

Growth Research:

> For funded teams managing multiple annotation projects.

Enterprise Research:

> For organizations that need custom deployment, security review, and support.

## What Must Exist Before Charging

Minimum:

- [x] Login and roles.
- [x] Projects.
- [x] Labels.
- [x] Annotation creation.
- [x] Review status.
- [x] Export.
- [x] Docker Compose demo.
- [x] CI checks.
- [ ] Real DICOM/NIfTI ingestion for uploaded scans.
- [x] Short demo script.
- [ ] Clear terms: de-identified research use only.

Charging can start before every enterprise feature exists, but customers must
understand this is a research MVP.

## Pricing Risks

- Too cheap: serious teams may assume the product is a toy.
- Too expensive: labs will continue using open-source/local tools.
- Unlimited usage: storage and compute costs can quietly break margins.
- Selling compliance too early: security promises can trap the product before
  product-market fit.
- Selling annotation labor: service delivery can overwhelm software development.

## Recommendation

Use Team Research at `$399/month` as the first real offer. Pair it with a
`$500` paid pilot for teams that want onboarding help. Keep Starter available
for researchers, but optimize demos, roadmap, and product decisions around the
Team Research buyer.
