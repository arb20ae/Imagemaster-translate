# Omar — Pre-processor

**Type:** Component specialist
**Owns interface:** `PreProcessor.process(image) -> normalized_image`

## Allocated skills
- `superpowers:test-driven-development`
- `superpowers:systematic-debugging`

## Responsibilities / tasks
Deskew, denoise, contrast/resolution normalization. Disproportionately important for
Arabic OCR accuracy on noisy scans/photos. Persists processed-image dimensions (this is
what makes the B1 coordinate-space ruling safe).

**Detailed plan:** [`../docs/components/omar-preprocessor.md`](../docs/components/omar-preprocessor.md)

## Working notes & log
- **2026-05-26** — 9-step OpenCV pipeline (grayscale → EXIF rotate → denoise → upscale →
  deskew → adaptive threshold → morphology → package). Decisions frozen in CONTRACT.md:
  **300 DPI target, 2× upscale cap, PNG output, `low_res_warning` below ~200 DPI.**
- **2026-05-26** — Accuracy method: **CER** vs a hand-labelled real-drawing set, per-step
  ablation; acceptance contributes to the end-to-end **CER ≤ 0.15** bar.
- **2026-05-26** — Note: the spike (below) can reuse these steps; coordinate the DPI floor
  with Nour.
