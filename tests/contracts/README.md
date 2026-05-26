# `tests/contracts/` — the single source of truth

`contracts.py` holds the **canonical** Pydantic models for every shape that crosses
a component boundary in Phase 1. It is owned by Vivek (backend) and ratified by Kian
+ Abdo. **Every component imports these models** rather than redefining its own:

- **Nour** (OCR adapter) produces `Region` (writes `text, bbox, confidence, lang, region_index, low_confidence`).
- **Iona** (translator) fills the translation fields on `Region` (`translation, translation_confidence, uncertain, uncertain_reason, glossary_hit, canonical_term`) and consumes `GlossaryEntry`.
- **Matt** (glossary) produces `GlossaryEntry`.
- **Solove** (result store) persists regions and serves `JobResult` / `JobStatusResponse`.
- **Zoriaz** (frontend) mirrors `JobResult` / `JobStatusResponse` as TypeScript types and renders `ImageRef.processed_url`.

## Rules

1. Changing any model requires a **version bump + Kian/Abdo sign-off**.
2. Bboxes are always in **pre-processed image pixel space** (see `contracts.py` docstring).
3. The raw `confidence` float always crosses the wire; `low_confidence` (bool) is the
   authoritative OCR flag (owned by Nour); `uncertain` is the translation flag (owned by Iona).

## Run the smoke tests

```bash
pip install -r requirements.txt   # pydantic
pytest tests/contracts/
```
