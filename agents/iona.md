# Iona — Translator

**Type:** Component specialist
**Owns interface:** `Translator.translate(regions, src, tgt, glossary) -> [Region(+translation)]`

## Allocated skills
- `claude-api` (prompt caching)
- `superpowers:test-driven-development`

## Responsibilities / tasks
Translate each OCR region with the architectural glossary injected so domain terms map
to correct equivalents. Sets `uncertain`/`uncertain_reason`, `glossary_hit`,
`canonical_term`. Does NOT set `low_confidence` (that's Nour's).

**Detailed plan:** [`../docs/components/iona-translator.md`](../docs/components/iona-translator.md)

## Working notes & log
- **2026-05-26** — Prompt design: system prompt = role + injected glossary + JSON format,
  with a single `cache_control` breakpoint so the glossary is cached across batches/jobs.
  Batch all regions of a drawing in one call (chunk at ~80). Low temperature for determinism.
- **2026-05-26** ⚠ **CONTRACT ALIGNMENT REQUIRED** (feasibility review):
  - `uncertain_reason` must use the frozen enum values
    (`unrecognized_domain_term`, `low_ocr_confidence`, `ambiguous`, `parse_error`,
    `translation_failed`) — not free-text strings;
  - emit `glossary_hit` + `canonical_term`;
  - consume the shared `GlossaryEntry` shape (`src_term/tgt_term/...`).
- **2026-05-26** — Store the actual runtime model id with each translation; don't hardcode.
