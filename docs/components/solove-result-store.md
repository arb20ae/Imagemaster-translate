# Solove — Result Store: Phase-1 Plan

**Component:** Result Store
**Owner:** Solove
**Date:** 2026-05-26
**Reference spec:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`
**Team charter:** `docs/team/TEAM.md`

---

## 1. Responsibility

The Result Store is the persistence layer for the entire pipeline. It receives the
output of the Translator stage, stores it durably, and serves it to the frontend for
the glossary view. Critically, it stores bounding boxes with enough precision that
Phase-2 overlay rendering needs zero re-processing — the data is already there.

The Result Store does NOT orchestrate the pipeline (that is Vivek / API Backend) and
does NOT own image pre-processing. It owns: schema, write path, read API, image
object-storage references, and the read queries the frontend depends on.

---

## 2. Data Schema

### 2.1 Entity overview

```
tenants (1) ─┬─── (N) users
             └─── (N) jobs
                         │
                         ├─── (1) image_refs
                         └─── (N) regions
                                     └─── (N) translations  [one per target language]
```

### 2.2 Table definitions

```sql
-- ── tenants ────────────────────────────────────────────────────────────────
-- A tenant is a solo user in Tier-0, a university cohort in Tier-3.
-- Kept minimal for Phase 1; fields added as the scaling ladder climbs.
create table tenants (
  id           bigint generated always as identity primary key,
  slug         text   not null unique,          -- e.g. "aub-2026"
  display_name text   not null,
  created_at   timestamptz not null default now()
);

-- ── users ──────────────────────────────────────────────────────────────────
-- Supabase auth.users provides the UUID; this table extends it.
create table users (
  id          uuid primary key references auth.users(id) on delete cascade,
  tenant_id   bigint not null references tenants(id),
  created_at  timestamptz not null default now()
);
create index users_tenant_id_idx on users (tenant_id);

-- ── jobs ───────────────────────────────────────────────────────────────────
-- One job = one drawing upload + pipeline run.
-- status drives async lifecycle; partial index keeps worker polling fast.
create type job_status as enum (
  'pending', 'preprocessing', 'ocr', 'translating', 'done', 'failed'
);

create table jobs (
  id              bigint generated always as identity primary key,
  tenant_id       bigint       not null references tenants(id),
  user_id         uuid         not null references users(id),
  status          job_status   not null default 'pending',
  src_lang        text         not null,   -- BCP-47, e.g. "en", "ar"
  tgt_lang        text         not null,
  error_message   text,
  pipeline_meta   jsonb,                   -- engine versions, timing telemetry (append-only)
  created_at      timestamptz  not null default now(),
  updated_at      timestamptz  not null default now()
);

-- Partial index: workers only ever poll non-terminal statuses
create index jobs_active_status_idx on jobs (tenant_id, status, created_at)
  where status in ('pending', 'preprocessing', 'ocr', 'translating');

-- Full index for dashboard / history views
create index jobs_tenant_user_idx on jobs (tenant_id, user_id, created_at desc);

-- ── image_refs ─────────────────────────────────────────────────────────────
-- Metadata about uploaded and pre-processed images.
-- Binary blobs live in object storage; this row holds the references.
create table image_refs (
  id              bigint generated always as identity primary key,
  job_id          bigint not null unique references jobs(id) on delete cascade,
  original_key    text   not null,   -- object-storage key for raw upload
  processed_key   text,              -- object-storage key for pre-processed image
  storage_bucket  text   not null default 'drawings',
  mime_type       text   not null,
  original_width  integer,           -- pixels; null until pre-processor fills it
  original_height integer,
  file_size_bytes bigint,
  created_at      timestamptz not null default now()
);
-- No additional index needed — always looked up by job_id (unique FK above).

-- ── regions ────────────────────────────────────────────────────────────────
-- One region = one text annotation extracted by the OCR adapter.
-- region_index preserves OCR output order for stable glossary sorting.
create table regions (
  id              bigint generated always as identity primary key,
  job_id          bigint  not null references jobs(id) on delete cascade,
  region_index    integer not null,        -- 0-based order within the job
  ocr_text        text    not null,        -- raw OCR output
  detected_lang   text,                   -- BCP-47 as reported by OCR engine
  ocr_confidence  numeric(5,4),           -- 0.0000–1.0000
  -- Bounding box — see §3 for coordinate convention
  bbox_x          integer not null,       -- left edge in pixels
  bbox_y          integer not null,       -- top edge in pixels
  bbox_w          integer not null,       -- width in pixels
  bbox_h          integer not null,       -- height in pixels
  bbox_rotation   numeric(7,4) default 0, -- degrees clockwise; for rotated annotations
  created_at      timestamptz not null default now(),
  unique (job_id, region_index)
);

-- Primary read path: all regions for a job, in order
create index regions_job_order_idx on regions (job_id, region_index);

-- ── translations ───────────────────────────────────────────────────────────
-- One row per (region, target language). Phase 1 has one target language per job,
-- but the schema is language-keyed so multi-language jobs in later phases cost
-- no migration.
create table translations (
  id                  bigint generated always as identity primary key,
  region_id           bigint not null references regions(id) on delete cascade,
  job_id              bigint not null references jobs(id) on delete cascade,  -- denorm for fast job-scoped queries
  tgt_lang            text   not null,
  translated_text     text   not null,
  translation_engine  text   not null,   -- e.g. "claude-3-5-sonnet-20241022"
  glossary_version    text,              -- FK to Matt's glossary version tag
  confidence          numeric(5,4),      -- translation confidence (0–1); null = not provided
  low_confidence_flag boolean not null default false,  -- pre-computed for fast UI filtering
  created_at          timestamptz not null default now(),
  unique (region_id, tgt_lang)
);

-- Primary glossary-view read: all translations for a job, in region order
create index translations_job_lang_idx on translations (job_id, tgt_lang);

-- Fast flag filter (low-confidence items highlighted in UI)
create index translations_low_conf_idx on translations (job_id, tgt_lang)
  where low_confidence_flag = true;
```

### 2.3 Relationship rationale

- `tenants` is the RLS anchor; every user and every job belongs to a tenant, so a
  single policy per table is sufficient for isolation.
- `jobs` owns the lifecycle. The frontend polls job status before requesting results.
- `image_refs` is 1:1 with jobs (separated to keep `jobs` slim and avoid large-column
  row bloat).
- `regions` is the canonical output of Nour's OCR Adapter. The four `bbox_*` integer
  columns plus `bbox_rotation` are denormalized (not JSONB) because they are always
  read together and used in arithmetic by the frontend renderer — normalized columns
  are faster to read and avoid JSONB extraction overhead.
- `translations` is keyed by `(region_id, tgt_lang)` to support future multi-language
  jobs without schema change. The `job_id` denormalization is intentional: the primary
  read query fetches all translations for a job in one pass without a regions join.

---

## 3. Bounding-Box Coordinate Convention

### Convention: top-left origin, pixel units, pre-processed image space

```
(0,0) ──────────────────── x (pixels, right)
  │
  │     ┌──────────────┐
  │     │  bbox_x,y    │  ← top-left corner
  │     │              │
  │     │    bbox_w ──►│
  │     └──────────────┘
  │       ↕ bbox_h
  y (pixels, down)
```

- **Origin:** top-left corner of the pre-processed image (the image served at
  `image_refs.processed_key`). This is the image the frontend displays.
- **Units:** integer pixels in pre-processed image space. The pre-processor records
  `original_width` / `original_height` so the frontend can compute scale factors if
  it ever needs to map back to the raw upload.
- **Columns:** `(bbox_x, bbox_y, bbox_w, bbox_h)` — left edge, top edge, width,
  height. This is the standard CSS/Canvas2D box model and directly maps to:
  - `ctx.strokeRect(bbox_x, bbox_y, bbox_w, bbox_h)` in Canvas2D
  - `left/top/width/height` CSS positioning over the image
  - OpenSeadragon overlay positioning via `viewer.addOverlay(el, new OpenSeadragon.Rect(...))`
- **Rotation:** `bbox_rotation` in degrees clockwise. Zero for most annotations;
  non-zero for rotated leader labels (common in architectural drawings). The frontend
  applies `transform: rotate(Ndeg)` around the bbox center for the overlay.
- **Phase-2 guarantee:** because bboxes are stored in pre-processed image space, the
  overlay renderer in Phase 2 can position translated text directly — no re-OCR, no
  re-computation.
- **Contract with Nour (OCR Adapter):** Nour's `Region{text, bbox, confidence, lang}`
  must deliver bboxes in this convention. If the underlying OCR engine returns
  normalized coordinates (0.0–1.0), Nour's adapter denormalizes them using the
  image dimensions before handing them to the Result Store write path.

---

## 4. Read API Shape (Frontend Contract)

This is the exact JSON contract Zoriaz's frontend consumes. Vivek exposes it as a
FastAPI endpoint; the Result Store supplies the underlying query.

### 4.1 GET /jobs/{job_id}/results

**Purpose:** Fetch the full glossary payload for a completed job.

**Response (HTTP 200):**

```json
{
  "job_id": 42,
  "status": "done",
  "src_lang": "en",
  "tgt_lang": "ar",
  "image": {
    "processed_url": "https://<storage>/drawings/jobs/42/processed.png",
    "width": 3508,
    "height": 2480
  },
  "regions": [
    {
      "region_id": 1001,
      "region_index": 0,
      "ocr_text": "reinforced concrete slab",
      "detected_lang": "en",
      "ocr_confidence": 0.97,
      "bbox": {
        "x": 412,
        "y": 88,
        "w": 340,
        "h": 28,
        "rotation": 0.0
      },
      "translation": {
        "translated_text": "بلاطة خرسانة مسلحة",
        "tgt_lang": "ar",
        "confidence": 0.94,
        "low_confidence": false,
        "glossary_version": "en-ar-v1.2"
      }
    }
  ]
}
```

**Notes:**
- `regions` is ordered by `region_index` (ascending) — the glossary panel renders
  them in OCR-document order.
- `translation` is a single object (not an array) because a job has one `tgt_lang`.
  If a future job produces multiple languages, the field becomes `translations: [...]`
  — the frontend must treat single-language as a special case of that array.
- `bbox` coordinates are in pre-processed image pixels. `image.width` / `image.height`
  allow the frontend to scale overlays if it renders the image at a different size.
- `low_confidence: true` signals the UI to flag that region (e.g. amber highlight +
  review marker in the glossary panel).
- `processed_url` is a time-limited signed URL generated by the API layer; the DB
  stores only the object-storage key.

### 4.2 GET /jobs/{job_id}/status

**Purpose:** Polling endpoint for job lifecycle (used before results are ready).

```json
{
  "job_id": 42,
  "status": "ocr",
  "updated_at": "2026-05-26T14:32:11Z"
}
```

### 4.3 GET /jobs (list)

**Purpose:** Job history for the current user.

```json
{
  "jobs": [
    {
      "job_id": 42,
      "status": "done",
      "src_lang": "en",
      "tgt_lang": "ar",
      "created_at": "2026-05-26T14:30:00Z",
      "thumbnail_url": "https://<storage>/drawings/jobs/42/thumb.png"
    }
  ]
}
```

---

## 5. Image Storage Approach

### Object storage for binaries; DB for metadata only

Binary image data (original upload, pre-processed image, thumbnail) lives in an
S3-compatible object store. The database holds only keys and metadata.

**Rationale:**
- Object storage is orders of magnitude cheaper per GB than Postgres storage.
- Postgres is not optimized for large binary blobs: they bloat TOAST, inflate
  vacuum work, and slow backup/restore.
- Signed URLs decouple access control from serving — the CDN or storage layer
  handles byte delivery without routing through the API.
- Supabase Storage (backed by S3) is the natural choice given the rest of the stack;
  it provides per-bucket RLS-style policies and signed URL generation out of the box.

**Bucket structure:**

```
drawings/
  jobs/{job_id}/original.{ext}    ← raw upload
  jobs/{job_id}/processed.png     ← pre-processor output (Omar)
  jobs/{job_id}/thumb.png         ← thumbnail for job-list UI
```

**Access control:** Supabase Storage policies restrict bucket access to the owning
user's tenant. The API generates short-lived signed URLs (15 minutes) for frontend
consumption; URLs are never stored in the DB.

---

## 6. Storage Technology Choice

### Postgres via Supabase

**Why Postgres:**
- Relational integrity (FK cascades, unique constraints) keeps the pipeline output
  consistent without application-layer guards.
- Row-level security (RLS) enforces tenant isolation at the DB layer — a bug in
  application-layer filtering cannot leak cross-tenant data.
- `jsonb` for the `pipeline_meta` audit trail (append-only, schema-flexible telemetry)
  without sacrificing relational structure for the core data.
- Excellent fit for the glossary join query (single `JOIN` across three tables,
  covered by the composite indexes above).

**Why Supabase specifically:**
- Managed Postgres removes operational burden at Tier-0/1 (no DBA needed).
- Built-in auth (`auth.users`) integrates with RLS policies directly.
- Supabase Storage is co-located, simplifying signed-URL generation.
- Free tier supports Tier-0; Pro/Team tiers support Tier-2/3 with read replicas and
  connection pooling (PgBouncer) available in one config change.
- The schema is standard Postgres — migrating to self-hosted Postgres or another
  managed provider (RDS, Cloud SQL) requires no data-model changes.

**Scaling ladder:**

| Tier | DB posture |
|------|-----------|
| 0 Solo | Supabase free; single connection; direct queries |
| 1 ~10 users | Supabase Pro; enable PgBouncer transaction-mode pooling |
| 2 Field | Add read replica for frontend reads; keep write path on primary |
| 3 Universities | Table partitioning on `jobs` by `tenant_id` if row count demands; Supabase Team or self-hosted |

Multi-tenancy is enforced by RLS from day one — adding a university cohort is
inserting one row in `tenants` and assigning users to it.

---

## 7. RLS Policies

Following the performance-aware pattern (wrap `auth.uid()` in a `SELECT` subquery so
it is evaluated once, not per row):

```sql
-- Enable RLS on all user-data tables
alter table jobs        enable row level security;
alter table image_refs  enable row level security;
alter table regions     enable row level security;
alter table translations enable row level security;
alter table users       enable row level security;

-- jobs: user sees only their own tenant's jobs
create policy jobs_tenant_policy on jobs
  for all to authenticated
  using (
    tenant_id = (
      select tenant_id from users where id = (select auth.uid())
    )
  );

-- image_refs, regions, translations: inherit via job_id
-- Use security-definer helper to avoid repeated subquery
create or replace function current_tenant_id()
returns bigint language sql security definer stable
set search_path = ''
as $$
  select tenant_id from public.users where id = (select auth.uid())
$$;

create policy image_refs_policy on image_refs for all to authenticated
  using (
    job_id in (select id from jobs where tenant_id = current_tenant_id())
  );

create policy regions_policy on regions for all to authenticated
  using (
    job_id in (select id from jobs where tenant_id = current_tenant_id())
  );

create policy translations_policy on translations for all to authenticated
  using (
    job_id in (select id from jobs where tenant_id = current_tenant_id())
  );

-- Index to back the RLS subquery
create index jobs_tenant_id_idx on jobs (tenant_id);
```

---

## 8. Query Patterns

### 8.1 Glossary view — primary read (single round-trip, no N+1)

```sql
-- Returns all regions + translations for a job, in order.
-- Called once per page load; result is cacheable by the API layer.
select
  r.id              as region_id,
  r.region_index,
  r.ocr_text,
  r.detected_lang,
  r.ocr_confidence,
  r.bbox_x,
  r.bbox_y,
  r.bbox_w,
  r.bbox_h,
  r.bbox_rotation,
  t.translated_text,
  t.tgt_lang,
  t.confidence      as translation_confidence,
  t.low_confidence_flag,
  t.glossary_version
from regions r
join translations t on t.region_id = r.id and t.tgt_lang = $2
where r.job_id = $1
order by r.region_index;
```

Uses: `regions_job_order_idx (job_id, region_index)` + `translations_job_lang_idx
(job_id, tgt_lang)`. One query, one round trip — no N+1.

### 8.2 Job status poll

```sql
select id, status, updated_at from jobs where id = $1;
```

Primary key lookup — always fast.

### 8.3 Low-confidence filter (UI review mode)

```sql
select r.*, t.*
from regions r
join translations t on t.region_id = r.id
where t.job_id = $1 and t.tgt_lang = $2 and t.low_confidence_flag = true
order by r.region_index;
```

Uses: `translations_low_conf_idx (job_id, tgt_lang) WHERE low_confidence_flag = true`.
Partial index makes this tiny even on large jobs.

### 8.4 Phase-2 overlay read (identical to 8.1)

Phase-2 overlay needs the same fields — `bbox_*` columns are already present. No
additional query or migration needed.

---

## 9. Write Path

The API Backend (Vivek) calls into the Result Store write path. The write contract is:

1. `create_job(user_id, tenant_id, src_lang, tgt_lang) -> job_id`
2. `update_job_status(job_id, status)`
3. `store_image_ref(job_id, original_key, mime_type, ...)`
4. `update_image_processed(job_id, processed_key, width, height)`
5. `upsert_regions(job_id, regions: list[Region])` — bulk insert, `ON CONFLICT (job_id, region_index) DO UPDATE`
6. `upsert_translations(regions: list[RegionWithTranslation])` — bulk insert, `ON CONFLICT (region_id, tgt_lang) DO UPDATE`
7. `mark_job_done(job_id)` / `mark_job_failed(job_id, error_message)`

Steps 5 and 6 use a single `INSERT ... ON CONFLICT DO UPDATE` batch (one statement
per table) to avoid N inserts for N regions. Idempotent upserts also mean a worker
can retry a failed translation run without duplicating rows.

---

## 10. TDD Approach

Every query and write function is tested before the implementation is wired up.

**Unit tests (pytest + `psycopg` against a local Supabase Docker / `supabase start`):**
- Schema migration applies cleanly on a fresh DB.
- `upsert_regions` with 50 regions round-trips correctly; re-running is idempotent.
- `upsert_translations` with mismatched `region_id` raises a FK violation.
- Glossary-view query returns regions in `region_index` order.
- Low-confidence partial index is used (verify with `EXPLAIN` in test).

**RLS integration tests:**
- User A cannot read User B's jobs (different tenants).
- User A can read their own job's regions and translations.
- Service-role bypass (used by pipeline workers) bypasses RLS correctly.

**Fixture strategy:** a seeded job with 10 regions and 10 translations covers all
read-path tests. A conftest fixture creates and tears down the job in a transaction.

**Contract test:** the glossary-view query output is validated against the JSON
schema in §4.1 using `pydantic` to catch drift between DB shape and API response.

---

## 11. Ordered Task List

1. **Schema migration** — write `migrations/001_result_store.sql`; includes all
   tables, indexes, RLS policies, and `current_tenant_id()` helper.
2. **Test fixtures** — `conftest.py` with Supabase local dev setup; seeded tenant,
   user, job, image_ref.
3. **Write-path tests** — pytest tests for each write function (red phase).
4. **Write-path implementation** — Python data-access layer satisfying tests.
5. **Read-path tests** — pytest tests for glossary-view query, status poll,
   low-confidence filter; contract test against §4.1 JSON schema.
6. **Read-path implementation** — queries and Pydantic response models.
7. **RLS integration tests** — multi-tenant isolation scenarios.
8. **Image-ref helpers** — signed URL generation wrapper (delegates to Supabase
   Storage SDK; tested with a mock storage client).
9. **API surface review with Vivek** — confirm write-path call signatures match
   pipeline orchestration expectations.
10. **Contract review with Zoriaz** — confirm §4.1 JSON shape matches frontend
    consumption; confirm bbox coordinate convention matches overlay plan.
11. **Performance verification** — run `EXPLAIN ANALYZE` on glossary-view query
    against a 500-region seed; confirm index scans, not seq scans.

---

## 12. Risks and Open Questions

| Risk / Question | Severity | Owner | Mitigation / Resolution needed |
|-----------------|----------|-------|-------------------------------|
| OCR engine bbox coordinate convention varies (normalized 0–1 vs pixel; top-left vs bottom-left origin) | HIGH | Nour + Solove | Nour's adapter contract must specify pixel, top-left output. Confirm before Step 4. |
| Pre-processor output image size differs from original — bboxes must be in processed-image space | HIGH | Omar + Solove | Omar to confirm and document the output image dimensions in `image_refs`; adapter adjusts before write. |
| Phase-2 overlay requires sub-word character-level bboxes (e.g. per-glyph for Arabic RTL rendering) | MEDIUM | Solove + Zoriaz | Current schema stores one bbox per region (word/phrase). If character-level is needed, `regions` gets a `char_boxes jsonb` column. Defer until Phase-2 spike. |
| Signed URL expiry during long frontend sessions | LOW | Vivek + Solove | API refreshes signed URLs on demand; frontend does not cache the URL beyond the session. |
| `pipeline_meta` JSONB growing unboundedly on retries | LOW | Vivek | Pipeline writes append entries with timestamps; a cleanup job can archive old entries. Decision deferred. |
| Multi-language jobs (Phase 1+ rollout) — one job → multiple tgt_lang | LOW | Solove | Schema already supports it (`translations` keyed by `tgt_lang`); API response shape needs a minor extension. No migration needed. |
| Supabase free tier row/storage limits during load testing | LOW | Abdo | Switch to Supabase Pro before any field testing; Pro limits are well above Tier-1 scale. |

---

## 13. Interface Contracts This Plan Depends On

- **Nour (OCR Adapter):** `Region{text, bbox{x,y,w,h,rotation}, confidence, lang}`
  in pixel coordinates, top-left origin, pre-processed image space.
- **Vivek (API Backend):** calls the write-path functions in §9 in the correct order;
  owns job status transitions; generates signed URLs using the object keys stored here.
- **Zoriaz (Frontend):** consumes the JSON shape in §4.1 exactly; renders bboxes
  using `(x, y, w, h, rotation)` against the `image.width` / `image.height` from the
  same response.
- **Matt (Glossary Store):** `glossary_version` tag stored in `translations.glossary_version`
  for auditability; no direct DB dependency between glossary store and result store.
