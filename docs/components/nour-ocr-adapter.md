# OCR Adapter — Phase 1 Plan

**Component:** OCR Adapter
**Owner:** Nour
**Date:** 2026-05-26
**Spec ref:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md` §3, §4, §9
**Interface provided:** `OcrEngine.extract(image) -> [Region{text, bbox, confidence, lang}]`
**Interface consumed:** `PreProcessor.process(image) -> normalized_image` (from Omar)
**Downstream consumers:** Iona (Translator), Solove (Result Store), Zoriaz (Frontend overlay, Phase 2)

---

## 1. Scope and Central Risk

Arabic OCR on scanned/photographed architectural drawings is the project's stated central
technical risk. Arabic is cursive, right-to-left, and context-dependent in letter form.
Architectural drawings compound this with: tiny annotation text (often 1.5–3 mm in the
original), dense linework overlapping text, text rotated at arbitrary angles (dimension
lines, section callouts), and mixed-language blocks (EN title block + AR body notes, or
vice versa).

This plan designs an adapter that:
1. Hides ≥2 OCR engine implementations behind one interface so any engine can be swapped
   or run in parallel without touching downstream code.
2. Runs a systematic benchmark against a hand-labelled Arabic real-drawing test set to
   pick the best engine before committing.
3. Defines the exact Region output contract so Iona and Solove can build against a stable
   schema from day one.

---

## 2. Adapter Abstraction

### 2.1 Interface contract

```
OcrEngine.extract(image: NormalizedImage) -> list[Region]
```

`NormalizedImage` is whatever Omar's pre-processor returns (assumed: a decoded image
buffer with known DPI, orientation corrected, contrast normalized). The adapter does NOT
do pre-processing — that is Omar's stage.

The adapter MAY call the engine once per image or tile the image for dense drawings (see
§5). Tiling is an internal implementation detail; callers always receive a single flat
list of Regions.

### 2.2 Region schema (exact, normative)

Every downstream consumer (Iona's translator, Solove's result store, Zoriaz's overlay)
depends on this schema. It must not change without a version bump and team agreement.

```
Region {
  text:        string          -- raw OCR text, preserved encoding (UTF-8); RTL Arabic included as-is
  bbox:        BoundingBox     -- see below
  confidence:  float           -- range [0.0, 1.0]; 1.0 = highest confidence
  lang:        string | null   -- BCP-47 language tag e.g. "ar", "en", "ar-SA", null if undetected
}

BoundingBox {
  x:      float   -- left edge, pixels from image left, in input-image coordinate space
  y:      float   -- top edge,  pixels from image top
  width:  float   -- pixel width  of the region
  height: float   -- pixel height of the region
  angle:  float   -- rotation in degrees clockwise from horizontal; 0.0 for upright text
}
```

Coordinate convention: origin (0, 0) is top-left of the image as received from Omar's
pre-processor (after deskew/normalize). All values are in pixels at the normalized image
resolution. Downstream consumers that need percentages or ratios must compute them from
the known image dimensions — the Region itself always uses absolute pixels.

Confidence is normalised to [0.0, 1.0] regardless of what the underlying engine returns.
Engines that return a 0–100 integer score are divided by 100. Engines that return
character-level scores are averaged to word/region level. The threshold for flagging a
region as low-confidence (surfaced to the user as a review flag) is provisionally 0.75;
this threshold is configurable and will be calibrated against the benchmark test set.

`lang` is null only when the engine does not attempt language detection. It is never
omitted from the object. This lets Iona check `if region.lang is None` cleanly.

`angle` is 0.0 for horizontal text. A region rotated 90° clockwise (common for dimension
annotations on the left edge of a drawing) has angle=90.0. The adapter normalises engine-
specific rotation representations to this convention.

### 2.3 Plug-in pattern

Each engine is one concrete class implementing the same abstract base:

```
AbstractOcrEngine (abstract)
  extract(image) -> list[Region]    # must be implemented

GoogleDocumentAiEngine(AbstractOcrEngine)
AzureDocumentIntelligenceEngine(AbstractOcrEngine)
MistralOcrEngine(AbstractOcrEngine)
```

A factory function or config key selects the active engine at startup. No conditional
branching in the pipeline — callers always see `OcrEngine.extract()`.

An `EnsembleEngine` can wrap two engines and merge results (for A/B testing or confidence
boosting); it implements the same interface.

---

## 3. Engine Candidates — Comparison

### 3.1 Google Document AI (Form Parser / General OCR processor)

| Dimension | Detail |
|-----------|--------|
| Arabic script support | Yes; production-grade Arabic OCR, trained on diverse document types |
| BBox quality | Word-level and paragraph-level bboxes; polygon coordinates available |
| Rotation handling | Auto-detects page orientation; word-level rotation angles in newer processors |
| Dense-text/drawings | General processor handles mixed text+graphics; Layout processor adds structure |
| Language detection | Per-page and per-paragraph language hints |
| Latency | ~2–8 s for a full A1-size drawing page (synchronous); async batch available |
| Price (2026) | ~$1.50 / 1000 pages (General OCR); Layout processor higher; check current pricing |
| Self-host option | No (managed cloud only) |
| Key risk for this project | Pricing on large architectural images (high DPI = large file); rotation precision for angled annotations |

### 3.2 Azure Document Intelligence (Read model / Layout model)

| Dimension | Detail |
|-----------|--------|
| Arabic script support | Yes; strong Arabic support including handwritten Arabic in newer models |
| BBox quality | Word-level polygons (not just axis-aligned rects); explicit angle per word |
| Rotation handling | Explicitly returns `angle` field per word — directly maps to our BBox.angle |
| Dense-text/drawings | Layout model separates text from tables/figures; useful for title-block parsing |
| Language detection | Per-page detected language list |
| Latency | ~3–10 s synchronous; async for large files |
| Price (2026) | ~$1.50 / 1000 pages (Read); Layout higher; check current pricing |
| Self-host option | Azure Container (preview); viable if data-privacy required |
| Key risk for this project | Arabic RTL text order in returned words needs verification against real drawings |

### 3.3 Mistral OCR (mistral-ocr-latest via API)

| Dimension | Detail |
|-----------|--------|
| Arabic script support | Claims strong multilingual support including Arabic; newer entrant — less production-proven |
| BBox quality | Returns markdown/structured text with bounding boxes; format is newer and less standardised |
| Rotation handling | Less documented; angle handling for rotated annotations unverified at planning time |
| Dense-text/drawings | Designed for document OCR; drawing-specific dense-text handling unverified |
| Language detection | Mixed; may not always return per-region language codes |
| Latency | Varies; API-based |
| Price (2026) | Competitive; check current pricing against Document AI and Azure |
| Self-host option | No (API only at planning time) |
| Key risk for this project | Immature bbox/rotation spec for architectural drawings; Arabic accuracy on real drawings unverified |

### 3.4 Selection strategy

No engine is selected by declaration. The benchmark harness (§4) runs all three on the
real-drawing test set and selects the primary engine by: (1) Arabic character accuracy,
(2) bbox IoU, (3) rotation correctness, in that priority order. Cost and latency are
secondary tie-breakers.

Working hypothesis going into the benchmark: Azure Document Intelligence is strongest on
rotated Arabic word bboxes due to its explicit per-word angle field; Google Document AI
is strongest on overall Arabic character accuracy due to training corpus size. Both are
tested. Mistral OCR is included as a low-cost challenger to validate or falsify its
Arabic claims.

---

## 4. Benchmark Harness

### 4.1 Test set

A hand-labelled Arabic real-drawing test set must exist before any engine is claimed to
"work." Requirements for the test set:

- Minimum 10 unique drawing sheets (target 20+), sourced from real Gulf/MENA construction
  drawings (scanned or photographed, not synthetic).
- Mix of: high-quality scans, phone-photograph images (lower quality, lens distortion),
  drawings with dense annotations, drawings with rotated dimension text, drawings with
  mixed EN+AR content, drawings with printed AND handwritten annotations if available.
- Each test image is labelled with ground-truth Regions: exact text (UTF-8), exact bbox
  (x, y, width, height, angle), and detected language. Labels stored as JSON matching
  the Region schema in §2.2.
- Labelling protocol: at least two independent labellers per image with an adjudication
  pass for disagreements. Character-level agreement, not just word-level.

Test set is versioned in object storage (not committed to Git due to image size). A
manifest file in the repo references the test set version.

### 4.2 Metrics

| Metric | Definition | Target (provisional) |
|--------|------------|----------------------|
| CER (Character Error Rate) | Edit distance / ground-truth char count, per region, averaged | < 10% on Arabic regions |
| WER (Word Error Rate) | Word-level equivalent of CER | < 15% on Arabic regions |
| BBox IoU | Intersection-over-Union of predicted bbox vs ground-truth bbox | > 0.70 average |
| Rotation error | \|predicted angle - ground-truth angle\| in degrees | < 5° average |
| Language detection accuracy | % regions with correct BCP-47 lang tag | > 90% |
| Latency | Wall-clock time per drawing image (end-to-end engine call), p50/p95 | p50 < 10 s |
| Cost per image | API cost at list price for one A1 drawing image at 300 DPI | Tracked; budget TBD |

CER is the primary accuracy metric. WER is secondary. IoU and rotation error gate Phase-2
overlay correctness. Language detection accuracy gates Iona's per-region language routing.

Metrics are computed separately for: (a) Arabic-only regions, (b) English-only regions,
(c) mixed-language regions, (d) rotated regions (angle > 5°), (e) dense regions (bbox
area / image area > threshold).

### 4.3 Harness design

The harness is a standalone Python script (no production dependencies) that:
1. Loads test images and ground-truth JSON from object storage.
2. For each engine under test, calls `engine.extract(image)` and records results + timing.
3. Matches predicted Regions to ground-truth Regions by bbox IoU (greedy max match).
4. Computes all metrics in §4.2 and writes a JSON/CSV results file.
5. Prints a per-engine summary table to stdout.

The harness is idempotent and reproducible: same test set + same engine version = same
numbers. Engine API versions are pinned in a harness config file.

---

## 5. Handling Dense, Tiny, Rotated, and Mixed-Language Annotations

### 5.1 Dense / tiny text

Architectural drawings often have annotation text at 1.5–3 mm original height. At 300 DPI
this is only ~18–35 pixels tall — near the lower bound for reliable OCR. Mitigations:

- Require Omar's pre-processor to normalise to at least 300 DPI before the image reaches
  the adapter. 400 DPI preferred for Arabic script.
- For images where the adapter detects very low confidence across many regions (average
  confidence < 0.60), re-request at a higher resolution crop if the original allows it,
  or flag the entire job as requiring human review.
- Tiling: for A0/A1 drawings at 300 DPI (image width > 4000 px), split into overlapping
  tiles (50 px overlap), run OCR per tile, then merge and de-duplicate Regions by IoU.
  Tiling is an internal implementation detail; the caller receives a flat list.

### 5.2 Rotated text

Dimension lines and section callouts are frequently at 90° or arbitrary angles. Engines
that do not handle rotation (e.g., returning a bbox that clips the rotated text without
the angle field) will produce low-confidence or empty results.

Mitigation: the adapter checks if `angle != 0` in the engine's raw response. If an engine
does not return angle information, the adapter runs a lightweight angle-detection pass
(e.g., using the aspect ratio and text-line direction from the bbox vertices) and
populates `bbox.angle` from that inference, with a lower confidence penalty applied.

### 5.3 Mixed-language drawings

A drawing may have an Arabic annotation next to an English dimension, or an English title
block with Arabic notes. The engine must return per-region language codes, not just a
per-page language. The adapter validates that `region.lang` is populated for every region;
if the engine returns only a page-level language, the adapter assigns it to all regions
from that page and logs a warning.

### 5.4 Handwritten annotations

Some scanned drawings include handwritten Arabic notes. Handwritten Arabic OCR is
significantly harder than printed. For Phase 1, the adapter does not attempt to
specifically improve handwritten results, but it does:
- Flag regions where the engine returns very low confidence (< 0.50) as potentially
  handwritten in the Region metadata (an optional `hints` field may be added post-MVP).
- Record these as a separate metric bucket in the benchmark to understand the gap.

---

## 6. Cost Controls

API-based OCR is charged per page or per unit of data processed. A high-DPI A0 drawing
can be several megabytes, and costs can add up quickly at scale.

Mitigations built into the adapter:

1. **Resolution cap before API call:** The adapter resizes any image above a configured
   maximum pixel area (default: 4096 × 4096 px = ~16 MP) to that maximum before sending
   to the API. This is a last-resort cap; Omar's pre-processor should already have
   normalised resolution. The cap is configurable per environment.

2. **Per-user quota integration:** The adapter exposes an estimated cost before making
   the API call (based on image size and known per-unit pricing). The API/BE layer
   (Vivek) checks this against the user's quota before invoking the adapter.

3. **Caching:** OCR results for identical image hashes are cached. If the same drawing
   is submitted twice (or two tiles are identical), the cached result is returned.
   Cache TTL is configurable; default 24 hours.

4. **Async / batching:** For bulk jobs, the adapter queues requests and uses the engine's
   async/batch API where available (Google Document AI and Azure both offer batch
   endpoints at the same or lower per-unit price with higher throughput).

5. **Engine tier selection:** A "cheap mode" config flag routes to the most cost-effective
   engine for a given job (e.g., Mistral OCR if it proves accurate enough and cheaper).

---

## 7. TDD and Testing Approach

### 7.1 Unit tests — mock engines

Unit tests never call a live API. Each engine implementation has a corresponding mock
that returns pre-canned Region lists from fixture files (JSON matching the Region schema).

```
tests/
  fixtures/
    google_docai_response_ar_sample.json   -- raw API response for a known test image
    azure_docint_response_ar_sample.json
    mistral_ocr_response_ar_sample.json
  unit/
    test_google_engine.py    -- patches the API client; verifies Region mapping
    test_azure_engine.py
    test_mistral_engine.py
    test_region_schema.py    -- validates Region objects: types, ranges, required fields
    test_bbox_normalisation.py  -- tests pixel coords, angle conversion
    test_confidence_normalisation.py
    test_tiling_merge.py     -- tests tile-split + Region de-duplication logic
  integration/
    test_engine_live.py      -- skipped unless env var LIVE_OCR_TESTS=1 set
  benchmark/
    run_benchmark.py         -- the harness (§4); not a pytest test, run separately
```

### 7.2 Contract tests

A contract test suite verifies that any concrete engine implementation satisfies the
interface contract: `extract()` returns a list of dicts/objects, each with the required
fields and value ranges. This suite runs against mock engines in CI and against live
engines in the nightly benchmark job.

### 7.3 CI pipeline

Standard CI (no LIVE_OCR_TESTS) runs unit tests only — fast, no API keys required. The
nightly benchmark job sets LIVE_OCR_TESTS=1, uses API keys from secrets, and posts metric
results to the observability dashboard.

---

## 8. Ordered Task List

| # | Task | Depends on | Done when |
|---|------|------------|-----------|
| 1 | Define and freeze Region schema (§2.2); share with Iona, Solove, Zoriaz | — | All downstream confirm the schema |
| 2 | Implement AbstractOcrEngine base class + contract test suite | Task 1 | Contract tests green |
| 3 | Implement GoogleDocumentAiEngine with unit tests (mock fixtures) | Task 2 | Unit tests green; Region mapping verified |
| 4 | Implement AzureDocumentIntelligenceEngine with unit tests (mock fixtures) | Task 2 | Unit tests green; angle field verified |
| 5 | Implement MistralOcrEngine with unit tests (mock fixtures) | Task 2 | Unit tests green |
| 6 | Implement tiling logic + merge/de-duplication + unit tests | Task 2 | Tiling unit tests green |
| 7 | Implement cost cap + resolution scaling + caching layer | Task 3–5 | Unit tests green; cost estimate verified |
| 8 | Assemble hand-labelled Arabic test set (with labelling protocol) | — | ≥10 images labelled and adjudicated |
| 9 | Implement benchmark harness (§4.3) | Tasks 3–5, 8 | Harness produces comparable per-engine metrics |
| 10 | Run benchmark; record baseline metrics for all three engines | Tasks 9 | Results table committed to docs |
| 11 | Select primary engine based on benchmark; document rationale | Task 10 | Engine selection decision recorded |
| 12 | Wire selected engine as default in factory; integration test with Omar's output | Tasks 11, Omar's task | Integration test green end-to-end |
| 13 | Calibrate low-confidence threshold (provisionally 0.75) against test set | Task 10 | Threshold produces < 5% false-flag rate on high-quality regions |
| 14 | Performance / latency test on A0 drawing at 300 DPI | Task 12 | p50 latency within budget |
| 15 | Handoff to Vivek: adapter callable from the pipeline; confirm quota hook contract | Tasks 12, 14 | Vivek integration confirmed |

---

## 9. Risks and Open Questions

### 9.1 Arabic OCR accuracy on real drawings (critical)

The benchmark may reveal that no managed engine meets the < 10% CER target on the most
difficult images (dense, rotated, low-resolution scans). Escalation path:
- First response: improve Omar's pre-processing (contrast enhancement, super-resolution
  upscaling before OCR call).
- Second response: ensemble two engines — use Azure for rotated regions and Google for
  dense printed Arabic; merge by confidence.
- Third response: fine-tune an open-source Arabic OCR model (e.g., PaddleOCR with Arabic
  weights) on labelled architectural drawings. This is expensive but may be necessary if
  managed engines fail. Flag as a risk to Abdo and Kian immediately if benchmarks are
  poor.

### 9.2 Rotated text precision

Rotated dimension annotations are the hardest sub-problem. If bbox angle is wrong by
> 5° at scale, Phase-2 overlay rendering will visually misplace translations. Open
question: do Google Document AI and Azure both return per-word polygon vertices (not just
axis-aligned rects) for rotated words? This must be confirmed in the first benchmark run,
not assumed from documentation.

### 9.3 Mixed-language region ordering

When a single Region contains both Arabic and English (e.g., "DPC (طبقة العزل)"), the
engine's text ordering may be inconsistent. The adapter must preserve the raw engine
output for Iona to handle, and must tag such regions with `lang: null` or a mixed-language
marker. Protocol to be agreed with Iona before Task 1 is closed.

### 9.4 Handwritten Arabic

No managed engine reliably transcribes handwritten Arabic. For Phase 1 the decision is to
flag these as low-confidence and surface them for user correction. A dedicated handwritten
Arabic model is Phase 2+ scope, not MVP. This must be communicated to the product owner
(Abdo) and reflected in the MVP success criteria.

### 9.5 API pricing volatility

OCR API pricing changes. The cost model is validated against list prices at planning
time, but must be re-checked before launch. Self-hosting (Azure Container, PaddleOCR)
is the fallback if API costs become prohibitive at scale.

### 9.6 Test set size and bias

Ten to twenty drawings is a small test set. Results may not generalise to the full
diversity of Gulf/MENA architectural drawing styles. Risk is accepted for Phase 1 with
the explicit understanding that the test set grows over time and accuracy dashboards in
production will track real-world performance.

### 9.7 Image DPI from Omar's pre-processor

The adapter assumes Omar's output is at a known, normalised DPI (target ≥300). If Omar's
pre-processor does not guarantee a minimum DPI, the adapter's tiny-text mitigation (§5.1)
cannot function correctly. This is a hard dependency: must be confirmed with Omar before
Task 3 begins.

---

## 10. Interface Summary (for cross-team reference)

**Provided interface:**
```
OcrEngine.extract(normalized_image) -> list[Region]

Region = {
  "text":       str,           # UTF-8 OCR text
  "bbox":       {
    "x":        float,         # pixels from left
    "y":        float,         # pixels from top
    "width":    float,         # pixels
    "height":   float,         # pixels
    "angle":    float          # degrees clockwise; 0.0 = upright
  },
  "confidence": float,         # [0.0, 1.0]; flag for review if < 0.75
  "lang":       str | null     # BCP-47 or null
}
```

**Consumed interface:** `PreProcessor.process(image) -> normalized_image` (Omar)

**Downstream consumers of this output:** Iona (Translator), Solove (Result Store),
Zoriaz (Frontend — Phase 2 overlay uses bbox)

---

*Plan owner: Nour. Review required from Kian (architecture) and Abdo (scope/acceptance)
before implementation begins.*
