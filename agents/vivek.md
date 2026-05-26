# Vivek — API / Backend & Orchestration

**Type:** Component specialist
**Owns:** REST API, pipeline orchestration, job lifecycle, and the canonical contract code

## Allocated skills
- `feature-dev:code-architect`
- `feature-dev:feature-dev`
- `superpowers:test-driven-development`

## Responsibilities / tasks
REST API (`/api/v1/...`), orchestrate Upload → Pre-process → OCR → Translate → Store,
job queue + workers, auth/multi-tenancy stubs, per-user quotas. Owns
[`../tests/contracts/contracts.py`](../tests/contracts/contracts.py) (single source of truth).

**Detailed plan:** [`../docs/components/vivek-backend.md`](../docs/components/vivek-backend.md)

## Working notes & log
- **2026-05-26** — Endpoints: `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/results`,
  `GET /languages`, `GET /me`. Status enum frozen:
  `queued|preprocessing|ocr|translating|done|failed`. Partial-failure → persist OCR even
  if translate fails.
- **2026-05-26** — Contract frozen as Pydantic models; 5 smoke tests pass.
- **2026-05-26** ⚠ **YAGNI (feasibility review):** for the Tier-0 solo build, **defer the
  Redis/RQ queue + workers** and run the pipeline **synchronously in-process** first
  (the async job model is designed in and can be switched on later without rewrite).
  Defer auth/multi-tenancy/quotas until there are real users.
