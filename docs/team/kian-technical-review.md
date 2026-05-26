# Kian — Technical Review of Phase-1 Component Plans

**Author:** Kian (Technical Expert / Architect)
**Date:** 2026-05-26
**Reviewed:** spec (`docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`), `docs/team/TEAM.md`, and all 7 component plans (Zoriaz, Vivek, Omar, Nour, Iona, Matt, Solove)
**Status:** Independent architecture review — blocking issues must be resolved before implementation

---

## 1. Verdict

**NOT buildable as-is. Conditionally approvable once the cross-component data
contract is unified.** The architecture is fundamentally sound — the staged,
swappable pipeline is honoured, the async job model is well-reasoned, and the
tech choices are consistent and justified. The plans are individually strong.

But the seven plans were written **in isolation against an under-specified §3
interface**, and they have **diverged on the single most important shared
artifact: the Region/result schema and its coordinate space.** Today, no two
plans agree on field names, and there is one **high-severity coordinate-space
defect** (`B1`) that, if shipped, makes every overlay and click-to-locate
highlight misalign. These are cheap to fix on paper and ruinous to fix after
code exists.

Decision: freeze the canonical contract in §2 below, resolve the four blocking
issues in §3, then green-light implementation. The contract must be owned by
**one author (Vivek's Pydantic models in `tests/contracts/`)** and consumed
verbatim by everyone.

---

## 2. The Canonical Cross-Component Data Contract (AUTHORITATIVE)

This supersedes the schema in every component plan. Vivek owns these as
Pydantic models; Nour, Iona, Solove, and Zoriaz import/mirror them. Any change
requires a version bump and Kian+Abdo sign-off.

### 2.1 Coordinate space (THE binding decision)

**All bboxes are stored and transmitted in PRE-PROCESSED (post-Omar) image
pixel space**, top-left origin, x→right, y→down, absolute pixels. The frontend
**displays the pre-processed image** (`image.processed_url`), NOT the original
upload, so overlays align without any client-side transform.

The original upload is retained (Solove `image_refs.original_key`) but is
**not** the display surface in Phase 1.

### 2.2 The `Region` object (internal — Nour → Iona → Solove)

| Canonical field | Type | Owner writes | Replaces these divergent names |
|---|---|---|---|
| `text` | `str` (UTF-8) | Nour | Zoriaz `source_text`, Solove `ocr_text` |
| `bbox.x` | `float` px | Nour | left edge, pre-processed space |
| `bbox.y` | `float` px | Nour | top edge |
| `bbox.w` | `float` px | Nour | Zoriaz `bbox.width` |
| `bbox.h` | `float` px | Nour | Zoriaz `bbox.height` |
| `bbox.angle` | `float` deg CW | Nour | **single rotation field.** Zoriaz `is_rotated`+`rotation_angle_deg`, Solove `bbox_rotation`. `0.0` = upright; no separate boolean |
| `confidence` | `float [0,1]` | Nour | Zoriaz `ocr_confidence`, Solove `ocr_confidence` |
| `lang` | `str \| null` (BCP-47) | Nour | Solove `detected_lang`. **Never omitted; null if undetected** |
| `region_index` | `int` (0-based) | Nour | **single ordering field.** Zoriaz `reading_order`. Assigned in document order |
| `translation` | `str \| null` | Iona | Zoriaz `translated_text` (flat), Solove nested `translation.translated_text`. Null on partial failure |
| `translation_confidence` | `float [0,1] \| null` | Iona | null if not provided (see B3) |
| `uncertain` | `bool` | Iona | true if any uncertainty source fires |
| `uncertain_reason` | `str \| null` | Iona | controlled vocabulary (Iona §4) |

### 2.3 The wire/API result object (Vivek/Solove → Zoriaz)

`GET /api/v1/jobs/{job_id}/results` (status `done` only):

```json
{
  "job_id": "string (UUID)",
  "status": "done",
  "src_lang": "en",
  "tgt_lang": "ar",
  "image": {
    "processed_url": "string (signed URL, PRE-PROCESSED image)",
    "width": 3508,
    "height": 2480
  },
  "regions": [
    {
      "region_id": "string",
      "region_index": 0,
      "text": "reinforced concrete slab",
      "lang": "en",
      "confidence": 0.97,
      "bbox": { "x": 412, "y": 88, "w": 340, "h": 28, "angle": 0.0 },
      "translation": "بلاطة خرسانة مسلحة",
      "translation_confidence": 0.94,
      "low_confidence": false,
      "uncertain": false,
      "uncertain_reason": null,
      "glossary_hit": true,
      "canonical_term": "reinforced concrete"
    }
  ],
  "stats": { "region_count": 67, "low_confidence_count": 5, "glossary_hit_rate": 0.72 }
}
```

Mandated decisions baked in above:
- `image.{processed_url,width,height}` is the **canonical image block** (adopts
  Solove's nested shape; replaces Zoriaz's flat `image_url` +
  `image_width_px`/`image_height_px` and Vivek's flat `image_url`). The URL
  field is **`processed_url`** to make the coordinate space explicit.
- `translation` is **flat** on the region (Zoriaz/Iona style), NOT nested in a
  `translation` sub-object (Solove). Solove may store it relationally; the API
  flattens it. The Phase-2 multi-language case becomes `translations: [...]` —
  a versioned change, not Phase 1's problem.
- `low_confidence` (boolean, pre-computed) **and** `confidence` (raw float)
  **both** cross the boundary — see B3.

### 2.4 Job status object (Vivek → Zoriaz)

Status enum is **frozen** to: `queued | preprocessing | ocr | translating |
done | failed`. (Solove's `pending` and Zoriaz's `processing` are eliminated —
see B4.) `GET /api/v1/jobs/{job_id}` returns `{job_id, status, created_at,
updated_at, src_lang, tgt_lang, stage_detail?, error?}`.

---

## 3. Blocking Issues (must fix before coding)

### B1 — COORDINATE-SPACE CONTRADICTION (HIGHEST RISK)

**Zoriaz's plan (§2b, §4) consumes bboxes in "natural pixel coordinate space
of the stored image" and loads `image_url` = "the original image." Omar
deskews AND upscales (Steps 5/6), producing a DIFFERENT coordinate space. Nour
(§2.2) and Solove (§3) correctly store bboxes in pre-processed space.** If
Zoriaz displays the original upload while bboxes are in pre-processed pixels,
**every highlight and Phase-2 overlay is offset and scaled wrong** — the core
feature silently breaks. Zoriaz's own Risk table flags this as Medium/High and
its Open Question 2 even asks for confirmation; the answer baked into the plan
("not normalised, not pre-processor output dimensions") is the **wrong** one.

**Ruling:** Bboxes live in **pre-processed image space** (per Nour/Solove). The
frontend MUST render `image.processed_url` (the post-Omar image) and use
`image.width`/`image.height` from the same results payload for its
`viewportX = bbox.x / image.width` conversion. Zoriaz §2b and §4 must be
rewritten to consume `processed_url` and the nested `image` block. Solove must
guarantee processed width/height are populated from Omar's output and returned
as `image.width/height`. Omar's Open Question Q1 is hereby answered: **store
both images; display the processed one.**

### B2 — REGION/RESULT FIELD-NAME DIVERGENCE

Three incompatible schemas exist for the same object:
- text: `source_text` (Zoriaz) vs `text` (Nour/Vivek/Iona) vs `ocr_text` (Solove)
- order: `reading_order` (Zoriaz) vs `region_index` (Solove)
- translation: flat `translated_text` (Zoriaz) vs nested `translation.*` (Solove) vs `translation` (Vivek/Iona)
- confidence: `ocr_confidence` (Zoriaz/Solove) vs `confidence` (Nour/Vivek)
- language: `lang` (Nour/Iona) vs `detected_lang` (Solove)
- rotation: `is_rotated`+`rotation_angle_deg` (Zoriaz) vs `angle` (Nour) vs `bbox_rotation` (Solove)
- bbox dims: `width/height` (Zoriaz) vs `w/h` (Nour/Solove)

**Ruling:** Adopt §2.2/§2.3 canonical names verbatim:
`text, bbox{x,y,w,h,angle}, confidence, lang, region_index, translation,
translation_confidence, uncertain, uncertain_reason`. **One rotation field
(`bbox.angle`), no boolean.** **`w`/`h`, not `width`/`height`.** Nour's Task 1
("freeze Region schema; all downstream confirm") is the gating task for the
whole team — it must use these exact names.

### B3 — CONFIDENCE OWNERSHIP & THRESHOLD CONFLICT

Five different threshold regimes: Zoriaz two-tier 0.60/0.40; Nour 0.75; Iona
0.60 (and 0.75 for Arabic); Vivek default 0.70; Solove a single pre-computed
boolean. The flag a user sees currently depends on which component you ask.

**Ruling:**
1. **Raw `confidence` (float) is canonical and ALWAYS crosses every boundary.**
   No component may discard it.
2. **The OCR adapter (Nour) owns the OCR low-confidence threshold** — it is the
   only stage that calibrates against the benchmark test set. It computes
   `low_confidence: bool` once (default 0.75, calibrated) and that boolean is
   persisted by Solove and returned on the wire.
3. **Iona owns `uncertain`/`uncertain_reason`** (a distinct signal: OCR
   low-confidence OR LLM uncertainty OR parse error). Iona's Arabic-specific
   0.75 logic stays, but it sets `uncertain`; it does NOT redefine
   `low_confidence`.
4. **Zoriaz's two-tier 0.60/0.40 is PRESENTATION ONLY** — it styles using the
   raw `confidence` float it now always receives. The frontend never owns the
   authoritative flag. Zoriaz's "thresholds do not belong in the API contract"
   is correct for *styling tiers*, wrong for the *authoritative low-confidence
   flag* — that one is owned upstream.

Both a boolean (`low_confidence`, authoritative) and the raw score
(`confidence`, for presentation gradients) cross the boundary. Iona's Open
Question 4 (boolean vs float) is resolved: keep the boolean authoritative;
carry the float too.

### B4 — JOB STATUS ENUM DIVERGENCE

Zoriaz: `queued|processing|done|failed`. Vivek:
`queued|preprocessing|ocr|translating|done|failed`. Solove:
`pending|preprocessing|ocr|translating|done|failed`. A frontend written
against `processing` mishandles Vivek's granular states, and Solove's `pending`
initial state never matches Vivek's `queued`.

**Ruling:** Freeze to **`queued | preprocessing | ocr | translating | done |
failed`** (Vivek's — the orchestrator owns lifecycle). Solove changes its enum
`pending`→`queued`. Zoriaz treats any of `preprocessing|ocr|translating` as its
single "processing" spinner state but must not hardcode a literal
`"processing"` value.

---

## 4. Non-Blocking Recommendations

- **N1 — Endpoint prefix.** Vivek uses `/api/v1/...`; Zoriaz/Solove use
  `/api/...` / `/jobs/...`. Standardize on **`/api/v1`** everywhere.
- **N2 — ID type.** Solove uses `bigint` identity job IDs; Zoriaz/Vivek assume
  UUID strings. **Use UUIDs for the externally exposed `job_id`** (non-
  enumerable, tenant-safe in signed URLs, matches Vivek). Internal bigint PKs
  are fine. Reconcile Solove §2.
- **N3 — DZI tiling is unowned.** Zoriaz assumes a DZI/IIIF tile endpoint;
  Vivek/Solove never commit to generating tiles. **For Phase 1, drop tiling**
  (YAGNI): cap upload at 10 MP and serve `processed_url` directly. Revisit in
  Phase 2 if large-image perf is proven a problem; otherwise assign tile
  generation explicitly to Vivek with a task.
- **N4 — Glossary→Translator field mismatch.** Iona consumes `GlossaryEntry`
  with `.src_term/.tgt_term/.context`; Matt's bulk-fetch returns
  `term/translation/synonyms/domain`. Align on one shared `GlossaryEntry`
  model. Confirm Vivek fetches the glossary snapshot once per job and passes it
  in (Iona OQ2 — agreed; prevents mid-job cache staleness).
- **N5 — `glossary_hit`/`canonical_term` provenance.** Vivek's results include
  these; Iona currently emits only translation+uncertainty. Add them to Iona's
  output contract.
- **N6 — Accuracy targets conflict.** Omar targets **CER < 0.15**; Nour targets
  **CER < 0.10**. One number, one shared test set: recommend **single hand-
  labelled set (owned by Abdo, format by Omar/Nour), Phase-1 acceptance
  CER ≤ 0.15 end-to-end**, with Nour's <0.10 as an internal engine-selection
  goal. bbox IoU > 0.70 and rotation error < 5° (Nour) are Phase-2-overlay
  gates only. Omar's acceptance harness must use the *selected* engine, not
  Tesseract (Tesseract only for relative ablation).
- **N7 — Translator model id.** Iona specifies `claude-sonnet-4-6`; Solove's
  example stores `claude-3-5-sonnet-20241022`. Store the actual runtime model
  id in `translations.translation_engine`; don't hardcode in schema docs.
- **N8 — Partial-failure shape.** Vivek's "translate partial fail → done with
  `translation=null`" is now reflected: `translation` is nullable on the wire,
  and add `"translation_failed"` to Iona's `uncertain_reason` vocabulary.
- **N9 — Multi-region term assembly.** Nour §9.3, Iona OQ5, and Matt R2 all
  independently raise OCR splitting multi-word terms across regions. Assign one
  owner (Nour: optional merge of adjacent same-line short regions) rather than
  three plans hedging.

---

## 5. Per-Component Notes

**Zoriaz (Frontend) —** Strong UI/a11y/TDD plan. **Must change:** display
`processed_url`, not the original (B1); adopt canonical field names incl.
`w/h`, `text`, `region_index`, flat `translation`, single `bbox.angle` (B2);
treat confidence tiers as presentation over the raw float (B3); spinner over
the granular status enum (B4). Drop DZI dependency for Phase 1 (N3). Phase-2
overlay hooks (mode prop, forward-compatible schema) are well done and
correctly reuse the same `bbox`.

**Vivek (Backend) —** Excellent spine. Async model, state machine, partial-
failure handling, swappable DI stages, and the shared `tests/contracts/` suite
are exactly right — **make that suite the single source of the Pydantic models
enforcing B2.** `image_url` here is already correctly the *normalized* image —
just rename to `processed_url` and nest under `image`. RQ-over-Celery with a
documented migration path is the correct YAGNI call. Resolve OQ4 (normalized
format/DPI) WITH Omar before Solove schemas regions — a real ordering
dependency.

**Omar (Pre-processor) —** Thorough, Arabic-aware, measurable. The deskew+
upscale steps create the coordinate space B1 hinges on — **Omar must emit and
persist the output image dimensions** so Solove fills `image.width/height`.
Answer OQ1 here: **persist BOTH original and processed; processed is the
display + bbox space.** The 2x upscale cap vs Nour's "≥300/400 DPI" expectation
(Nour §5.1, R9.7) may conflict on very low-res inputs — Omar and Nour must
agree the DPI floor. CER target reconcile per N6.

**Nour (OCR Adapter) —** The §2.2 schema is the closest to correct and is the
**base** for the canonical Region (already `text/bbox{x,y,w,h,angle}/
confidence/lang`, absolute pre-processed pixels). Two fixes: (1) add
`region_index` to the emitted Region (ordering owner); (2) Nour owns the
`low_confidence` boolean computation (B3). Engine A/B harness, IoU/rotation
metrics, and ensemble fallback are excellent and de-risk the central Arabic
problem properly. Keep §9.1 escalation path visible to Abdo.

**Iona (Translator) —** Best-in-class prompt/caching design; breakpoint
placement and determinism approach are correct. **Must change:** align input
`GlossaryEntry` field names with Matt (N4); emit `glossary_hit`/
`canonical_term` (N5); map Claude's internal JSON `id` back to canonical
`region_id` and emit `translation` (not a competing keyed object). Confirm she
sets `uncertain`, never `low_confidence` (B3). `output_config:{"effort":"low"}`
is a reasonable determinism choice.

**Matt (Glossary) —** Solid, well-normalized schema; Arabic normalisation rules
and partial indexes follow Postgres best practice. Leaf-node dependency posture
is correct. Cross-component action: publish the **canonical `GlossaryEntry`
shape** Iona consumes (term, translation, synonyms, domain, context?) so N4 is
closed. R1 (Arabic presentation-form codepoints from real OCR) is a genuine
risk — test against Nour's actual output before seeding.

**Solove (Result Store) —** Strong relational design, correct object-storage
split, sound RLS with the `(select auth.uid())` performance pattern, and a
single-round-trip glossary query. **Must change:** rename to canonical
(`ocr_text`→`text`, `detected_lang`→`lang`, `bbox_rotation`→`angle`, nested
`translation` object → flat on the wire) (B2); enum `pending`→`queued` (B4);
external `job_id` to UUID (N2). Solove already correctly identifies the two
HIGH risks (bbox convention + processed-image space) in §12 — this review rules
in his favour on both; he and Zoriaz must now agree. Character-level bbox
deferral is correct YAGNI.

---

## 6. Risks & Gaps Summary

- **Arabic OCR remains the central risk** (spec §1, Nour §9.1) — correctly
  owned and benchmark-gated; ensure the escalation path (pre-proc → ensemble →
  fine-tune PaddleOCR) is visible to Abdo before engine selection.
- **Shared test set is referenced by 4 plans but owned by none** — Abdo must
  assign collection/curation explicitly (Omar OQ3); one set, one CER number
  (N6).
- **Multi-region term fragmentation** is triple-hedged and unowned (N9).
- **YAGNI watch:** DZI tiling (N3), webhooks, multi-page PDF, char-level boxes,
  dataset-level glossary versioning — all correctly deferred; keep them out of
  Phase 1.
- **No scope creep into Phase 2+** detected beyond well-marked, inert hooks.
  Legal caveat (no full code text reproduction) is respected.
