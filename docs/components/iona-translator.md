# Iona — Translator Component Plan

**Owner:** Iona  
**Date:** 2026-05-26  
**Phase:** 1 (MVP)  
**Spec reference:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`  
**Team reference:** `docs/team/TEAM.md`

---

## Interface contract

```python
Translator.translate(
    regions:  list[Region],   # from Nour — each has .text, .bbox, .confidence, .lang
    src:      str,            # ISO 639-1 language code, e.g. "en", "ar"
    tgt:      str,            # ISO 639-1 language code
    glossary: list[GlossaryEntry],  # from Matt — each has .src_term, .tgt_term, .context
) -> list[Region]             # same regions, each with .translation and .translation_confidence added
```

`Region` input fields (from Nour): `text`, `bbox`, `confidence`, `lang`  
`Region` output additions: `translation` (str), `translation_confidence` (float 0-1), `uncertain` (bool), `uncertain_reason` (str | None)

This component does **not** own OCR, glossary storage, or result persistence. It receives regions from Nour and a pre-fetched glossary slice from Matt, calls Claude, and returns enriched regions.

---

## 1. Prompt design — glossary injection and architectural terminology

### System prompt (cached)

The system prompt has three sections in order from most stable to least stable, which maps to the caching strategy described in section 2.

**Section A — Role and domain framing (never changes):**

```
You are a specialist architectural drawing annotation translator.
Your job is to translate short text annotations taken from technical
architectural detail drawings. These annotations are professionally
authored, typically brief (one phrase to two short sentences), and must
be rendered with correct industry terminology in the target language.

You are not a general-purpose translator. Every output must reflect how
a qualified architect or building contractor in the target-language
country would write the same note. Generic equivalents are unacceptable
where a domain term exists.
```

**Section B — Injected glossary (changes per language pair, stable per job):**

```
ARCHITECTURAL GLOSSARY ({src} → {tgt})
The following terms MUST be translated to the canonical target-language
industry equivalent shown. Do not paraphrase, split, or substitute these terms.

{for each entry}
  {src_term} → {tgt_term}  [{context if present}]
{end}

If an annotation contains a term from this glossary, use the canonical
translation listed above. If an annotation contains a term not in this
glossary but still appears to be a domain term, translate it using your
knowledge of architectural practice in the target locale, then set the
"uncertain" field to true with reason "unrecognized_domain_term".
```

**Section C — Response format instructions (never changes per job):**

```
OUTPUT FORMAT
Return a JSON array. One object per input annotation, in the same order
as the input. Each object:
  {
    "id":         <copied from input>,
    "translation": <translated text>,
    "uncertain":  true | false,
    "reason":     <string if uncertain, else null>
  }

Return only the JSON array. No preamble, no explanation, no markdown
fences. Your output must parse with json.loads() without modification.
```

### User turn (per batch, changes every call)

```
DRAWING CONTEXT
Source language: {src_label}  (e.g. "English (UK)")
Target language: {tgt_label}  (e.g. "Arabic (Gulf region)")
Drawing type hint: {drawing_type}  (e.g. "wall section", "floor build-up",
                                     "unknown" if not determinable)

ANNOTATIONS TO TRANSLATE
{json_array_of_annotation_objects}
```

Each annotation object in the user turn:

```json
{ "id": 7, "text": "damp-proof membrane", "ocr_confidence": 0.91 }
```

`ocr_confidence` is included so Claude can factor low-fidelity OCR into its certainty estimate. It is not included in the system prompt because it varies per region.

### Why drawing context belongs in the user turn

The drawing-type hint helps Claude pick the right register (e.g. "blinding concrete" vs "blinding layer" depending on whether it is a structural or architectural section). It is derived at the orchestration layer from Nour's detected language and any title-block inference from the full OCR pass. Because it changes per job, it must sit after the last cache breakpoint.

---

## 2. Prompt caching strategy

The cache key is the rendered bytes of `tools + system + messages` up to each `cache_control` breakpoint. The strategy exploits the fact that most cost is in the system prompt, which can be shared across all regions in a single job and, for the same language pair, across successive jobs.

### Breakpoint placement

```
tools         (empty for this call — no function-calling)
system
  ├─ Section A  [role + domain framing]               } COMBINED
  └─ Section B  [glossary for this language pair]     } cache_control: ephemeral
messages
  user turn:    [drawing context + batch of annotations]   ← volatile, NOT cached
```

A single `cache_control: {"type": "ephemeral"}` breakpoint is placed at the end of the system prompt (i.e. on the last text block of `system`). This caches Sections A + B together.

### Why this placement

- Section A is identical across every call the service ever makes. It never changes.
- Section B (the glossary) changes only when the language pair changes or the glossary is updated. For a single job (same user, same drawing), it is the same on every batch call. Caching it together with Section A avoids paying for it repeatedly across the batches of a single job, and across different jobs using the same language pair.
- The user turn (drawing context + annotation batch) changes on every call and must not be cached.

### Minimum prefix length check

The Anthropic API requires at least 1024 tokens for Sonnet-class models before a cache entry is written (4096 for Opus). Section A alone is approximately 120 tokens. The EN→AR glossary at MVP seed size (estimated 150–300 term pairs) will be approximately 600–1200 tokens. The combined system prompt will comfortably exceed the Sonnet minimum on any realistic glossary. If a sparse glossary is used in early development (fewer than ~80 terms), cache writes may silently not occur; this is harmless but should be monitored via `usage.cache_creation_input_tokens` in the response.

### Cache hit verification

Log `usage.cache_read_input_tokens`, `usage.cache_creation_input_tokens`, and `usage.input_tokens` on every API response. During CI and staging, assert that a second call with the same language pair returns `cache_read_input_tokens > 0`. A zero value across repeated calls signals a silent invalidator — most likely the glossary serialization is non-deterministic. Fix: sort glossary entries by `src_term` before rendering.

### TTL choice

Use the default 5-minute TTL for Phase 1. A typical drawing job (OCR + translate) completes in under 2 minutes; the 5-minute window ensures the second and subsequent batch calls within a job hit the cache. If usage patterns show jobs running longer (large complex drawings with many regions), extend to `"ttl": "1h"`.

### Model choice

Use `claude-sonnet-4-6` for Phase 1. It supports prompt caching, handles EN↔AR translation well, and its 1M context window makes it feasible to send all regions in one call for typical drawings. Cost: $3/$15 per million tokens. The Opus tier is unnecessary for a well-constrained translation task with a hard glossary; move to `claude-opus-4-7` only if blind testing against a labelled set reveals Sonnet misses domain terms that Opus catches.

---

## 3. Batching strategy

### Decision: batch all regions in one call per drawing

Rather than one API call per region, send all regions from a drawing in a single call (or the fewest calls possible given the context window).

**Rationale:**

- A typical architectural detail drawing has 10–60 annotations. At approximately 10–30 tokens per annotation, the full batch is well within the 1M context window.
- One call means the system-prompt prefix (including the cached glossary) is paid only once, and caching amortizes across all regions in a single request.
- One call also gives Claude drawing-level context: it sees all annotations at once and can resolve ambiguity across them (e.g. if annotation 3 says "RC slab" and annotation 12 says "reinforced concrete", it can apply consistent terminology).

**Chunking fallback:**

For unusually large drawings (more than approximately 200 annotations, or total annotation tokens exceeding 50K), chunk into batches of 80 regions. Place the `cache_control` breakpoint on the system prompt as described above; the cache remains valid across chunks because the system prompt does not change between chunks of the same job.

**Trade-offs accepted:**

- Larger user-turn payload increases non-cached input tokens slightly vs per-region calls, but the glossary system-prompt cost dominates and that is cached.
- Batch failure (API error) fails all regions at once. Mitigation: retry the entire batch on transient errors (5xx, 429); on repeated failure, fall back to per-region calls so partial results can be returned.

**One-by-one is rejected for Phase 1** because it multiplies the uncached input tokens by N and loses the cross-annotation context benefit, for no gain on a reasonably sized drawing.

---

## 4. Confidence and uncertainty flagging

### Sources of uncertainty

Three distinct sources feed the final `uncertain` flag on each output region:

| Source | Where it comes from | How it propagates |
|--------|--------------------|--------------------|
| Low OCR confidence | `region.confidence < threshold` (from Nour) | Pre-filter: if OCR confidence is below 0.6, mark uncertain before calling Claude at all; include the annotation anyway so Claude sees it, but the flag is set regardless of Claude's output |
| Claude's explicit uncertain flag | Claude sets `"uncertain": true` in its JSON output | Passed through directly |
| Failed JSON parse / missing field | Claude output cannot be parsed or a field is absent | Mark the region uncertain with `reason: "translation_parse_error"` |

### Threshold calibration

The OCR-confidence threshold of 0.6 is a starting point. It must be calibrated against the hand-labelled test set (spec §9). If high-confidence OCR regions still yield bad translations, lower the threshold is not the right fix — that indicates a prompt or glossary issue.

### User-facing surface

The `uncertain` flag and `reason` are stored in the result store (Solove's domain) and surfaced by Zoriaz in the glossary panel as a visual indicator (e.g. a warning icon next to the translation). The user can click through to see the reason. This directly satisfies the MVP success criterion: "low-confidence items flagged for user review."

### Uncertain reason vocabulary

Keep the reason values to a small controlled set so the frontend can render them meaningfully:

- `"low_ocr_confidence"` — OCR returned confidence below threshold
- `"unrecognized_domain_term"` — Claude identified a likely domain term not in the glossary
- `"ambiguous_source_text"` — Claude indicated the source text is ambiguous or possibly malformed
- `"translation_parse_error"` — Claude's output could not be parsed
- `"short_fragment"` — annotation is a single character or symbol, likely non-textual

---

## 5. EN↔AR specifics for Phase 1

### RTL and direction

Arabic is written right-to-left. The `translation` field returned by `Translator.translate` is a plain Unicode string; the directionality is encoded in the characters themselves. The component does not need to add explicit RTL markers. Responsibility for correct RTL rendering lies with Zoriaz (the frontend). The Translator does not add `‫` (RLM) or `dir="rtl"` attributes — those are presentation concerns.

### Arabic register and region variant

The system prompt specifies "Arabic (Gulf region)" as the target locale in the user turn for the MVP. Gulf Arabic is the primary target market (MENA/GCC construction sector). Classical Modern Standard Arabic (MSA) is used as the baseline because architectural specifications in the Gulf are almost universally written in MSA rather than a dialect. The glossary must use MSA terms; the system prompt instructs Claude to use MSA register.

For a future extension to Egyptian or Levantine markets, the user-turn `tgt_label` and the glossary section change; the rest of the prompt is unchanged.

### Arabic OCR caveat

Nour's OCR stage is responsible for extracting Arabic text accurately. However, Arabic OCR on noisy scans is acknowledged in the spec as the central technical risk. When `region.lang == "ar"` and `region.confidence < 0.75` (a higher threshold than for Latin script), the Translator should set `uncertain: true` with reason `"low_ocr_confidence"` even if the default OCR threshold would not trigger. This higher threshold for Arabic is a Phase 1 safety measure pending empirical calibration.

### Bidirectional glossary

Phase 1 requires EN→AR and AR→EN. The glossary from Matt is structured symmetrically. The prompt template is direction-agnostic; the `src` and `tgt` parameters control which direction is rendered into the system prompt. No separate prompt path is needed for each direction.

---

## 6. Determinism and testability

### Low temperature

All Claude API calls use the default (no `temperature` parameter on `claude-sonnet-4-6`, which is adaptive and cannot accept sampling parameters). To maximise reproducibility, use `output_config: {"effort": "low"}`. Low effort on a constrained, well-specified translation task is appropriate and reduces variance without hurting quality for this use case.

Why this matters: the unit tests (below) use golden-output comparison. If outputs vary between runs on identical inputs, golden tests become flaky. Low effort substantially reduces variance; it does not guarantee identical outputs but makes flaky tests rare enough to be useful.

### Golden-output test fixtures

Maintain a test fixture file at `tests/translator/fixtures/en_ar_golden.json` containing:

```json
[
  {
    "id": "test_001",
    "input_text": "damp-proof course",
    "src": "en",
    "tgt": "ar",
    "glossary": [{"src_term": "damp-proof course", "tgt_term": "طبقة عازلة للرطوبة"}],
    "expected_translation": "طبقة عازلة للرطوبة",
    "expect_uncertain": false
  },
  ...
]
```

A golden-output test passes the fixture through `Translator.translate` with the real Claude API (in a slow integration test suite gated by a `RUN_INTEGRATION=1` env var) and asserts:

- `translation == expected_translation` for glossary-bound terms (exact match is acceptable because the glossary term is injected verbatim)
- `uncertain == expect_uncertain`
- The JSON output parses without error

Golden tests for non-glossary terms use a looser assertion: the translation must contain expected domain vocabulary (substring match or a small set of acceptable variants), not an exact string match.

### Mocking the API in unit tests

All unit tests (fast, no network) mock the Claude API at the `anthropic.Anthropic.messages.create` boundary using `unittest.mock.patch` or `pytest-mock`. The mock returns a pre-constructed `Message` object with a hard-coded `content[0].text` value.

Example pattern (Python):

```python
# tests/translator/test_translator_unit.py

from unittest.mock import MagicMock, patch
from translator.translator import Translator

MOCK_CLAUDE_RESPONSE_JSON = '[{"id": 1, "translation": "طبقة عازلة للرطوبة", "uncertain": false, "reason": null}]'

def make_mock_message(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    msg.usage.cache_read_input_tokens = 0
    msg.usage.cache_creation_input_tokens = 500
    msg.usage.input_tokens = 120
    return msg

@patch("anthropic.Anthropic")
def test_glossary_term_translated_exactly(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = make_mock_message(MOCK_CLAUDE_RESPONSE_JSON)

    translator = Translator(client=mock_client)
    regions = [Region(id=1, text="damp-proof course", bbox=..., confidence=0.95, lang="en")]
    glossary = [GlossaryEntry(src_term="damp-proof course", tgt_term="طبقة عازلة للرطوبة")]

    result = translator.translate(regions, src="en", tgt="ar", glossary=glossary)

    assert result[0].translation == "طبقة عازلة للرطوبة"
    assert result[0].uncertain is False
    mock_client.messages.create.assert_called_once()
```

Unit tests must cover:

- Glossary term present → correct canonical translation
- Low OCR confidence → `uncertain: True` regardless of Claude's response
- Claude returns `uncertain: true` → propagated to output
- Claude returns malformed JSON → `translation_parse_error` uncertainty
- Empty region list → empty output, no API call made
- Batch chunking boundary (201 regions → 3 calls, not 2)
- Cache usage fields are logged (assert the logging call was made)

---

## 7. Handling terms not in the glossary

The glossary covers curated architectural terms. Many annotation fragments will not appear in it: dimensions (`2400mm`), reference numbers (`REF A-07`), material callouts not yet in the glossary (`Rockwool 035`), and general construction language.

### Handling strategy

**For unrecognized fragments that appear to be domain terms:**  
The system prompt instructs Claude to translate using its knowledge of architectural practice in the target locale and set `uncertain: true` with reason `"unrecognized_domain_term"`. This surfaces them for user review without blocking the translation.

**For non-textual or purely numeric fragments:**  
Symbols (`@`, `Ø`, `≈`), dimension strings (`300 × 200`), reference tags (`A-1`), and part numbers should be passed through unchanged. The system prompt must explicitly state this:

```
For annotations that are purely numeric, dimensional (e.g. "300 × 200"),
reference tags (e.g. "REF-07", "A-1"), or mathematical symbols, return
the original text unchanged as the translation. Do not attempt to
translate these. Set uncertain: false.
```

**For partial matches:**  
If "reinforced concrete slab" is not in the glossary but "reinforced concrete" is, Claude will use the glossary term for the matched portion and apply its architectural knowledge to complete the phrase. This is acceptable behavior and will be validated in the golden-output test set.

**Glossary growth loop:**  
When `uncertain: true` and `reason: "unrecognized_domain_term"` appears repeatedly for the same source term across multiple drawings, that term is a candidate for Matt's glossary. The result store should track uncertain translations; a reporting query can surface the most frequent unrecognized terms for glossary curation. This is a data pipeline concern, not a Translator concern, but the Translator must emit the right signals to make it possible.

---

## 8. Ordered task list

Tasks are sequenced to unblock integration with Nour and Matt as early as possible.

### Sprint 1 — Skeleton and unit tests

1. Define `Region`, `GlossaryEntry`, and `TranslationResult` dataclasses (or Pydantic models) — agree types with Nour (OCR adapter) and Solove (result store).
2. Implement `Translator` class skeleton with the correct interface signature.
3. Write the full unit test suite (mocked) from the specification above. All tests fail at this point — this is TDD.
4. Implement prompt-building functions: `build_system_prompt(src, tgt, glossary)` and `build_user_turn(regions, src_label, tgt_label, drawing_type_hint)`.
5. Implement JSON response parsing and error handling (malformed output → parse error uncertainty).
6. Make all unit tests pass against the mocked client.
7. Add logging for cache usage fields (`cache_read_input_tokens`, `cache_creation_input_tokens`).

### Sprint 2 — Integration and caching

8. Wire up the real `anthropic` Python SDK client with `claude-sonnet-4-6` and `output_config: {"effort": "low"}`.
9. Add the `cache_control: {"type": "ephemeral"}` breakpoint to the system prompt rendering.
10. Write integration tests (behind `RUN_INTEGRATION=1`) against the real API.
11. Populate the EN↔AR golden-output fixture with 20+ real architectural terms from Matt's seed glossary.
12. Verify cache hits in integration tests (`assert usage.cache_read_input_tokens > 0` on second call with same glossary).
13. Implement chunking fallback for large batches (>80 regions).

### Sprint 3 — AR specifics, edge cases, and handoff

14. Validate Arabic RTL output: pass several translations to Zoriaz for visual rendering check (does the text display correctly in the glossary panel?).
15. Calibrate the Arabic OCR confidence threshold (0.75 starting point) against Nour's benchmark test set.
16. Add the short-fragment passthrough logic (numeric / dimensional / reference tags).
17. Implement the uncertain-term logging hook so Solove can record them in the result store for glossary growth telemetry.
18. Run the full golden-output suite against the hand-labelled test set (spec §9). Report accuracy.
19. Write the integration test that asserts end-to-end: `Translator.translate` → result includes correct glossary terms → uncertain flags present where expected.
20. Handoff review with Kian (Technical Expert): interface compliance, caching verification, test coverage.

---

## 9. Risks and open questions

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Claude produces non-JSON output | Medium | Retry once with explicit instruction "Your previous response was not valid JSON. Return only the JSON array."; on second failure mark all regions as parse-error uncertain |
| Glossary too sparse → many `unrecognized_domain_term` flags at MVP | Medium | Seed glossary with the 200 most frequent architectural terms in EN↔AR drawings before first user testing; track which terms appear most often as unrecognized |
| Cache not hitting across batches of the same job | Low | Ensure glossary serialization is sorted and deterministic; verify in integration tests before Sprint 2 handoff |
| Arabic OCR quality from Nour below threshold for most annotations | High | Translator correctly flags them as low-confidence but cannot improve OCR quality; this risk is owned by Nour and Omar. If more than 30% of regions arrive with low OCR confidence, the product experience is poor regardless of translation quality — this is a joint risk to flag to Abdo |
| Rate limits on high-volume batch calls | Low | Claude's SDK retries automatically on 429; add a per-job concurrency limit in Vivek's job queue to prevent a single large drawing from consuming all quota |
| User mistakes a wrong translation for a correct one (liability) | Medium | Visible confidence flags and "reference aid, not certified source" disclaimer (spec §10) are the product-level mitigations; the Translator's role is to emit reliable uncertainty signals, not to provide legal cover |
| `claude-sonnet-4-6` insufficient for difficult Arabic domain terms | Low-Medium | Validate against the hand-labelled test set; if accuracy falls short, switch to `claude-opus-4-7` (at ~5× cost) for the translation stage only — the modular interface makes this a one-line change |

### Open questions

1. **Drawing-type hint source:** Who provides `drawing_type` for the user turn? The spec says it can be inferred from OCR output (title block). Is this Nour's responsibility (OCR adapter) or Vivek's (orchestrator)? Recommend: Vivek infers it from Nour's full OCR output and passes it to `Translator.translate` as an optional parameter (defaults to `"unknown"`).

2. **Glossary version pinning:** If Matt updates the glossary between two batches of the same job (unlikely but possible), the cached system prompt may be stale. Recommend: the orchestrator fetches the glossary once per job at job-creation time and passes the snapshot to the Translator. The Translator does not call Matt's Glossary store directly.

3. **Arabic numeral handling:** In Arabic, numerals are sometimes written in Eastern Arabic digits (٠١٢٣٤٥٦٧٨٩) and sometimes in Western digits. Architectural drawings from the Gulf typically use Western digits. The passthrough rule for numeric fragments handles this, but if a mixed string appears (e.g. "طبقة ٥٠مم"), Claude should translate the text part and leave the numeral unchanged. Confirm this is correct behavior with Abdo before implementation.

4. **Confidence score output from Claude:** The JSON schema described above does not include a numeric translation confidence score from Claude, only a boolean `uncertain` flag. A numeric score would give the frontend more granularity. Decision deferred: start with boolean (simpler, sufficient for MVP); if user testing shows demand for gradients, add a `translation_confidence` float in a follow-up sprint.

5. **Handling multi-line annotations:** Some drawing annotations span multiple lines. Nour's OCR adapter may return these as a single region or as multiple regions. The Translator treats each region as one translation unit. If a multi-line annotation is split into separate regions by OCR, translations of the parts may be grammatically incomplete. This edge case should be raised with Nour: can the OCR adapter optionally merge adjacent same-bbox-column regions? If not, the Translator accepts fragmented input and translates each fragment as-is, which may produce awkward partial translations. Flag uncertainty in that case.
