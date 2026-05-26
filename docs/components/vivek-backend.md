# Vivek — API / Backend & Orchestration Plan (Phase 1)

**Owner:** Vivek  
**Date:** 2026-05-26  
**Reference:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`  
**Role scope:** REST API, pipeline orchestration, async job queue + workers, auth &
multi-tenancy stubs, per-user usage quotas. Coordinates but does NOT implement:
`PreProcessor`, `OcrEngine`, `Translator`, `Glossary` (owned by Omar, Nour, Iona, Matt).

---

## 1. API Endpoints

All endpoints are prefixed `/api/v1`. Responses are JSON. Auth header:
`Authorization: Bearer <token>` (stubbed in Phase 1; real JWT in Tier 1 hardening).

### 1.1 Upload & Job Creation

**POST /api/v1/jobs**

Request (multipart/form-data):
```
file:        <image binary>   # JPEG, PNG, TIFF, or PDF page
src_lang:    "en" | "ar"      # source language (auto-detect fallback planned)
tgt_lang:    "en" | "ar"      # target language
```

Response 202 Accepted:
```json
{
  "job_id": "uuid-v4",
  "status": "queued",
  "created_at": "ISO8601",
  "poll_url": "/api/v1/jobs/{job_id}"
}
```

Design notes:
- 202 not 200: the job is queued, not done. The client polls or uses the webhook.
- Validate file MIME type and size (configurable limit, default 20 MB). Reject early
  to avoid wasting worker budget.
- Write image to object storage (S3-compatible); store only the object key in the DB,
  never the binary in Postgres.
- Insert job row with `status=queued`; enqueue task referencing `job_id`.
- Quota gate runs here: if user is over their monthly image allowance, return 429
  with `quota_exceeded` error before any storage write.

---

### 1.2 Job Status

**GET /api/v1/jobs/{job_id}**

Response 200:
```json
{
  "job_id": "uuid-v4",
  "status": "queued | preprocessing | ocr | translating | done | failed",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "src_lang": "en",
  "tgt_lang": "ar",
  "stage_detail": "translating 42/67 regions",  // optional progress hint
  "error": null | { "code": "ocr_timeout", "message": "..." }
}
```

Design notes:
- Status field is the single source of truth; frontend polls this until
  `done` or `failed`.
- `stage_detail` is best-effort; if a worker does not emit it, omit the field.
- Recommend 2-second polling interval with exponential back-off up to 10 s;
  WebSocket/SSE upgrade is a Tier 1 nice-to-have, not Phase 1.

---

### 1.3 Fetch Results

**GET /api/v1/jobs/{job_id}/results**

Available only when `status == done`.

Response 200:
```json
{
  "job_id": "uuid-v4",
  "src_lang": "en",
  "tgt_lang": "ar",
  "image_url": "https://<cdn>/jobs/<id>/normalized.jpg",  // pre-signed URL, TTL 1h
  "regions": [
    {
      "region_id": "uuid",
      "text": "Screed layer",
      "translation": "طبقة الطراطة",
      "bbox": { "x": 120, "y": 340, "w": 180, "h": 24 },
      "confidence": 0.91,
      "low_confidence": false,
      "glossary_hit": true,
      "canonical_term": "screed"
    }
  ],
  "stats": {
    "region_count": 67,
    "low_confidence_count": 5,
    "glossary_hit_rate": 0.72
  }
}
```

Design notes:
- `low_confidence: true` when OCR confidence < threshold (configurable, default 0.70).
  Frontend surfaces a flag for user review (spec §9).
- `glossary_hit` indicates the canonical glossary term was used; helps Matt measure
  glossary coverage.
- `image_url` is a short-lived pre-signed URL to the normalized image (post-preprocessor).
  Bboxes are in normalized-image pixel space so overlay is trivial in Phase 2.
- Returns 404 if job not found, 409 if job is not yet `done`.

---

### 1.4 Language List

**GET /api/v1/languages**

Response 200:
```json
{
  "pairs": [
    { "src": "en", "tgt": "ar", "available": true },
    { "src": "ar", "tgt": "en", "available": true }
  ]
}
```

Design notes:
- Static in Phase 1; backed by a config value in env/DB for later rollout.
- Drives the frontend language picker; avoids hardcoding on the client.

---

### 1.5 User / Auth Stubs (Phase 1 foundation)

**GET /api/v1/me** — returns authenticated user info and quota state.

```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "tenant_id": "uuid",           // null for solo tier
  "quota": {
    "monthly_images_allowed": 50,
    "monthly_images_used": 12,
    "resets_at": "ISO8601"
  }
}
```

- In Phase 1 (solo/Tier 0): auth middleware accepts a static API key from env
  (`IMAGEMASTER_API_KEY`). The `user_id` is a fixed sentinel. No login flow yet.
- Designed so swapping to JWT in Tier 1 is a one-file change in the auth middleware.

---

## 2. Async Job Lifecycle

### Why Async?

OCR on a dense architectural drawing (often 300 dpi, A1 size) can take 5–30 seconds
depending on the engine. LLM translation of 50–100 regions adds another 5–15 seconds.
Synchronous HTTP would time out or leave the browser hanging. An async job queue
decouples request receipt from execution, gives clean status semantics, and lets
workers scale horizontally without changing the API.

### State Machine

```
queued
  → preprocessing     (worker picks up job; PreProcessor.process called)
  → ocr               (normalized image passed to OcrEngine.extract)
  → translating       (regions passed to Translator.translate, glossary injected)
  → done              (results persisted; available via /results)
  → failed            (any unrecoverable error; partial results optionally saved)
```

State transitions are always forward (no re-entry except via a retry mechanism).
Each transition writes `updated_at` + `status` to the jobs DB row atomically.

### Partial Failure Behaviour

- OCR succeeds, translation fails → job enters `failed` with `error.code = "translate_error"`.
  OCR regions ARE persisted so the raw extracted text is not lost. The `/results`
  endpoint returns 409 (not done), but a future `GET /api/v1/jobs/{id}/ocr_raw`
  endpoint can expose the raw OCR output for debugging / manual translation.
- Pre-processor fails → job enters `failed` with `error.code = "preprocess_error"`.
  No downstream stages run.
- Partial region translation failure (one LLM call fails mid-batch) → Translator
  returns a best-effort result with `confidence: null` and `translation: null` on
  affected regions; job reaches `done` with `stats.failed_region_count > 0`. Frontend
  flags those regions. This is the least disruptive failure mode for the user.
- Worker crash / timeout → job remains `queued` or intermediate; a cleanup cron
  (every 5 min) requeues jobs stuck in a non-terminal state for > configured timeout
  (default: preprocessing 60s, ocr 120s, translating 180s).

---

## 3. Pipeline Wiring

The orchestration layer owns the *sequence and error handling*; each stage is a
dependency-injected adapter that satisfies a typed protocol (spec §3 contracts).
No stage knows about the others.

```
worker.run(job_id):
  job   = db.get_job(job_id)
  image = storage.get(job.image_key)

  # Stage 1 — Pre-process
  db.set_status(job_id, "preprocessing")
  normalized = PreProcessor.process(image)          # Omar's implementation
  storage.put(job.normalized_key, normalized)

  # Stage 2 — OCR
  db.set_status(job_id, "ocr")
  regions = OcrEngine.extract(normalized)           # Nour's implementation

  # Stage 3 — Glossary + Translation
  db.set_status(job_id, "translating")
  glossary = Glossary.lookup_batch(regions, src, tgt)  # Matt's implementation
  regions  = Translator.translate(regions, src, tgt, glossary)  # Iona's implementation

  # Persist
  ResultStore.save(job_id, regions)                 # Solove's implementation
  db.set_status(job_id, "done")
```

### Swappability Contract

Each stage is injected through a protocol/interface (Python `Protocol` type). The
worker factory reads env config to select the concrete implementation:

```
PREPROCESSOR_IMPL = "opencv"   # → OpenCVPreProcessor()
OCR_IMPL          = "google"   # → GoogleDocAIOcrEngine()   or "azure" / "mistral"
TRANSLATOR_IMPL   = "claude"   # → ClaudeTranslator()
```

Switching OCR engine for an A/B test = change one env var + redeploy workers.
No orchestration code changes.

---

## 4. Tech Choices & Justification

### Framework: FastAPI (Python)

- Python has the strongest OCR/CV/ML ecosystem (the other stage owners all use Python).
- FastAPI gives async request handling, automatic OpenAPI docs, Pydantic models for
  strict request/response validation, and dependency injection — the right fit for a
  small team moving fast with typed contracts.
- Comparable performance to Node.js for I/O-bound API work; good enough for all tiers.

### Queue: Redis + RQ (with a Celery migration path)

- **Redis** is a single dependency that serves both the job queue and a fast
  status-cache layer. Available as a managed add-on on Render/Railway/Fly with zero
  ops overhead at Tier 0.
- **RQ (Redis Queue)** is intentionally simple: enqueue a Python function, a worker
  process picks it up. Minimal config overhead for a solo dev in Phase 1.
- RQ's limitation is no native task routing or priority queues. **Migration path:**
  if Tier 2/3 demands priority lanes (e.g. "premium users get a fast lane") or
  cross-service routing, swap to **Celery + Redis broker** with zero changes to the
  worker business logic (Celery tasks are plain Python callables, same as RQ jobs).
  The swap is isolated to `queue/` module; pipeline code is unchanged.
- Alternative (Celery from day one) adds config surface area without benefit at
  Tier 0. YAGNI.

### Horizontal Scaling

Workers are stateless Python processes. Each reads a job from Redis, runs the pipeline,
writes results to the DB/storage, exits. To handle more concurrency:
- Tier 0: 1 worker process on the same VM as the API.
- Tier 1: 2–4 workers as separate containers (same image, `CMD rq worker`).
- Tier 2/3: autoscaling worker pool (container autoscaling on Render/Fly, or ECS/GKE).
  Workers pull from a shared Redis queue; stateless design means any worker handles
  any job.

No application code changes between tiers — only deployment config.

### Database

Postgres (managed: Supabase / Render Postgres). Owned and schemed by Solove (Result
Store), but the jobs table row schema is Vivek's:

```
jobs (
  id           UUID PRIMARY KEY,
  user_id      UUID NOT NULL,
  tenant_id    UUID,
  status       TEXT NOT NULL DEFAULT 'queued',
  src_lang     TEXT NOT NULL,
  tgt_lang     TEXT NOT NULL,
  image_key    TEXT NOT NULL,       -- object storage key
  normalized_key TEXT,             -- written after pre-processing
  error_code   TEXT,
  error_msg    TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
)
```

### Object Storage

S3-compatible (AWS S3, Cloudflare R2, or MinIO for local dev). The API layer writes
the upload; pre-processor reads and writes back the normalized image. Workers reference
objects by key; they never pass large binaries through the queue (only `job_id` is
enqueued).

---

## 5. Auth, Multi-Tenancy & Quota (Phase 1 Stubs)

### Phase 1 (Tier 0) — API-key stub

- Single static API key read from `IMAGEMASTER_API_KEY` env var.
- All requests are treated as a single `user_id = "owner"`.
- Auth middleware lives in `api/middleware/auth.py`; designed as a FastAPI dependency
  so it can be swapped without touching route handlers.

### Tier 1 design-in (not built yet, but designed for)

- JWT-based auth (e.g. Supabase Auth or Auth0). Middleware verifies token, extracts
  `user_id` and `tenant_id`, injects into request state. Route handlers are unchanged.
- `tenants` table enables university cohort onboarding: a tenant is a university or
  firm; users belong to one tenant.
- Quota row per user (or per tenant for group plans):

```
user_quotas (
  user_id              UUID PRIMARY KEY,
  monthly_images_allowed  INT DEFAULT 50,
  monthly_images_used     INT DEFAULT 0,
  period_start         TIMESTAMPTZ
)
```

- The quota gate in `POST /api/v1/jobs` increments `monthly_images_used` atomically
  (Postgres `UPDATE ... RETURNING`). Exceeding the limit returns HTTP 429 with a
  `Retry-After` header indicating quota reset time.
- In Phase 1 the quota table exists with a single row for the owner. The gate runs in
  production code from day one, so no migration is needed when real users are added.

---

## 6. Error Handling

| Scenario | HTTP | Job state | Behaviour |
|---|---|---|---|
| File too large | 400 | not created | Reject before storage write |
| Unsupported MIME type | 415 | not created | Reject immediately |
| Quota exceeded | 429 | not created | Return `quota_exceeded` + reset time |
| Pre-processor crash | — | `failed` | `error_code = preprocess_error`; no downstream |
| OCR timeout | — | `failed` | `error_code = ocr_timeout`; raw bytes preserved |
| Translate partial fail | — | `done` | Affected regions have `translation = null`; flagged |
| Translate total fail | — | `failed` | `error_code = translate_error`; OCR regions saved |
| Worker crash (unhandled) | — | stuck → requeued | Cleanup cron requeues after timeout |
| Job not found | 404 | — | Standard 404 JSON |
| Results not ready | 409 | any non-done | Return current status + poll hint |

All errors are logged with `job_id`, `user_id`, `stage`, and stack trace for
observability. Error responses follow a consistent envelope:

```json
{ "error": { "code": "quota_exceeded", "message": "Human-readable message" } }
```

---

## 7. TDD Approach

Following team working agreement: TDD by default.

### Unit tests (fast, no I/O)

- Route handler logic: inject mock DB + storage + queue; assert correct HTTP status
  and response shape for each endpoint.
- Pipeline orchestration: mock all four stage interfaces; assert state transitions
  fire in order and that partial-failure paths set the correct `status` + `error_code`.
- Quota gate: mock DB; assert 429 fires at boundary, 202 fires below.
- Auth middleware: assert valid key passes, invalid key returns 401.

### Integration tests (real Redis + Postgres, mocked stages)

- Enqueue a job, run the worker in-process, assert the DB row reaches `done` and
  `ResultStore.save` was called with correct regions.
- Test the stuck-job cleanup cron: insert a job with `status=ocr` and
  `updated_at = now() - 5min`; run cron; assert job is requeued.

### Contract tests (stage interface compliance)

- Each stage adapter (Omar, Nour, Iona, Matt) must pass a shared contract test suite
  that asserts the return type and shape of their interface method. This lives in
  `tests/contracts/` and is run by each stage's CI as well as Vivek's.

### End-to-end smoke test

- Upload a known fixture image (small, English), assert job reaches `done`, assert
  regions are non-empty and have expected fields. Run on every PR.

---

## 8. Ordered Task List

**Week 1 — Foundations**

1. Set up FastAPI project skeleton: `api/`, `workers/`, `queue/`, `tests/`.
2. Define Pydantic models for all request/response shapes (this is the shared
   contract that Zoriaz integrates against).
3. Implement `POST /api/v1/jobs` (file validation, storage write, job row insert,
   enqueue) — TDD.
4. Implement `GET /api/v1/jobs/{job_id}` (status poll) — TDD.
5. Implement auth middleware stub (static API key).
6. Implement quota gate stub (single-user, always passes, but code path wired).

**Week 2 — Worker & Pipeline**

7. Implement worker entry point (`workers/pipeline_worker.py`) with injected stage
   mocks; assert state transitions — TDD.
8. Implement protocol definitions for all four stage interfaces (Python `Protocol`).
   Share with Omar, Nour, Iona, Matt as the binding contract.
9. Implement stuck-job cleanup cron.
10. Implement `GET /api/v1/jobs/{job_id}/results` — TDD.
11. Implement `GET /api/v1/languages` — trivial.
12. Implement `GET /api/v1/me` — quota state read.

**Week 3 — Integration & Hardening**

13. Integration test: full job lifecycle with real Redis + Postgres (Docker Compose).
14. Wire in Omar's PreProcessor once his interface is ready; run contract tests.
15. Wire in Nour's OcrEngine; run contract tests; adjust status timing.
16. Wire in Iona's Translator + Matt's Glossary; run contract tests.
17. End-to-end smoke test with a real fixture image.
18. Pre-signed URL generation for `image_url` in results.
19. Logging + basic error tracking (Sentry DSN from env, optional).

**Week 4 — Observability & Docs**

20. Structured JSON logging for every state transition and stage call.
21. OpenAPI spec review with Zoriaz; agree on any shape adjustments.
22. Document local dev setup (Docker Compose: API + worker + Redis + Postgres).
23. Acceptance checklist run against spec §9 success criteria.

---

## 9. Risks & Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| OCR stage takes > 2 min on large A1 drawings | Medium | Medium | Configurable per-stage timeout; partial-failure path preserves OCR output |
| Redis flap loses enqueued job | Low | Medium | RQ job persistence (`persist=True`); cleanup cron recovers stuck jobs |
| Object storage cost surprise on large uploads | Low | Low | 20 MB file size limit; pre-processor outputs smaller normalized image |
| Stage interface contract breaks mid-sprint | Medium | High | Shared `tests/contracts/` suite run by all owners catches regressions immediately |
| Pre-signed URL expiry races (frontend loads slow) | Low | Low | Default TTL 1 hour; increase if field testing shows issues |

### Open Questions

1. **Webhook vs polling:** Should Phase 1 support a webhook callback on job completion?
   Simpler UX but adds outbound HTTP complexity. Defer to Tier 1 unless Zoriaz needs it.

2. **Retry policy:** Should failed jobs be automatically retried (e.g. transient OCR
   timeout), or only on explicit user action? Recommend: one automatic retry for
   `ocr_timeout`; no auto-retry for `translate_error` (LLM failures are usually
   configuration, not transient).

3. **Job TTL / data retention:** How long are results kept? Permanent storage costs
   accumulate. Propose: 7-day TTL on the object storage image + results in Tier 0;
   configurable per tenant in Tier 3. Needs Abdo/Kian sign-off.

4. **Normalized image format:** PreProcessor (Omar) — what image format and DPI does
   the normalized output use? This determines `image_url` MIME type and bbox coordinate
   space. Must be agreed before Solove schemas the regions table.

5. **src_lang auto-detect:** The spec implies language auto-detection is desirable.
   OCR engine returns a detected `lang` per region. Should the API accept
   `src_lang = "auto"` and resolve from OcrEngine output? Phase 1 stub: accept the
   field, ignore it, require explicit lang. Phase 2: resolve from OcrEngine.

6. **Multi-page PDF:** Should Phase 1 support multi-page PDFs or only single images?
   Recommend: single-image only for Phase 1 (simplest job model); multi-page is a
   job-fan-out concern for Phase 2.

---

## Summary

Vivek owns the spine of the system: the REST API that accepts uploads and exposes
results, the async pipeline that sequences Omar → Nour → Iona/Matt → Solove, the
queue/worker infrastructure, and the auth/quota scaffolding. By keeping every stage
behind a typed protocol and injecting them as config, the pipeline is fully swappable
without touching orchestration code — enabling the OCR engine A/B tests and the LLM
upgrades that will carry the product from Phase 1 to Phase 3.
