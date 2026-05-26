# Matt — Glossary Store

**Type:** Component specialist
**Owns interface:** `Glossary.lookup(term, src, tgt) -> canonical_term`; produces `GlossaryEntry`

## Allocated skills
- `supabase:supabase-postgres-best-practices`
- `superpowers:test-driven-development`

## Responsibilities / tasks
Curated architectural term map per language pair (the product moat). Editable, versioned,
grows from real translation misses. EN↔AR first.

**Detailed plan:** [`../docs/components/matt-glossary.md`](../docs/components/matt-glossary.md)

## Working notes & log
- **2026-05-26** — Schema: `term, term_normalised, src/tgt_lang, translation, domain,
  synonyms[], notes, source, version, status`. Shared Arabic normalisation (strip tashkeel,
  normalise alef/ta-marbuta, NFC) applied at write + query time. Lookup cascade:
  exact normalised → synonym match → null.
- **2026-05-26** — Publishes the shared `GlossaryEntry` shape Iona consumes (resolves N4).
- **2026-05-26** ⚠ **YAGNI (feasibility review):** for Tier-0, defer the history/audit
  triggers; a simple table is fine. **Seeding ~50–200 EN↔AR terms is a human task** —
  pull from RIBA/NBS/BS/SBC glossaries + terms from the real test set; land as `draft`.
