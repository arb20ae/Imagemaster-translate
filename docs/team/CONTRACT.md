# Frozen Canonical Contract — Phase 1

**Status:** FROZEN ✅ (2026-05-26). Ratified by Kian (technical) + Abdo (PM) + Lead.
**Code source of truth:** [`tests/contracts/contracts.py`](../../tests/contracts/contracts.py)
**Supersedes:** the schema sections in every `docs/components/*` plan.

This document is the human-readable companion to the Pydantic models. The models
are authoritative; this page records the decisions and the resolved open questions
so the freeze is complete. **Any change requires a version bump + Kian/Abdo sign-off.**

---

## 1. Rulings adopted (from Kian's technical review)

| Ruling | Decision | Encoded as |
|--------|----------|-----------|
| **B1 — coordinate space** | Bboxes live in **pre-processed image pixel space**; frontend displays `image.processed_url`. | `BBox` + `ImageRef`, module docstring |
| **B2 — field names** | One canonical schema; `w`/`h` (not width/height); single `bbox.angle` (no `is_rotated`); flat `translation`; `text`, `region_index`, `lang`. | `Region`, `ResultRegion` |
| **B3 — confidence** | Raw `confidence` always transmitted; `low_confidence` bool owned by **Nour**; `uncertain`/`uncertain_reason` owned by **Iona**; frontend tiers are presentation-only. | `Region`, `ResultRegion`, `UncertainReason` |
| **B4 — status enum** | Frozen to `queued / preprocessing / ocr / translating / done / failed`. | `JobStatus` |
| **N1 — API prefix** | `/api/v1` everywhere. | (backend) |
| **N2 — id type** | External `job_id` is a UUID string; internal PKs may be bigint. | `str` job ids |
| **N4 — glossary shape** | Shared `GlossaryEntry` (`src_term, tgt_term, src_lang, tgt_lang, domain, synonyms, context, version`). | `GlossaryEntry` |
| **N5 — provenance** | Iona emits `glossary_hit` + `canonical_term`. | `Region`, `ResultRegion` |
| **N8 — partial failure** | `translation` is nullable; `uncertain_reason` includes `translation_failed`. | models |

## 2. Resolved open questions (the freeze items)

### 2.1 Normalized-image format & DPI floor (Omar + Vivek — was a real ordering dependency)
**Decision:**
- Pre-processor target resolution is **300 DPI**; upscaling is capped at **2×** to
  avoid inventing detail.
- If effective DPI after the 2× cap is still **< 200 DPI**, the image is processed
  anyway but Omar sets a per-image **`low_res_warning`** in the job metadata so the
  user is told OCR quality may be poor. (This is job-level metadata, not a per-region
  field — it does not change the `Region` schema.)
- Output image format is **PNG** (lossless; preserves thin linework better than JPEG).
- Omar **persists the processed image dimensions**, which Solove returns as
  `image.width` / `image.height`. This is what makes B1 safe.

### 2.2 Glossary consumption (Matt + Iona — N4)
**Decision:** Vivek fetches the glossary **snapshot once per job** (filtered by
language pair, optionally by domain) and passes it into Iona, preventing mid-job
cache staleness. Iona builds an in-memory map keyed by normalized `src_term`. The
shared shape is `GlossaryEntry` (above).

### 2.3 Multi-region term fragmentation (N9 — assigned)
**Owner: Nour.** Optional merge of adjacent, same-line, short OCR regions before
emitting `Region`s, so multi-word terms (e.g. "damp-proof course") are not split.
Off by default; enabled once measured against the test set.

## 3. Accuracy bar (one number, one set — N6)
- **Phase-1 acceptance:** end-to-end **CER ≤ 0.15** on the shared Arabic test set,
  using the *selected* OCR engine.
- Nour's **CER < 0.10** is an internal engine-selection goal (not the gate).
- **bbox IoU > 0.70** and **rotation error < 5°** are **Phase-2 overlay** gates only.
- Shared test set owned by **Abdo** (curation), format by **Omar + Nour**.

## 4. YAGNI — deferred out of Phase 1 (confirmed)
DZI/IIIF tiling (cap uploads at 10 MP, serve `processed_url` directly), webhooks,
multi-page PDF, character-level boxes, dataset-level glossary versioning, and all
Phase 2+ features (overlay, building codes) beyond inert, marked hooks.

## 5. Sign-off
- **Kian (Technical):** contract matches review §2; B1–B4 encoded. ✅
- **Abdo (PM):** owners assigned, accuracy bar single-sourced, YAGNI held. ✅
- **Lead:** authored as single source of truth; smoke tests added. ✅

**Gate status: GREEN for implementation.** Next artifact: the walking-skeleton
implementation plan (`writing-plans`).
