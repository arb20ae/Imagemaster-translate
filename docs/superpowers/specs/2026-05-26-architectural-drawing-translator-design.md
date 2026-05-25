# Imagemaster-Translate — Design Spec

**Date:** 2026-05-26
**Status:** Approved direction; pending final spec review
**Repo:** https://github.com/arb20ae/Imagemaster-translate.git

---

## 1. Vision & Problem

International architectural detail drawings are hard to read across language and
standards boundaries. Students, lecturers, tutors, and contractors working with
foreign drawings struggle with both the **language** of annotations and the
**conventions/standards** they encode.

Imagemaster-Translate is a web tool that lets a user upload a detail drawing and
get its annotations translated — and, in later phases, get the drawing explained,
mapped to the originating country's building codes, cross-referenced across
standards, and eventually reconstructed as editable CAD.

The product goal is to be the place where someone working with an unfamiliar
international drawing can **get everything they need at once** — not just a
language tool, but a practical professional reference.

## 2. Scope & Phasing

The full vision is too large for one build. It is decomposed so each phase ships
real value and de-risks the next.

| Phase | Capability | Core AI/tech skill | Rationale |
|------|-----------|-------------------|-----------|
| **1 (MVP)** | Translate text annotations; **glossary / side-by-side view** | OCR + glossary-aware machine translation | Tractable, shippable, immediately useful |
| **2** | **In-place overlay** of translations **+ Building-codes reference** for the document's country of origin | Layout/positioning; country-of-origin detection; curated code index | Overlay reuses Phase 1 bounding boxes; building codes turn it from educational tool into professional reference |
| **3** | **Explain/teach** the detail (symbols, line types, materials, build-up) | Multimodal vision + reasoning | Highest educational value; reuses uploaded-drawing infrastructure |
| **4** | **Standards interpretation** (ISO / BS / DIN / GB / ANSI cross-reference) | Knowledge base + reasoning | Builds on the explanation engine |
| **5** | **DWG / DXF reconstruction** (experimental) | Vector reconstruction / vectorization | Research-grade; gated behind validated demand |

**Language rollout (within Phase 1+):**
1. English ↔ Arabic (first)
2. Major European (DE / FR / ES / IT / NL …)
3. Asian (Chinese, etc.)
4. Maximum coverage (any-to-any)

### Note on the Arabic-first choice
Strategically strong: the MENA/Gulf construction market is large and underserved,
and no existing tool *understands architectural drawings* in Arabic. Technically,
Arabic is one of the **harder OCR scripts** on noisy scans/photos (RTL, cursive,
context-dependent letter forms, rotated annotations). The first language pair is
therefore also the hardest OCR problem — this raises the bar on OCR-engine
selection and demands dedicated Arabic accuracy testing.

## 3. Architecture — modular, swappable pipeline

No single vendor or model is load-bearing. The spine is a staged pipeline where
each stage sits behind a clean interface and can be swapped or A/B-tested.

```
Upload
  → Pre-process (deskew, denoise, normalize)
  → OCR (text + bounding boxes + confidence + detected language)
  → Glossary-aware Translation (LLM + injected architectural glossary)
  → Result store (regions + translations + bboxes)
  → Glossary / side-by-side view
        ↘ Phase 2 → Overlay renderer (reuses bboxes)
        ↘ Phase 2 → Country detection → Building-codes reference
        ↘ Phase 3 → Multimodal explanation engine
```

### Stage interfaces (the contracts)
- `PreProcessor.process(image) -> normalized_image`
- `OcrEngine.extract(image) -> [Region{text, bbox, confidence, lang}]`
- `Translator.translate(regions, src, tgt, glossary) -> [Region{+translation}]`
- `Glossary.lookup(term, src, tgt) -> canonical_term`
- *(Phase 2)* `CountryDetector.detect(regions, image) -> {country, standard, confidence}`
- *(Phase 2)* `CodeIndex.lookup(country, topic) -> [reference]`

Swappability is the key property: it lets us A/B OCR engines to win the Arabic
accuracy fight, drop in a multimodal LLM for Phase 3, and migrate hot stages to
self-hosted engines later if cost or data-privacy require it.

## 4. Components

- **Web frontend** — upload, large-image drawing viewer (pan/zoom), glossary panel
  with click-to-locate, language picker. Later: overlay toggle, codes panel.
- **API / orchestration backend** — runs the pipeline; manages async jobs (OCR can
  be slow → job queue + workers).
- **Pre-processor** — deskew, denoise, contrast/resolution normalization.
  Disproportionately important for Arabic scan accuracy.
- **OCR adapter** — wraps the chosen OCR engine; returns text + bbox + confidence + lang.
- **Translator** — LLM call translating each region with the architectural glossary
  injected and the drawing context, so domain terms stay correct.
- **Glossary store** — curated EN↔AR (then per-pair) architectural term map. The moat.
- **Result store** — persists regions, translations, bboxes (makes Phase 2 overlay "free").
- *(Phase 2)* **Country detector** — infers origin from language, title-block markings,
  standard references, and units.
- *(Phase 2)* **Building-codes reference index** — see §6.

## 5. The differentiator: a curated architectural glossary

This is what makes the product *good* rather than "image translate." Generic MT
mangles construction terms (e.g. Arabic ↔ *screed, soffit, damp-proof course, RCC,
blinding*). We maintain a domain glossary per language pair and **inject it into
every translation**, forcing terms to their correct industry equivalents.

- Starts cheap (a spreadsheet / simple table).
- Compounds in value as it grows.
- Genuinely defensible IP — hard for a generic competitor to replicate.

## 6. Building-codes reference (Phase 2) — design & legal caveat

**Value:** turns the product from an educational tool into a one-stop professional
reference — translate the drawing *and* surface the relevant code for its country.

**Design:**
1. `CountryDetector` infers the document's country of origin (language, title-block,
   referenced standards such as DIN/BS/SASO/SBC, measurement units).
2. `CodeIndex` returns the **applicable code(s)** for that country plus a curated
   reference: code name, governing body, scope summary, and an **official link**.

**Legal caveat (important):** building codes are frequently **copyrighted and sold**
(IBC, Eurocodes, BS, Saudi SBC, etc.). The feature must **identify and link to /
summarize official sources — not reproduce full code text** — to avoid licensing
and liability risk. It is built as a "code identifier + curated reference index,"
which is both safer and still highly useful.

## 7. Scaling ladder & infrastructure

The product grows in stages; the infrastructure is architected from day one to
support the full ladder with **no rewrite** between tiers.

| Tier | Audience | Infra focus |
|------|----------|-------------|
| **0** | Solo (you) testing | Cheap single managed deployment; local dev; cost guardrails |
| **1** | ~10 invited users | Auth, per-user usage quotas, basic monitoring |
| **2** | Field / LinkedIn connections | Feedback capture, accuracy telemetry, onboarding flow |
| **3** | Universities & beyond | Multi-tenant cohorts, higher concurrency, autoscaling workers, optional SSO |

**Architectural enablers (built early so scaling is config, not rewrite):**
- **Containerized, stateless backend** behind a load balancer.
- **Async job queue + horizontally scalable workers** (OCR/translation are the slow,
  scalable part).
- **Managed database** (jobs, users, regions, glossary) + **object storage** (images).
- **Auth + multi-tenancy** from early so university cohorts onboard cleanly.
- **Per-user usage quotas** for cost control (and future monetization metering).
- **Observability**: logging, error tracking, and **cost + OCR-accuracy dashboards**
  (accuracy must be measurable — see §9).
- Start on a small managed host (e.g. Render / Railway / Fly.io or a single cloud VM),
  with a clear path to container autoscaling / serverless workers.

## 8. Proposed tech stack

- **Frontend:** React / Next.js + canvas/SVG drawing viewer (e.g. OpenSeadragon for
  large-image pan/zoom).
- **Backend:** Python (FastAPI) — strongest OCR/CV/ML ecosystem — with an async job
  queue (Redis/RQ or Celery).
- **OCR:** start managed (Google Document AI / Azure Document Intelligence / Mistral
  OCR), **benchmarked on real Arabic drawings before committing**.
- **Translation:** Claude (vision-capable), glossary-injected.
- **Storage:** object storage (images) + relational DB (jobs / regions / glossary / users).

## 9. MVP success criteria

The MVP succeeds if: a user uploads a scanned EN or AR detail drawing, the system
extracts the annotations, translates them with **correct architectural terminology**,
and presents an accurate, **click-to-locate glossary** — with **low-confidence items
flagged** for user review.

Target a concrete accuracy bar measured against a **hand-labelled test set of real
drawings** before claiming the MVP works. (Define the exact threshold during planning.)

## 10. Strengths & weaknesses of investing

### Strengths / Opportunities
- **Real, underserved pain.** Cross-border detail drawings genuinely confuse students,
  tutors, and contractors; no dominant tool owns this niche.
- **Arabic-first = strategic whitespace.** Large Gulf/MENA construction market; generic
  tools translate Arabic *language* but none understand *architectural drawings*.
- **Defensible moat over time.** Curated domain glossary + (later) standards/codes
  knowledge base compound and resist generic-competitor replication.
- **Coherent expansion ladder.** Translation → overlay+codes → explanation → standards
  → CAD; each phase reuses the last.
- **Favorable timing.** Multimodal AI is now good enough to make Phases 1–3 feasible at
  reasonable cost.

### Weaknesses / Threats / Risks (with mitigations)
- **Arabic OCR on noisy scans is the central technical risk.** Poor accuracy on real
  photos would undermine MVP credibility. *Mitigation:* heavy pre-processing, OCR
  engine A/B, confidence flags, human-correctable results.
- **Drawings are visually dense & noisy** — tiny fonts, rotated text, overlapping
  linework — harder than typical document OCR.
- **Per-use API costs** scale with usage; large images are expensive. *Mitigation:*
  modular stages allow self-hosting hot paths later; per-user quotas.
- **Trust / liability.** A mistranslated structural note is high-stakes. *Mitigation:*
  position as a **learning/reference aid, not a certified source**; visible confidence
  scores. Building-codes feature links to official sources rather than reproducing them.
- **Phases 4–5 are research-grade.** DWG reconstruction could consume large effort for
  marginal payoff — explicitly **gated behind validated demand** (YAGNI).
- **Unclear monetization (acknowledged).** The MVP doubles as **demand validation** to
  answer commercial-vs-academic before heavy spend.

## 11. Out of scope (for now / YAGNI)

- Full DWG/DXF reconstruction (Phase 5, demand-gated).
- Reproducing full building-code text (legal risk — link/summarize only).
- Maximum-language any-to-any coverage (last in rollout).
- Certified/authoritative translation guarantees.
