# Imagemaster-Translate — Team Charter

**Date:** 2026-05-26
**Reference spec:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`

This charter assigns one specialist per pipeline component, plus a project manager
and a technical expert. Each specialist owns one stage behind a clean interface
(see spec §3) so they can work and be tested independently.

## Org chart

```
                         Abdo  (Project Manager)
                           |
                         Kian  (Technical Expert / Architect)
                           |
   ┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
 Zoriaz     Vivek      Omar       Nour       Iona       Matt      Solove
 Frontend   API/BE   Pre-proc   OCR adpt  Translator  Glossary   Results
```

## Leadership

### Abdo — Project Manager (oversight)
- **Role:** Owns scope, sequencing, dependencies, and acceptance. Keeps work aligned
  to the spec and the phasing/scaling ladder. Runs the final best-practice review
  together with the lead (Claude).
- **Skills:** `superpowers:writing-plans`, `superpowers:verification-before-completion`,
  `superpowers:requesting-code-review`, `superpowers:finishing-a-development-branch`.
- **Tasks:** Consolidate component plans into one Phase-1 plan; enforce interface
  contracts; gate completion on evidence; flag scope creep (YAGNI).

### Kian — Technical Expert / Architect
- **Role:** Guards architecture quality, interface design, tech-stack choices, and
  cross-component consistency. Reviews each specialist's plan for soundness.
- **Skills:** `feature-dev:code-architect`, `pr-review-toolkit:type-design-analyzer`,
  `pr-review-toolkit:code-reviewer`, `superpowers:receiving-code-review`.
- **Tasks:** Validate the modular pipeline contracts; pressure-test the OCR-engine and
  storage choices; ensure stages are swappable and independently testable.

## Component specialists

### Zoriaz — Web Frontend
- **Owns:** Upload UI, large-image drawing viewer (pan/zoom), glossary panel with
  click-to-locate, language picker. (Phase 2: overlay toggle, codes panel.)
- **Skills:** `frontend-design:frontend-design`, `superpowers:test-driven-development`,
  `chrome-devtools-mcp:a11y-debugging`.
- **Interface consumed:** Result store API (regions + translations + bboxes).
- **Phase-1 tasks:** Viewer that renders the drawing and highlights a region when its
  glossary entry is clicked; confidence flags surfaced in the UI; responsive + a11y.

### Vivek — API / Backend & Orchestration
- **Owns:** REST API, pipeline orchestration, async job queue + workers, auth &
  multi-tenancy, per-user usage quotas.
- **Skills:** `feature-dev:code-architect`, `superpowers:test-driven-development`,
  `feature-dev:feature-dev`.
- **Interfaces:** Coordinates all stage interfaces (`PreProcessor`, `OcrEngine`,
  `Translator`, `Glossary`); exposes results to the frontend.
- **Phase-1 tasks:** Define job lifecycle (upload → processing → done); wire the
  pipeline; stub auth + quota hooks; design for horizontal worker scaling.

### Omar — Pre-processor
- **Owns:** Deskew, denoise, contrast/resolution normalization. Critical for Arabic
  scan accuracy.
- **Skills:** `superpowers:test-driven-development`, `superpowers:systematic-debugging`.
- **Interface provided:** `PreProcessor.process(image) -> normalized_image`.
- **Phase-1 tasks:** Pipeline of OpenCV-style steps with measurable before/after impact
  on OCR accuracy; configurable per input type (photo vs scanned PDF).

### Nour — OCR Adapter
- **Owns:** Wrapping the chosen OCR engine; returning text + bbox + confidence + lang.
  Runs the engine A/B for Arabic accuracy.
- **Skills:** `superpowers:test-driven-development`, `superpowers:systematic-debugging`.
- **Interface provided:** `OcrEngine.extract(image) -> [Region{text,bbox,confidence,lang}]`.
- **Phase-1 tasks:** Adapter abstraction over ≥2 engines (e.g. Google Document AI vs
  Azure vs Mistral OCR); benchmark harness against a hand-labelled Arabic test set.

### Iona — Translator
- **Owns:** LLM translation of each region with the architectural glossary injected and
  drawing context.
- **Skills:** `claude-api`, `superpowers:test-driven-development`.
- **Interface provided:** `Translator.translate(regions, src, tgt, glossary) -> [Region{+translation}]`.
- **Phase-1 tasks:** Glossary-aware prompt with caching; EN↔AR first; confidence /
  low-certainty signalling; deterministic, testable outputs.

### Matt — Glossary Store
- **Owns:** Curated architectural term map per language pair (the product moat).
- **Skills:** `supabase:supabase-postgres-best-practices`,
  `superpowers:test-driven-development`.
- **Interface provided:** `Glossary.lookup(term, src, tgt) -> canonical_term`.
- **Phase-1 tasks:** Schema + seed EN↔AR architectural glossary; fast lookup; editable;
  versioned so it can grow as the moat.

### Solove — Result Store
- **Owns:** Persisting regions, translations, bboxes, job metadata (makes Phase-2
  overlay "free").
- **Skills:** `supabase:supabase-postgres-best-practices`,
  `superpowers:test-driven-development`.
- **Interface provided:** read/write API for job results consumed by the frontend.
- **Phase-1 tasks:** Schema for jobs/regions/translations/bboxes; object storage for
  images; queries optimized for the glossary view and future overlay.

## Working agreement
- Every stage hides behind its interface (spec §3) and is independently testable.
- TDD by default (user may override).
- No stage reproduces full building-code text (legal caveat, spec §6).
- Accuracy is measurable against a hand-labelled real-drawing test set before any
  "it works" claim (spec §9).
- All work committed to this repo under `docs/` (plans) and code dirs (later).
