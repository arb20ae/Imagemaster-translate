# Nour — OCR Adapter

**Type:** Component specialist
**Owns interface:** `OcrEngine.extract(image) -> [Region]`

## Allocated skills
- `superpowers:test-driven-development`
- `superpowers:systematic-debugging`

## Responsibilities / tasks
Wrap the chosen OCR engine(s) behind one interface; run the engine A/B to win Arabic
accuracy. Owns the authoritative `low_confidence` flag (calibrated to the benchmark).

**Detailed plan:** [`../docs/components/nour-ocr-adapter.md`](../docs/components/nour-ocr-adapter.md)

## Working notes & log
- **2026-05-26** — Region schema (now canonical):
  `text, bbox{x,y,w,h,angle}, confidence, lang, region_index, low_confidence`.
  Engine candidates: Google Document AI, Azure Document Intelligence, Mistral OCR.
  Benchmark metrics: Arabic CER/WER, bbox IoU, rotation error, latency, cost.
- **2026-05-26** ⚠ **Add `region_index` to the emitted Region** (ordering owner).
- **2026-05-26** 🚩 **HIGHEST-PRIORITY per feasibility review:** this component is the
  make-or-break risk. Run a **time-boxed Arabic-OCR spike FIRST** (3–5 days, no app/DB):
  feed ~15–20 real Arabic drawings through 2–3 engines (+Omar's pre-proc) and measure CER.
  Decision gate: **GO / PIVOT / STOP** before building the rest.
