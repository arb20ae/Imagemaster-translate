# Independent Feasibility & Best-Practice Audit

**Author:** Independent auditor (fresh eyes; did not write any of the planning docs)
**Date:** 2026-05-26
**Reviewed:** README, design spec, TEAM, CONTRACT, Kian + Abdo reviews, all 7 component
plans, `tests/contracts/contracts.py` + `test_contracts.py`.
**Lens applied:** This is built by **one person + AI assistance**, scaling solo → ~10
users → field/LinkedIn testers → universities. The named "team" (Zoriaz, Vivek, Omar,
Nour, Iona, Matt, Solove, Abdo, Kian) are **AI agent personas, not hired engineers.**
Feasibility is judged against that reality, not a funded team.

---

## 1. Verdict

**CONDITIONAL GO — but not on the plan as currently sequenced.** The thinking is
genuinely excellent. The architecture is sound, the contract freeze was the right call,
and the YAGNI discipline on *features* (Phases 2–5, DWG, code text) is exemplary. But the
plan commits the exact mistake it warns about, one level up: it applies YAGNI rigorously
to **features** while building **production-grade infrastructure** (Redis/RQ workers,
Supabase multi-tenancy + RLS, per-user quotas, auth middleware, autoscaling-ready
stateless workers, OpenSeadragon tiling-capable viewer, a 3-engine OCR A/B harness)
*before a single real Arabic drawing has been run through a single OCR engine.*

For a solo developer, that is the wrong risk order. The project's own documents name
**Arabic OCR accuracy on noisy scans as THE central risk** (spec §1, §10; Kian §6; Abdo
risk register) — and then schedule it to be validated in "Stage 2 — accuracy hardening,"
*after* the walking skeleton, the contract, the backend spine, the multi-tenant DB, and
the frontend viewer are built. That means the make-or-break unknown is answered last,
after the most effort is sunk. **A solo dev cannot afford to discover in week 6 that no
managed engine clears CER ≤ 0.15 on real Gulf drawings.**

So: feasible and implementable **yes** — *after* re-sequencing to put a throwaway
Arabic-OCR spike first, and after cutting roughly half the Phase-1 infrastructure down to
Tier-0 reality. As written, it is over-built for "solo + 10 users" and back-loads its
biggest risk. Fix those two things and it is a confident GO.

---

## 2. Top 5 Highest-Impact Recommendations (ranked)

### 1. Run a throwaway Arabic-OCR spike BEFORE the walking skeleton. (Highest impact.)
Time-box it to 3–5 days. No app, no queue, no DB, no contract. A flat Python script:
collect 15–20 real Gulf/MENA drawings (the hardest part — start *today*), hand-label the
text, run Google Document AI, Azure Document Intelligence, and Mistral OCR raw, then with
2–3 OpenCV pre-processing variants, and compute CER. **This single experiment answers
whether the product is viable at all.** Everything downstream is wasted effort if the
answer is "no managed engine clears the bar and fine-tuning PaddleOCR is the only path."
The plan currently schedules this as Stage 2 (Abdo §4); move it to Stage -1. The agent
exercise already produced the metrics, harness design, and escalation path (Nour §4, §9.1)
— pull them forward and run them on real images now. See §4.

### 2. Cut Phase-1 infrastructure to Tier-0 reality; defer the scaling ladder. (YAGNI on infra.)
For solo + 10 invited users, the following are **premature and should be deferred or
stubbed to near-nothing:** Redis/RQ + separate worker processes (start with FastAPI
`BackgroundTasks` or a single in-process worker — 10 users do not need a queue);
Supabase **RLS + multi-tenant `tenants` table** (one owner, then ~10 trusted invitees —
app-level `user_id` filtering is plenty; RLS is real complexity and a real footgun);
**per-user quota tables and 429 gates** (you are the only user — a hard global daily spend
cap protects the wallet far more cheaply); the **history/audit trigger** on the glossary
(a CSV in Git is the moat at 100 terms). The spec's "no rewrite between tiers" goal (§7)
is seductive but is itself a YAGNI violation for a solo MVP: you are paying integration
and cognitive cost *now* to save a refactor you may never need, for a user base that may
never materialise. Build for 10 users; re-architect for universities **if** universities
show up. The modular stage interfaces already make that re-architecture cheap — which is
the part of "scale-ready" actually worth keeping.

### 3. Acquire and hand-label the real Arabic drawing test set NOW — it is the true critical path.
Four plans reference this test set; Kian and Abdo both flag it as "owned by none" and
assign it to "Abdo" — but Abdo is an AI persona. **In solo reality, only the owner can
source real Gulf construction drawings, and that is a human, logistical, relationship-
driven task with a long lead time** (NDAs, asking contacts, anonymising proprietary
sheets). It gates the spike (#1), the OCR engine selection, the accuracy bar, the glossary
seed, and the "it works" claim. Nothing else in the plan can truly be validated without
it. Start collecting before writing any code. If 20 real drawings cannot be sourced, that
is itself a critical finding about project viability.

### 4. Put a hard cost ceiling in before the first cloud API call; don't rely on quotas.
The plan's cost control is per-user quotas — which do nothing when the only user is the
owner running benchmarks in a loop. Each OCR engine call on a large drawing plus a Claude
vision/translation pass costs real money, and the 3-engine A/B *multiplies* that across
the whole test set on every harness run. Add: (a) a hard daily/monthly spend cap at the
billing-account level on every cloud provider (Google/Azure/Mistral/Anthropic) — set it
*before* the first key is used; (b) the image-hash result cache (Nour §6.3) brought
forward so re-running the harness on unchanged images is free; (c) a downscale-before-send
cap (Nour §6.1). See §5.

### 5. Collapse the 9-persona, 4-week, contract-frozen process to match solo cadence.
The multi-agent exercise paid off once — it surfaced the schema-divergence integration
risk on paper (Abdo §2), which is real value. But the *frozen contract + version-bump +
"Kian/Abdo sign-off"* governance is ceremony for a solo dev: you are all nine people. Keep
`tests/contracts/contracts.py` as the single source of truth (it is genuinely good and
worth keeping), but drop the change-control ritual — when the spike reveals that, say,
bbox angle handling needs to change, just change the Pydantic model and the tests. The
real risk for a solo dev is not "uncoordinated specialists drift"; it is "one person burns
weeks polishing seven components before learning the core idea doesn't work." The process
should optimise for fast learning, not coordination overhead that no longer exists.

---

## 3. Feasibility for a Solo Dev + the Thinnest Viable First Build

### Is Phase 1 buildable by one person + AI?
**Yes, but the proposed Phase-1 scope is roughly 2× what it needs to be.** Every
individual component plan is implementable with AI help — none is beyond a capable solo
dev. The problem is the *aggregate*: FastAPI + Redis/RQ + async workers + Supabase +
RLS + multi-tenancy + quotas + auth + object storage + signed URLs + 3 OCR adapters +
ensemble + benchmark harness + Claude integration with prompt caching + Next.js +
OpenSeadragon + SVG overlay + Zustand + a11y + RTL + Playwright E2E. That is a small
team's quarter, presented as a solo Phase 1. It will either take many months or get
half-finished. The fix is not "work harder" — it is to cut.

### Over-engineered for solo / 10 users? Yes. Specifically:
- **Redis/RQ + standalone workers** — unjustified at 10 users. FastAPI `BackgroundTasks`
  or a single worker loop handles this. (Vivek's RQ-over-Celery YAGNI call is good; the
  miss is that *any* broker is YAGNI at this scale.)
- **Supabase RLS + `tenants` + multi-tenant policies** (Solove §2, §7) — real complexity
  and a debugging tax for a single-tenant reality. Defer until a second tenant exists.
- **Per-user quota tables + 429 enforcement** (Vivek §5) — replace with one global spend
  cap. The quota *table* can wait until paying/cohort users exist.
- **OpenSeadragon + DZI tiling** — Kian already deferred tiling (N3); good. For Phase 1,
  `cap at 10 MP and serve the processed image directly`. A plain pan/zoom `<img>` +
  SVG overlay (or a tiny library) is enough until images actually break it.
- **Three OCR engines + ensemble in the product** — the *spike* needs all three to choose
  one; the *shipped app* needs exactly one behind the swappable interface. Don't ship the
  ensemble until the benchmark proves one engine is insufficient (Nour §9.1 path).
- **Glossary history table + Postgres trigger + audit timeline** (Matt §1.2, §4) — a
  versioned CSV/seed file is the moat at MVP size. Defer the audit infra.

### The genuinely thinnest first build (after the spike answers "OCR works"):
1. One FastAPI process. Upload endpoint → runs the pipeline **synchronously in a
   background task** → writes results. No Redis, no separate workers.
2. **One** OCR engine (the spike winner) behind the existing `OcrEngine` interface.
3. Pre-processor: just the high-impact steps the spike proved help (likely grayscale +
   denoise + deskew + upscale + adaptive threshold). Skip the rest until measured.
4. Claude translation with glossary injected from a **CSV/JSON file** (skip Postgres
   glossary entirely for v1) + the prompt caching (Iona's caching design is cheap and
   worth keeping from day one).
5. Storage: SQLite or a single Postgres table for results + local disk / one bucket for
   images. No RLS, no tenants, no quotas — just `user_id` column, single user.
6. Frontend: upload form + results page. Image with SVG bbox overlay + glossary list +
   click-to-locate. Keep Zoriaz's coordinate math and a11y intent; drop tiling/DZI.
7. Keep `tests/contracts/contracts.py` as the typed seam between stages.

This is a 1–2 week build for a solo dev with AI, and it delivers the *entire* MVP success
criterion (spec §9). The deferred infra is added back **only when a tier actually
arrives** — and the modular interfaces (the part of the architecture genuinely worth its
weight) make that cheap.

---

## 4. Risk-First Sequencing Recommendation

The plan's sequence (Abdo §4) is: Contract Freeze → **walking skeleton** → deepen
Omar → Nour → Iona → **accuracy hardening (CER gate)**. The walking-skeleton-first
instinct is correct *best practice for integration risk*. But it answers the wrong risk
first. For this project the dominant risk is **technical (does Arabic OCR work?)**, not
**integration (do the stages connect?)**. Walking skeleton de-risks integration; it does
nothing for the central technical unknown.

**Recommended order:**

- **Stage -1 — Arabic OCR spike (NEW, FIRST, throwaway).** 3–5 days. Real drawings, raw
  engines ± pre-processing, measure CER/WER, bbox IoU, rotation, cost, latency. Exit
  criterion: a clear answer to "can a managed engine clear CER ≤ 0.15 on real Arabic
  drawings, at what cost, with which pre-processing?" The spike **must measure**: (1)
  per-engine CER on Arabic regions (the gate); (2) cost per drawing at list price; (3)
  whether engines return usable rotated-word bboxes (Nour §9.2 — confirm, don't assume);
  (4) the *delta* from 2–3 pre-processing variants (proves Omar's stage earns its
  complexity). Throwaway code — do not gold-plate it into the product.
  - **GO/PIVOT/STOP gate here.** If managed OCR clears the bar → proceed. If only with
    heavy pre-processing → Omar's scope is now evidence-based. If nothing clears it →
    decide on fine-tuning (a different, larger project) or pivot to an easier language
    pair *before* building the app, not after.
- **Stage 0 — Thin vertical slice** (the §3 build) against the real winning engine, not
  stubs. This *is* the walking skeleton, but with the real OCR/translation already
  validated — so it proves integration AND product value at once.
- **Stage 1 — Deepen only what the slice proves weak.** Omar → Nour → Iona remains the
  right *dependency* order for deepening (each consumes the previous). Keep it.
- **Stage 2 — Add infra only as tiers arrive** (auth/quotas/queue/RLS when ~10 real users,
  then cohorts, exist).

In short: **keep "walking skeleton first" as a principle, but precede it with a
throwaway risk spike, and run the skeleton on the validated engine rather than stubs.**

---

## 5. Cost Notes

- **Testing cost is the near-term risk, not university scale.** A 3-engine A/B over a
  20-image hand-labelled set, re-run on every harness change, is the most expensive thing
  in the whole plan during development — and it is incurred by the solo owner, with no
  quota to stop it. The per-user quota mechanism (Vivek §5) **does not protect the
  developer**, who *is* the user. Mitigations the plan under-weights:
  - Hard **billing-account spend caps** on all four vendors (Google, Azure, Mistral,
    Anthropic), set before the first call. This is the real backstop.
  - **Result caching by image hash** (Nour §6.3) — pull forward so re-runs are free.
  - **Downscale/area cap before send** (Nour §6.1) — high-DPI A0 sheets are the costly
    inputs.
- **University-tier cost** scales with images × (1 OCR call + 1 Claude call). Claude with
  prompt caching (Iona §2) and batching-all-regions-per-drawing (Iona §3) is well
  designed and genuinely controls the LLM side. The uncontrolled variable is **OCR engine
  per-page price × large high-DPI sheets** — at cohort scale this dominates. The
  swappable interface preserving a self-host path (PaddleOCR / Azure Container) is the
  right long-term hedge (Nour §9.5), but is a Phase-3 concern, not now.
- **Cost-control gap:** no explicit per-job cost ceiling or "estimated cost before run"
  shown to anyone. Nour §6.2 mentions exposing an estimate to Vivek's quota gate, but
  with quotas deferred (rec #2) the estimate has no consumer. Recommend a simple global
  daily-spend kill-switch in the orchestrator regardless of quotas.

---

## 6. Remaining Plan Gaps / Contradictions

The contract freeze resolved the big ones (B1–B4, N1–N9). Cross-checking the **component
plans against the frozen `contracts.py`**, several plans still contain the *old, now-wrong*
shapes — Abdo §3 step 4 says each owner makes "the one-line edit to their plan," but those
edits have **not been made**. A solo dev reading a component plan today will be misled:

- **Zoriaz §2b still specifies the pre-freeze schema:** `source_text`, `translated_text`,
  `reading_order`, `ocr_confidence`, `bbox.width/height`, `is_rotated` +
  `rotation_angle_deg`, flat `image_width_px/height_px`, and status `processing`. Its
  §2b coordinate note still says bboxes are in **"natural pixel coordinate space of the
  stored image… not pre-processor output dimensions"** — the *exact* B1 defect Kian ruled
  against. Open Questions 1–6 (§9) are all already answered by the contract but still
  presented as open. **This plan directly contradicts the frozen contract and must be
  reconciled or it will mislead implementation.**
- **Solove §2.2/§4.1 still uses** `pending` status, `ocr_text`, `detected_lang`,
  `bbox_rotation`, nested `translation` object, and **bigint `job_id`** in the §4.1 wire
  example (`"job_id": 42`) — contradicting N2 (external UUID) and B2/B4. The §13 interface
  contract still lists `bbox{...rotation}` not `angle`.
- **Nour §2.2 / §10** still defines `bbox.width/height` (not `w/h`) and omits
  `region_index` + `low_confidence` from the emitted Region — the two fixes Kian assigned
  it. The contract has them; Nour's own plan doesn't yet.
- **Iona** does not emit `glossary_hit`/`canonical_term` in her §1 output spec (N5),
  uses `reason` strings (`translation_parse_error`, `ambiguous_source_text`,
  `short_fragment`) that **do not match the frozen `UncertainReason` enum**
  (`parse_error`, `ambiguous`, plus `translation_failed`, `unrecognized_domain_term`,
  `low_ocr_confidence`). The vocabularies must be reconciled — this is a real
  code-level mismatch, not cosmetic.
- **Vivek §1.3** still shows flat `image_url` and a `confidence` threshold of 0.70;
  the contract moved confidence ownership to Nour at 0.75. Vivek §2 partial-failure note
  ("`confidence: null`") conflicts with the frozen model where `confidence` is required
  and non-null (only `translation`/`translation_confidence` are nullable).

**Net:** the *frozen artifact is internally consistent and tests pass-shaped*, but **five
of seven component plans still describe the pre-freeze world.** For a solo dev these stale
docs are a trap. Either delete the superseded schema sections (the contract already says
it "supersedes the schema sections in every component plan") or annotate them. Given the
re-sequencing recommended above, the cleaner move is to treat `contracts.py` as the only
schema authority and stop maintaining the per-plan schemas at all.

**Other gaps:**
- **Testing strategy is sound in principle** (TDD, mocked engines, contract suite, golden
  outputs, accuracy harness) but is *heavy* for solo cadence and partly aspirational
  (golden-output Arabic translations require the test set that doesn't exist yet). Keep
  the contract smoke tests and the accuracy harness; relax the per-component TDD ceremony
  to "tests where they buy confidence."
- **Is CER ≤ 0.15 end-to-end measurable as defined?** Mostly. The metric is standard and
  the set is specified (≥20 drawings, ≥10 Arabic). Two soft spots: (a) "end-to-end" CER
  conflates OCR error and (for the translation view) is really an OCR-extraction metric —
  translation quality is *not* captured by CER at all, yet the MVP's value is the
  *translation*. There is no defined acceptance metric for translation correctness
  (golden-term match is mentioned but not gated). (b) CER depends on region-matching
  (greedy IoU, Nour §4.3); a region the OCR *misses entirely* (no bbox) is a deletion —
  ensure the harness counts missed regions, or CER will look artificially good on sparse
  detection. Recommend an explicit **recall/coverage** metric alongside CER.
- **`drawing_type` hint** (Iona) is "inferred by Vivek from OCR output" but no component
  owns that inference; it will silently default to "unknown." Minor, but unowned.
- **Inconsistent CER comparator** still lingers in prose: Omar §6.2 "CER < 0.15", Nour
  §4.2 "< 10%", contract "≤ 0.15 (gate) / <0.10 (internal)." The *contract* resolved it;
  the component plans didn't update. Same staleness issue as above.

---

## 7. What Is Genuinely Good (Do Not Change)

- **The modular, swappable stage pipeline.** This is the single best decision in the
  whole plan. It is what makes the OCR A/B possible, makes the recommended infra-cutting
  *safe* (you can add the queue/DB later without touching pipeline logic), and de-risks
  the Phase-2/3 expansion. Keep the typed `Protocol`/Pydantic seams.
- **`tests/contracts/contracts.py` as a single source of truth.** Clean, well-documented,
  ownership annotated, smoke-tested, and it round-trips the canonical example. This is
  exactly the right artifact; it should *replace* the per-plan schemas, not coexist.
- **Feature-level YAGNI discipline.** Phases 4–5 demand-gated, DWG deferred, building-code
  *text* explicitly not reproduced (the legal caveat is correct and important), any-to-any
  language deferred. This judgement is excellent — it just needs to be applied to infra too.
- **The curated glossary as the moat,** and Iona's glossary-injection + prompt-caching +
  batch-per-drawing design. The caching/batching is cheap to keep from day one and
  genuinely controls LLM cost. The miss-driven glossary growth loop is a real
  differentiator.
- **Naming Arabic OCR as the central risk, and Nour's escalation path** (pre-proc →
  ensemble → fine-tune PaddleOCR). The *analysis* of the risk is correct and thorough —
  the only fix needed is to *act on it first* rather than last.
- **The honest framing of the product** as a learning/reference aid with visible
  confidence flags, not a certified source. Correct for trust and liability.
- **Omar's Arabic-specific pre-processing reasoning** (diacritics, fine strokes, adaptive
  threshold block size) is domain-aware and correct — it just shouldn't all be built
  before the spike proves which steps move CER.

---

### One-line bottom line
The plan is intellectually strong and architecturally sound, but it is sequenced and
sized for a funded team building for universities, not a solo dev proving an idea —
**spike the Arabic OCR first, cut Phase-1 infra to Tier-0, and ship the thin slice.**
