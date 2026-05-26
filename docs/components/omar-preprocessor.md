# Pre-processor Component Plan — Omar

**Owner:** Omar (Pre-processor specialist)
**Date:** 2026-05-26
**Phase:** 1 (MVP)
**Interface provided:** `PreProcessor.process(image) -> normalized_image`
**Reference spec:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`
**Reference team:** `docs/team/TEAM.md`

---

## 1. Role in the Pipeline

The pre-processor is the first stage after upload. Its output is the sole input to
the OCR adapter (Nour's stage). Because OCR accuracy — especially Arabic accuracy on
noisy scans — is the central technical risk of the MVP, the quality of this stage
disproportionately determines whether the product works.

Arabic is uniquely sensitive to pre-processing failures: RTL cursive letterforms have
fine strokes, context-dependent shapes, and diacritics that disappear or smear under
noise, blur, or poor contrast. A processing step that is neutral for Latin text can
be catastrophic for Arabic. Every step below is justified in terms of both input
types (phone photo vs. scanned PDF page) and Arabic-specific impact.

---

## 2. Ordered Processing Pipeline

The pipeline runs in this fixed order. Each step operates on the output of the
previous one. Steps marked OPTIONAL are gated by the input-type config (see §4).

### Step 1 — Input normalisation (always)

**What:** Accept any common input form (PIL Image, numpy array, raw bytes, file path).
Standardise to a numpy uint8 BGR array (OpenCV's native format) at the start.
Also record input metadata: original dimensions, colour mode, estimated DPI if
readable from EXIF/PDF metadata.

**Why:** Downstream steps all assume a consistent array type. Recording original DPI
determines whether upscaling (Step 5) is needed and by how much.

**Helps:** both input types equally.

### Step 2 — Colour-to-grayscale conversion (always)

**What:** Convert to single-channel grayscale using OpenCV `cvtColor(BGR2GRAY)`.
If the image is already grayscale, this is a no-op. If it is a colour photo, use a
luminosity-weighted conversion (OpenCV's default).

**Why:** OCR engines work on intensity, not colour. Grayscale halves memory and
processing cost for all subsequent steps. For architectural drawings, colour carries
almost no annotation information — annotations are black ink on a light background
(or white ink on a dark blueprint). Converting early means every downstream step
works on a simpler 1-channel signal.

**Arabic note:** No specific impact on Arabic letterforms, but it simplifies the
channel maths that follow.

**Helps:** both input types.

### Step 3 — EXIF rotation correction (always)

**What:** Read EXIF orientation tag (if present) and rotate the image to its true
upright orientation before any other geometric processing.

**Why:** Phone cameras write orientation to EXIF rather than rotating pixels. Without
this step, deskew (Step 6) will measure the wrong angle and all bounding boxes will
be offset. Scanned PDFs rarely have this problem; phone photos almost always do.

**Helps:** phone photos primarily.

### Step 4 — Noise reduction / denoising (always, parameters vary)

**What:** Apply a non-local means denoising filter (`cv2.fastNlMeansDenoising` for
grayscale). Parameters: `h` (filter strength), `templateWindowSize`,
`searchWindowSize` — tuned per input type (see §4).

**Why:** Phone photos carry sensor noise (ISO grain) and JPEG compression artefacts.
Scanned PDFs carry scanner noise and paper texture. Both degrade OCR by fragmenting
thin strokes into disconnected blobs or thickening them into merged blobs. Arabic
letterforms are stroke-thin and connected; noise that affects a single stroke can
change the letter identity (e.g. noise on a diacritic or on the final-form of a
letter).

Non-local means is preferred over Gaussian blur because it preserves edges (letter
boundaries) while smoothing flat regions. Gaussian blur is faster but smears edges,
which is harmful for Arabic fine strokes.

**Alternative for performance:** `cv2.bilateralFilter` — faster, also edge-preserving,
slightly less effective on heavy noise. Consider as a fast-path option.

**ML alternative (optional, Phase 1b):** A learned denoising model (e.g. DnCNN or
the denoising mode of a document-restoration model such as DocUNet) could
outperform classical filters on degraded scan types. Flagged as a future upgrade;
the interface is unchanged.

**Helps:** phone photos significantly; scanned PDFs moderately.

### Step 5 — Resolution upscaling (conditional on DPI / pixel density)

**What:** If the effective DPI is below a threshold (default: 200 DPI; see §4),
upscale to at least 300 DPI using `cv2.resize` with bicubic interpolation
(`INTER_CUBIC`). Cap upscaling at 2x original dimensions to avoid artefact
amplification on very low-resolution inputs.

**Why:** OCR engines — especially Tesseract and cloud engines benchmarked on typical
documents — assume text height of approximately 30–50 px per character. Arabic
characters at 150 DPI may be 10–15 px tall; at that size, fine strokes and
diacritics are 1–2 px wide and are lost to any threshold step. Upscaling before
binarization (Step 7) ensures there is enough pixel mass to survive thresholding.

**Why bicubic:** Bicubic interpolation preserves edge sharpness better than bilinear
for text at moderate upscale ratios. Nearest-neighbour produces artefacts at Arabic
stroke junctions.

**ML alternative (optional, Phase 1b):** A super-resolution model (e.g. Real-ESRGAN,
which has a document-optimised variant) would produce crisper results at 4x upscale
than bicubic, especially for Arabic fine strokes. Flagged for evaluation in the
accuracy test harness (§6).

**Helps:** low-resolution phone photos significantly; low-DPI scans moderately.

### Step 6 — Deskew (conditional, see §5 for edge cases)

**What:** Detect and correct page tilt. Strategy:

1. Apply a light threshold to produce a binary version for analysis only (not
   permanent — Step 7 produces the real binary).
2. Detect dominant line angle using Hough line transform
   (`cv2.HoughLinesP`) or projection-profile skew estimation (projection profile is
   more robust for drawings with mixed linework).
3. If detected skew angle exceeds a minimum threshold (default: 0.5°) and is below a
   maximum (default: 45°), apply an affine rotation
   (`cv2.warpAffine`) with white (255) border fill.
4. Return angle as metadata alongside the image for downstream logging.

**Why:** Even a 2° skew can misalign OCR bounding boxes with annotation text. For
Arabic — which uses right-to-left word order and has no descenders/ascenders as
separation cues — a skewed baseline means the OCR engine merges or splits words at
the wrong boundary. Annotation text on architectural drawings is also frequently
positioned at arbitrary angles (rotated dimension labels, leader-line text); Step 6
targets full-page tilt, not individual-annotation rotation (that is OCR's
responsibility).

**Helps:** phone photos significantly (hand-held shots are rarely level); scanned
PDFs occasionally (some scanners produce 0.5–2° systematic tilt).

### Step 7 — Adaptive binarization / contrast normalisation (always)

**What:** Convert the grayscale image to binary (black on white) using adaptive
thresholding: `cv2.adaptiveThreshold` with `ADAPTIVE_THRESH_GAUSSIAN_C`, block size
tuned per input type (default 31 for scans, 51 for photos), constant C tuned per
input type.

Fallback: if adaptive threshold produces less than 5% foreground or more than 70%
foreground (pathological result), retry with Otsu's global threshold.

Ensure the output is always white background / black text (invert if needed by
checking mean pixel value).

**Why:** OCR engines perform best on binarized images. Adaptive thresholding handles
uneven illumination (common in phone photos of large drawings placed on a desk) and
varying paper tone (yellowed drawings, blueprint backgrounds). Global Otsu threshold
fails in uneven-lighting conditions because the optimal global cutoff does not exist.

**Arabic note:** Adaptive binarization is critical for Arabic because diacritics
(harakat, shadda) are small marks that a too-aggressive threshold will eliminate
entirely, or a too-lenient threshold will merge with adjacent strokes. Block size
must be large enough to include diacritics in the local neighbourhood.

**Helps:** phone photos significantly (uneven flash/ambient light); scanned PDFs
moderately (uneven scanner illumination, yellowed paper).

### Step 8 — Morphological cleanup (conditional, light by default)

**What:** Apply a small morphological opening (`cv2.morphologyEx` with
`MORPH_OPEN`, 1x1 or 2x2 kernel) to remove isolated noise pixels that survived
denoising and binarization. Apply a light closing (2x2) to reconnect broken strokes
if stroke fragmentation is detected (heuristic: foreground pixel connectivity below
a threshold).

Gate this step: skip if the binarized image already has clean, connected foreground
regions (measured by connected-component analysis on a sample).

**Why:** Post-binarization noise and stroke breaks are common after Step 7. For
Arabic, a broken stroke changes the character identity. For example, a broken
`ب` (ba) looks like two separate components to OCR. The morphological operations
are small and conservative — a 3x3 kernel can merge distinct characters, which is
worse than a break.

**Helps:** scanned PDFs with scanner noise; phone photos with aggressive JPEG
compression.

### Step 9 — Output packaging (always)

**What:** Return the processed image as a numpy uint8 array (grayscale, white
background, black text) plus a metadata dict:

```python
{
  "original_size": (h, w),
  "output_size": (h, w),
  "effective_dpi_in": int_or_none,
  "skew_angle_deg": float_or_none,
  "steps_applied": ["grayscale", "denoise", "upscale", ...],
  "input_type_detected": "photo" | "scan" | "unknown"
}
```

The metadata is logged by the API layer (Vivek's stage) for observability and
accuracy correlation (§6).

---

## 3. Technology Choice: OpenCV in Python

**Choice:** `opencv-python` (OpenCV 4.x) as the primary image-processing library,
within the Python / FastAPI backend mandated by the project spec (§8).

**Justification:**

1. **Ecosystem fit.** The backend is Python; OpenCV is the de facto standard
   image-processing library in that ecosystem. No cross-language FFI overhead.
2. **Comprehensive.** Denoising, geometric transforms, morphology, adaptive
   threshold, and Hough transforms are all first-class in OpenCV. No need for
   multiple libraries.
3. **Performance.** OpenCV is C++ under the hood; Python bindings are thin wrappers.
   Processing a 300 DPI A1 scan (roughly 10 Mpx) completes in well under 1 s per
   step on modest hardware.
4. **Swappability.** Because the interface is `PreProcessor.process(image) ->
   normalized_image`, the internals can migrate to a different library (scikit-image,
   Pillow for specific steps, a deep-learning model) without changing the contract.
5. **Testability.** numpy arrays are easy to create, compare (pixel-wise diff), and
   assert on in pytest fixtures.

**Supporting libraries:**

| Library | Role |
|---------|------|
| `opencv-python` | All core processing steps |
| `Pillow` | EXIF reading (more reliable than OpenCV for EXIF) |
| `numpy` | Array manipulation |
| `scikit-image` | Optional: projection-profile skew (more robust than Hough on dense linework) |

**Optional ML enhancements (Phase 1b, gated behind config flag):**

- `torch` + a lightweight super-resolution model (Real-ESRGAN) for Step 5 upscaling.
- `torch` + DnCNN or similar for Step 4 denoising on severely degraded inputs.
These are importable optionally: if `torch` is not installed, the pipeline falls
back to classical methods silently.

---

## 4. Configurable Pipeline Per Input Type

The interface `PreProcessor.process(image) -> normalized_image` remains fixed.
Configuration is injected at construction time or via a config dict per call.

```python
# Conceptual (not implementation code):
# PreProcessor(config: PreProcessorConfig | None = None)
# PreProcessor.process(image, input_type: Literal["photo", "scan", "auto"] = "auto")
```

`input_type="auto"` triggers a lightweight heuristic classifier (Step 0, internal):
- Checks EXIF for camera make/model → photo.
- Checks for PDF source metadata → scan.
- Checks image noise profile (coefficient of variation in a flat region) → high CV = photo.
- Checks colour depth and histogram shape.

**Config parameters that vary by input type:**

| Parameter | scan default | photo default | Notes |
|-----------|-------------|---------------|-------|
| denoise `h` | 7 | 12 | Photos need stronger denoising |
| denoise `templateWindowSize` | 7 | 9 | |
| adaptive threshold block size | 31 | 51 | Photos have more uneven light |
| adaptive threshold C | 5 | 8 | |
| upscale DPI threshold | 200 | 150 | Photos from modern phones often > 300 effective DPI |
| deskew min angle | 0.5° | 1.0° | Scans can have systematic sub-degree tilt |
| morphological kernel | 1×1 | 2×2 | Photos need slightly more cleanup |

All defaults are overridable; the caller (Vivek's API layer) can pass a config dict
to tune for a specific drawing batch or user upload.

---

## 5. Edge Cases

| Edge case | Detection method | Handling |
|-----------|-----------------|----------|
| Low-resolution phone photo (< 100 effective DPI) | DPI estimation from image dimensions and EXIF | Upscale to 300 DPI (2x cap may be insufficient — log a low-quality warning in metadata); flag OCR confidence as potentially unreliable |
| Heavily skewed photo (> 30°) | Hough / projection profile | Apply correction up to 45°; beyond 45°, log a warning and skip deskew (correction at that angle is geometrically ambiguous); surface warning to user |
| Low-contrast blueprint (white lines on blue/dark background) | Histogram analysis: mean < 80 OR mode in dark range | Invert image before grayscale conversion; proceed normally |
| Colour drawing (coloured annotations, highlighted regions) | Saturation channel check | Convert to grayscale (colour carries no annotation information needed for OCR); note: colour annotations may be useful later for Phase 2 overlay — preserve original in result store |
| Very large image (> 20 Mpx, e.g. A0 scan at 600 DPI) | Pixel count check | Downsample to 400 DPI equivalent before processing to cap memory; log original DPI for downstream use |
| Completely blurred image (motion blur on phone) | Laplacian variance < threshold | Log quality warning; apply unsharp mask as best-effort; do not block the pipeline |
| Mixed-language annotation with RTL and LTR text | Not handled by pre-processor | Pass through normally; this is the OCR adapter's (Nour's) responsibility |
| Two-page spread scanned as one image | Detected via aspect ratio and centre-line whitespace | Log as potential two-page spread; do not split (splitting changes the interface contract — flag for future Phase 1b enhancement) |

---

## 6. Measuring Before/After Impact on OCR Accuracy

**This is the most important section.** The project spec (§9) requires accuracy be
measured against a hand-labelled test set before claiming the MVP works. The
pre-processor must prove it helps.

### 6.1 Test set requirements

A hand-labelled test set of real architectural drawings must be assembled (this is a
shared team responsibility, not just Omar's, but Omar defines the format):

- Minimum 20 images for Phase 1 evaluation: at least 10 Arabic-annotated drawings,
  at least 5 phone photos, at least 5 scanned PDFs. Mix of clean and degraded.
- Each image has a corresponding ground-truth JSON file listing every annotation
  text string visible in the image (not bounding boxes — text strings are sufficient
  for OCR accuracy measurement at this stage).
- Images should include at least 3 "hard" Arabic cases: low-res scan, noisy photo,
  rotated annotation text.

### 6.2 Accuracy metric

Use **Character Error Rate (CER)** as the primary metric (standard for Arabic OCR
evaluation):

```
CER = (substitutions + insertions + deletions) / total_ground_truth_characters
```

Lower is better. Also track **Word Error Rate (WER)** as a secondary metric.

For Phase 1, target: CER < 0.15 (< 15%) on the hand-labelled Arabic test set after
preprocessing. Baseline (no preprocessing) is measured first to establish the delta.

### 6.3 Evaluation harness

The evaluation harness is a pytest fixture + script (not application code):

1. For each test image in the set:
   a. Run OCR directly on the raw image → record raw CER/WER.
   b. Run `PreProcessor.process(image)` → run OCR on the result → record processed CER/WER.
2. Compute mean and per-image delta (processed CER - raw CER).
3. Report: percentage of images improved, percentage worsened, mean CER delta.
4. Store results in a JSON report file (committed to `tests/accuracy/results/`) so
   regressions are detectable in CI.

### 6.4 Per-step ablation

To understand which steps contribute most, the harness also supports running the
pipeline with individual steps disabled. This identifies if any step hurts accuracy
(e.g. over-aggressive denoising blurring thin Arabic strokes) and guides parameter
tuning.

### 6.5 OCR engine dependency

The evaluation harness depends on Nour's OCR adapter. For isolated pre-processor
testing before Nour's stage is ready, use Tesseract 5 (with Arabic language pack)
as a local reference engine. Tesseract is not the production engine but is
sufficient to measure relative improvement from pre-processing.

### 6.6 Ongoing measurement

The metadata dict returned by Step 9 includes `steps_applied` and
`input_type_detected`. The API layer (Vivek) logs this per job. Once the product
has user uploads, real-world OCR confidence scores can be correlated with input
type and processing path — building a feedback loop to tune parameters without
needing new hand-labelled data.

---

## 7. TDD / Testing Approach

All code is written test-first. Tests live in `tests/preprocessor/`.

### 7.1 Fixture images

A set of small (< 200 KB) fixture images is committed to `tests/fixtures/images/`:

| Fixture filename | Description | Tests it covers |
|-----------------|-------------|-----------------|
| `scan_clean_arabic.png` | Clean 300 DPI scan with Arabic annotations | Baseline; no-op path |
| `scan_noisy_arabic.png` | 200 DPI scan with scanner noise | Step 4 denoising |
| `scan_skewed_2deg.png` | Clean scan rotated 2° | Step 6 deskew |
| `photo_lowres_arabic.jpg` | 96 DPI phone photo | Steps 3, 4, 5 |
| `photo_uneven_light.jpg` | Photo with flash hotspot | Step 7 adaptive threshold |
| `blueprint_whiteonblue.png` | White lines on dark blue background | Step 2 + inversion edge case |
| `scan_lowcontrast_latin.png` | Latin-annotated low-contrast scan | Steps 4, 7 (non-Arabic baseline) |

Fixture images are synthetic (generated by the test author) or anonymized real
drawings cleared for testing use. They must NOT contain personally identifiable
information or unpublished proprietary drawing content.

### 7.2 Test categories

**Unit tests (per step):**
- Each pipeline step has an isolated unit test that receives a crafted input
  (constructed programmatically or from a fixture) and asserts a measurable output
  property (e.g. after deskew, the detected skew angle on the output is < 0.5°;
  after binarization, the output has exactly 2 unique pixel values).

**Integration tests (full pipeline):**
- `test_process_scan()` — runs the full pipeline on a scan fixture; asserts output
  dtype, shape, and that output CER (via Tesseract) is not worse than input CER.
- `test_process_photo()` — same for a photo fixture.
- `test_interface_contract()` — asserts that the return type of `process()` is always
  a numpy uint8 array regardless of input format (PIL, bytes, path).

**Regression tests (accuracy baseline):**
- `test_accuracy_no_regression()` — runs the full evaluation harness (§6.3) on the
  fixture set and asserts that mean CER delta <= 0 (i.e. processing never makes
  accuracy worse on the fixture set as a whole).

**Edge-case tests:**
- One test per row in the edge-cases table (§5).
- Tests for pathological inputs: all-black image, all-white image, 1x1 pixel image,
  non-image bytes (should raise a clear ValueError, not an OpenCV crash).

### 7.3 Mocking OCR in unit tests

Unit tests for the pre-processor do not invoke a real OCR engine. Accuracy
assertions in unit tests use pixel-level metrics (e.g. SSIM comparison to a
reference-processed ground truth image) or geometric metrics (angle, DPI). OCR is
only invoked in the accuracy harness (§6.3) and in integration tests explicitly
tagged `@pytest.mark.ocr`.

---

## 8. Ordered Task List

Tasks are ordered: each unblocks the next.

1. **Set up `tests/fixtures/images/`** — create or collect the 7 fixture images
   listed in §7.1. No code written yet; this unblocks all subsequent test writing.

2. **Scaffold `PreProcessor` class** — empty class with the `process()` signature,
   typed parameters, and docstring. Write the interface-contract test first
   (TDD: test fails, then implement).

3. **Implement Step 1 (input normalisation) + Step 9 (output packaging)** — the
   shell that all other steps plug into. Tests: type coercion tests for PIL / bytes
   / path inputs.

4. **Implement Step 2 (grayscale) + Step 3 (EXIF rotation)** — trivial steps; tests
   assert output is single-channel and orientation is upright.

5. **Implement Step 4 (denoising)** with scan and photo parameter sets. Tests:
   SSIM of noisy fixture vs. denoised output should be higher than SSIM of noisy
   vs. original (noise is reduced); edge content is preserved (Canny edge count
   does not drop by more than 20%).

6. **Implement Step 5 (upscaling)** with DPI detection. Tests: output DPI >= 300;
   upscale does not exceed 2x; already-sufficient-DPI images are not upscaled.

7. **Implement Step 6 (deskew)**. Tests: after processing `scan_skewed_2deg.png`,
   re-measure skew angle and assert < 0.5°.

8. **Implement Step 7 (adaptive binarization)**. Tests: output has exactly 2 unique
   pixel values; background is white (mean > 200); adaptive beats Otsu on the
   uneven-light fixture (compare foreground connectivity).

9. **Implement Step 8 (morphological cleanup)**. Tests: connected-component count
   does not increase (no new fragments created).

10. **Implement input-type auto-detection heuristic** and per-type config switching.
    Tests: photo fixtures are detected as `photo`; scan fixtures as `scan`.

11. **Write integration tests** for full pipeline on all fixtures.

12. **Assemble accuracy evaluation harness** (§6.3) using Tesseract. Run baseline
    (raw CER) and processed CER on the full fixture set. Commit results to
    `tests/accuracy/results/baseline.json`.

13. **Tune parameters** based on Step 12 results. Re-run harness; commit updated
    results.

14. **Write edge-case tests** (§7.2) and implement handlers (§5).

15. **Document config API** in this file and in code docstrings.

16. **Hand off to Nour** — ensure `PreProcessor` output format matches what
    `OcrEngine.extract()` expects (coordinate with Nour on array format, colour mode,
    DPI metadata passing).

---

## 9. Risks and Open Questions

| # | Risk / Question | Likelihood | Impact | Mitigation / Resolution needed |
|---|----------------|-----------|--------|-------------------------------|
| 1 | Over-denoising blurs Arabic fine strokes, worsening CER | Medium | High | Ablation tests (§6.4) will detect this; parameter `h` is tunable per input type; non-local means is chosen specifically for edge preservation |
| 2 | Adaptive threshold block size too small for large Arabic characters, or too large for small diacritics | Medium | High | Test on fixture images at multiple scales; expose block size as a config parameter; may need multi-scale binarization for mixed-size text |
| 3 | Deskew misidentifies drawing linework as text baseline, corrects to wrong angle | Medium | Medium | Use projection-profile method rather than Hough when linework density is high; cap correction at 45°; log detected angle in metadata |
| 4 | Super-resolution model adds latency beyond acceptable threshold for a web tool | Low-Medium | Medium | SR is optional (Phase 1b, config flag); classical bicubic is the default; measure latency in integration tests |
| 5 | Hand-labelled test set is too small (< 20 images) or biased toward one input type | Medium | High | Shared team task to collect diverse drawings; Omar defines format but collection is coordinated by Abdo/PM |
| 6 | Tesseract (used in testing) behaves differently from the production OCR engine | Medium | Medium | Ablation results are directional, not absolute; Nour's benchmark harness on the same test set is the authoritative accuracy measurement |
| 7 | Blueprint inversion heuristic (Step 5 edge case) misidentifies dark-toned scans as blueprints | Low | Low | Heuristic uses both mean and histogram mode; fallback is to attempt both polarities and pick the one with higher foreground connectivity |
| 8 | Large A0 scans at 600 DPI exceed memory limits in serverless workers | Medium | Medium | Cap at 400 DPI equivalent in Step 5; coordinate with Vivek on worker memory limits; consider tiled processing for Phase 1b |

**Open questions for Kian / Abdo:**

- Q1: Should the pre-processor return the original (pre-processed) image alongside
  the normalised image for Phase-2 overlay purposes, or does the result store
  (Solove) retain the original independently? (This affects the return type.)
- Q2: What is the acceptable processing latency budget per image? (Informs whether
  SR upscaling is viable in Phase 1 or must wait for Phase 1b.)
- Q3: Who is responsible for collecting and curating the hand-labelled test set?
  Omar defines the format; Abdo should assign the collection task explicitly.
