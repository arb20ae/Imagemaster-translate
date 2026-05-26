# Solove — Result Store

**Type:** Component specialist
**Owns:** persistence of jobs/regions/translations/bboxes + the read API the frontend consumes

## Allocated skills
- `supabase:supabase-postgres-best-practices`
- `superpowers:test-driven-development`

## Responsibilities / tasks
Persist results so the frontend renders them and Phase-2 overlay is "free" (bboxes stored
in pre-processed pixel space). Serve `JobResult` / `JobStatusResponse`.

**Detailed plan:** [`../docs/components/solove-result-store.md`](../docs/components/solove-result-store.md)

## Working notes & log
- **2026-05-26** — Schema: tenants/users/jobs/image_refs/regions/translations; bbox as
  integer pixel cols in pre-processed space; single-round-trip results query.
- **2026-05-26** ⚠ **CONTRACT ALIGNMENT REQUIRED** (feasibility review):
  - external `job_id` = **UUID** (not bigint);
  - rename to canonical wire names: `ocr_text`→`text`, `detected_lang`→`lang`,
    `bbox_rotation`→`angle`; **flatten** `translation` on the wire;
  - status enum `pending`→`queued`.
- **2026-05-26** ⚠ **YAGNI (feasibility review):** for Tier-0, defer RLS + multi-tenancy;
  consider starting on **SQLite/local Postgres** before Supabase, behind the same interface.
