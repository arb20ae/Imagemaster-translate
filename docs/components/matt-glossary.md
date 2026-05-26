# Glossary Store — Phase-1 Component Plan

**Owner:** Matt  
**Date:** 2026-05-26  
**Status:** Draft — pending Kian / Abdo review  
**Interface provided:** `Glossary.lookup(term, src, tgt) -> canonical_term`  
**Reference spec:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`  
**Reference team:** `docs/team/TEAM.md`

---

## Role in the pipeline

The Glossary Store is the product moat. It is a curated map of architectural and
construction terms per language pair. At Phase 1, the language pair is English <-> Arabic.

Every translation call from Iona's Translator stage injects the relevant glossary
slice, ensuring terms like *screed*, *soffit*, *damp-proof course*, *blinding*, *RCC*,
and *pile cap* reach the LLM as correct, verified industry equivalents — not as
guesses from general-purpose machine translation.

The store is also the compounding asset: every new term added, every correction, and
every domain expansion grows the moat. Versioning and status tracking ensure that
growth is measurable and auditable.

---

## 1. Data Schema

### 1.1 Core table: `glossary_terms`

```sql
CREATE TABLE glossary_terms (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The source term exactly as it should appear or be looked up
    term            TEXT        NOT NULL,
    -- Normalised form used for lookup (lowercase, diacritic-stripped, Unicode NFC)
    term_normalised TEXT        NOT NULL,

    -- BCP-47 language tags: 'en', 'ar', 'de', etc.
    src_lang        TEXT        NOT NULL,
    tgt_lang        TEXT        NOT NULL,

    -- The canonical translation to inject into the LLM prompt
    translation     TEXT        NOT NULL,

    -- Architectural sub-domain for filtering and future phase expansion
    -- e.g. 'structural', 'finishes', 'waterproofing', 'mep', 'soil', 'concrete'
    domain          TEXT        NOT NULL DEFAULT 'general',

    -- Comma-separated or JSONB array of alternate spellings / abbreviations
    -- stored as TEXT[] for easy containment queries
    synonyms        TEXT[]      NOT NULL DEFAULT '{}',

    -- Curator notes: source provenance, usage context, disputed terms, etc.
    notes           TEXT,

    -- Where the translation came from
    -- e.g. 'RIBA_glossary', 'BS_8000', 'expert_review', 'ai_proposed'
    source          TEXT        NOT NULL DEFAULT 'manual',

    -- Monotonically increasing integer bumped on every edit to this row
    version         INTEGER     NOT NULL DEFAULT 1,

    -- 'active' | 'draft' | 'deprecated'
    status          TEXT        NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'draft', 'deprecated')),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent exact duplicate (term, src_lang, tgt_lang) triples
    CONSTRAINT uq_term_lang_pair UNIQUE (term_normalised, src_lang, tgt_lang)
);
```

**Why these columns:**

| Column | Reason |
|--------|--------|
| `term` / `term_normalised` | Separates display form from lookup key; normalisation handles Arabic diacritic variants and case differences in Latin scripts. |
| `src_lang` / `tgt_lang` | Explicit direction: EN->AR and AR->EN are separate rows, allowing different translations and curator notes per direction. |
| `translation` | The canonical string injected verbatim into the LLM prompt. |
| `domain` | Enables bulk-fetch filtering (e.g. send only `structural` + `finishes` terms for a foundation detail). Future: per-domain accuracy metrics. |
| `synonyms` | Captures abbreviations (`DPC` for `damp-proof course`), alternate spellings, and legacy terms. Drives synonym-aware lookup. |
| `notes` | Provenance and usage guidance for curators; not surfaced to end users in Phase 1. |
| `source` | Provenance trail. Distinguishes hand-curated entries from AI-proposed ones that need review. |
| `version` | Row-level version counter. Incremented on every UPDATE. Feeds audit log and cache invalidation. |
| `status` | Soft-delete / draft workflow. Only `active` entries are returned by `Glossary.lookup`. |

### 1.2 Audit / history table: `glossary_term_history`

```sql
CREATE TABLE glossary_term_history (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    term_id         UUID        NOT NULL REFERENCES glossary_terms(id),

    -- Snapshot of the row at the moment of change
    term            TEXT        NOT NULL,
    term_normalised TEXT        NOT NULL,
    src_lang        TEXT        NOT NULL,
    tgt_lang        TEXT        NOT NULL,
    translation     TEXT        NOT NULL,
    domain          TEXT        NOT NULL,
    synonyms        TEXT[]      NOT NULL,
    notes           TEXT,
    source          TEXT        NOT NULL,
    version         INTEGER     NOT NULL,
    status          TEXT        NOT NULL,

    changed_by      TEXT,       -- user or system identifier
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    change_reason   TEXT        -- optional curator comment
);
```

**Why a separate history table rather than a single-table approach:**
- The live `glossary_terms` table stays lean for fast lookups.
- History rows are append-only; no UPDATE contention on the audit trail.
- The full change log is queryable for any term at any version without table scans on the hot path.

A Postgres trigger on `glossary_terms` writes to `glossary_term_history` before every UPDATE or DELETE, capturing the old row.

### 1.3 Indexes

```sql
-- Primary lookup index: normalised term + direction
CREATE INDEX idx_glossary_lookup
    ON glossary_terms (src_lang, tgt_lang, term_normalised)
    WHERE status = 'active';

-- Domain filter (bulk-fetch by domain + language pair)
CREATE INDEX idx_glossary_domain
    ON glossary_terms (src_lang, tgt_lang, domain)
    WHERE status = 'active';

-- GIN index for synonym array containment queries
CREATE INDEX idx_glossary_synonyms
    ON glossary_terms USING GIN (synonyms);
```

All three are partial indexes on `status = 'active'` — following the Supabase/Postgres
best-practice of partial indexes to keep index size minimal and cache-friendly on the
hot path (only active terms are ever looked up at runtime).

---

## 2. Lookup Design

### 2.1 `Glossary.lookup(term, src, tgt) -> canonical_term`

The lookup contract is intentionally simple for the caller (Iona's Translator). Internally
it applies a resolution cascade:

```
1. Exact normalised match:
   SELECT translation FROM glossary_terms
   WHERE term_normalised = normalise(term)
     AND src_lang = src AND tgt_lang = tgt
     AND status = 'active'
   LIMIT 1;

2. Synonym match (if step 1 misses):
   SELECT translation FROM glossary_terms
   WHERE normalise(term) = ANY(synonyms)
     AND src_lang = src AND tgt_lang = tgt
     AND status = 'active'
   LIMIT 1;

3. Miss -> return NULL (caller treats as "no glossary override").
```

A miss is a clean NULL; Iona falls back to pure LLM translation for that term. This
is the correct behaviour — the glossary enforces terms it knows about, stays silent
on unknowns.

### 2.2 Normalisation function

Arabic diacritic normalisation is the hardest part of the lookup. The same root word
may appear with tashkeel (short vowel marks), without them, in different Unicode
normalisation forms, or with variant characters (alef forms, ta marbuta, etc.).

A shared `normalise(text, lang)` utility is applied consistently at:
- Write time: `term_normalised` is computed on INSERT/UPDATE.
- Read time: the query input is normalised before the SELECT.

**For Arabic (`ar`):**
- Apply Unicode NFC normalisation.
- Strip tashkeel (harakat): Unicode block U+064B–U+065F and U+0670.
- Normalise alef variants (آ أ إ ا → ا), ta marbuta (ة → ه), and alef maqsura (ى → ي).
- Collapse multiple whitespace.
- Lowercase (Arabic has no case, but mixed Arabic-Latin terms may include Latin parts).

**For English (`en`):**
- Lowercase.
- Strip leading/trailing whitespace; normalise internal whitespace.
- Unicode NFC.

This normalisation is implemented as a Python utility function (`glossary/normalise.py`)
that is called by both the seeding script and the lookup path. The Postgres
`term_normalised` column is populated by the application layer, not a DB function,
so the same normalisation logic is always in one place.

### 2.3 Multi-word terms

Multi-word terms (e.g. "damp-proof course", "reinforced concrete column") are stored
as full phrases in `term` / `term_normalised`. Lookup is phrase-level, not word-level.
OCR regions often capture full annotations as a phrase, so phrase-level lookup is the
right default.

A future Phase-2 enhancement can add word-level tokenisation and partial-phrase matching,
but that complexity is out of scope for Phase 1.

### 2.4 Morphological variants (Arabic)

Arabic has rich morphology (prefixes, suffixes, root-based derivations). Full stemming
is deferred to Phase 2. Phase 1 mitigates with:
- Synonym entries for the most common inflected forms of high-value terms.
- Seeding both forms explicitly (e.g. construct noun and verbal noun variants where both
  appear in real drawings).
- An "open question" flag in this plan (see §9) for when stemming becomes necessary.

---

## 3. Seeding Strategy

### 3.1 Initial seed (~50–200 terms)

**Sources (in priority order):**

1. **RIBA architectural glossary / NBS (National Building Specification) term lists.**
   Freely available online; covers UK/international standard terms.
2. **BS 8000 (Workmanship on Building Sites) index terms** — widely used reference;
   terms appear verbatim on UK and Gulf drawings.
3. **Saudi Building Code (SBC) and SASO published glossaries** — Arabic-first, high
   relevance for MENA/Gulf market.
4. **Expert review pass.** A practising architect or structural engineer reviews the
   initial list for accuracy and adds missing domain terms.
5. **Drawn from the hand-labelled test set** (the real drawings used for OCR accuracy
   benchmarking per spec §9). Every annotation in the test set that is a domain term
   is a candidate for the glossary.

**Seed process:**
- Maintain the master seed list as a CSV in `data/seed/glossary_en_ar_seed.csv`
  with columns matching the schema.
- A `scripts/seed_glossary.py` script reads the CSV and inserts rows with
  `source='seed_v1'`, `version=1`, `status='active'`.
- The script is idempotent: on conflict (`term_normalised`, `src_lang`, `tgt_lang`)
  it skips or updates, never duplicates.

### 3.2 Growth and curation workflow

**Proposed feedback loop (Phase 1+):**
- Iona logs every `NULL` (miss) from `Glossary.lookup` to a `glossary_misses` table
  with the raw OCR term, language pair, and job ID.
- A curator reviews the miss log periodically and promotes high-frequency misses to
  new glossary entries (status `draft` first, then `active` after review).
- The LLM translation of a term can be used as an initial draft (`source='ai_proposed'`),
  but a human must set it to `status='active'`.
- This creates a pull-based curation queue driven by real usage.

---

## 4. Versioning Strategy

### 4.1 Row-level versioning

Each row carries an integer `version` column incremented on every UPDATE. This is
the mechanism for cache invalidation: Iona caches the glossary snapshot at fetch
time with an ETag derived from the maximum `(updated_at, version)` across the
fetched rows. When a row is edited, the max changes and the cache is invalidated.

### 4.2 History table as the audit trail

The `glossary_term_history` trigger provides a full timeline of every change to every
term. This means:
- The glossary's IP accumulation is provably tracked (valuable as a moat argument).
- Rollbacks are possible by restoring a previous history snapshot.
- Accuracy regressions can be diagnosed by comparing translation at time T1 vs T2.

### 4.3 No dataset-level version in Phase 1

A dataset-level semantic version (`v1.0`, `v1.1`) is useful for downstream tooling
(e.g. pinning a specific glossary snapshot for reproducibility). This is deferred to
Phase 2 when there are enough consumers to warrant it. In Phase 1, the row-level
`version` + `updated_at` is sufficient.

---

## 5. Storage Choice: Postgres via Supabase

**Why Postgres:**
- The glossary is a structured, relational dataset with lookup keys, versioning, and
  an audit trail — a classic relational workload.
- Postgres full-text search and GIN indexes for synonym arrays are built-in, removing
  any need for a separate search engine at Phase 1 scale.
- The rest of the pipeline (Solove's result store, Vivek's job queue) also lives in
  Postgres/Supabase, so there is one operational surface to monitor.

**Why Supabase specifically:**
- Managed Postgres removes operational overhead at Tier 0/1 scale.
- Supabase Row-Level Security (RLS) policies can restrict glossary write access to
  curators without application-layer plumbing.
- Supabase provides a REST/PostgREST auto-API; the glossary editor UI (future) can
  call it directly with no extra backend code.
- The scaling ladder in the spec (§7) calls for a managed DB from day one. Supabase
  fits the Render/Railway/Fly.io tier-0 profile and can be migrated later if needed.

**Fast-lookup approach:**
- Partial index on `(src_lang, tgt_lang, term_normalised) WHERE status = 'active'`
  makes the exact-match lookup an index scan on a small, cache-resident structure.
- At 200 terms the full active table easily fits in Postgres shared_buffers.
- At 10,000+ terms (future) the partial index remains O(log n) on the lookup key.
- Supabase connection pooling (PgBouncer) in transaction mode is used so the many
  short-lived glossary lookups do not exhaust connections.

---

## 6. How Iona's Translator Consumes the Glossary

Two access patterns are supported:

### 6.1 Bulk fetch for a language pair (primary pattern)

Before processing a job, Iona fetches the full active glossary for the language pair:

```
GET /glossary?src_lang=en&tgt_lang=ar&status=active
```

This returns all active `(term, translation, synonyms, domain)` rows. Iona builds an
in-memory lookup dict for the duration of the job. This eliminates per-term network
round-trips during translation of a many-region drawing.

Cache invalidation: the response includes an `ETag` (hash of max `updated_at`). Iona
re-fetches only when the ETag changes. At Phase 1 update frequency (manual curation
every few days), the cached dict will be hot for nearly every request.

The bulk fetch is filtered by `domain` when the drawing type is known (e.g. structural
detail), to keep the injected glossary slice small and LLM-prompt-friendly.

### 6.2 Per-term lookup (fallback / testing)

`Glossary.lookup(term, src, tgt)` is the single-term interface from the spec. It is
used in tests, in the curation UI (Phase 2), and as a fallback if bulk fetch is not
yet implemented. It hits the exact-match index directly.

### 6.3 Prompt injection format

The glossary slice is injected into Iona's LLM prompt as a structured block:

```
ARCHITECTURAL GLOSSARY (EN->AR):
screed = الخرسانة العازلة
soffit = السقف السفلي
damp-proof course = الطبقة العازلة للرطوبة
...
Use these translations exactly. Do not paraphrase glossary terms.
```

This format is deterministic and testable: the same glossary + same input yields the
same output (modulo LLM temperature, which Iona sets to 0 for translation).

---

## 7. TDD / Testing Approach

Tests are written before implementation code (per team working agreement).

### 7.1 Unit tests (`tests/glossary/`)

| Test | What it covers |
|------|----------------|
| `test_normalise_arabic` | Strip tashkeel, alef variants, ta marbuta — one test per rule |
| `test_normalise_english` | Lowercase, whitespace normalisation |
| `test_lookup_exact_match` | Returns correct translation for known active term |
| `test_lookup_synonym_match` | Returns correct translation when input is an alias |
| `test_lookup_miss_returns_none` | Returns `None` for unknown term |
| `test_lookup_ignores_draft` | `draft` status rows are not returned |
| `test_lookup_ignores_deprecated` | `deprecated` status rows are not returned |
| `test_lookup_case_insensitive` | `DPC` == `dpc` == `Dpc` |
| `test_lookup_diacritic_insensitive` | Arabic term with tashkeel matches stored form without |

### 7.2 Integration tests (against a test Supabase project or local Postgres)

| Test | What it covers |
|------|----------------|
| `test_bulk_fetch_returns_active_only` | Bulk GET excludes draft/deprecated rows |
| `test_bulk_fetch_domain_filter` | Domain filter returns only matching rows |
| `test_seed_script_idempotent` | Running seed twice does not duplicate rows |
| `test_history_trigger_fires_on_update` | Editing a row writes a history snapshot |
| `test_version_increments_on_update` | Version column increments correctly |

### 7.3 Accuracy regression test

The hand-labelled test set (spec §9) includes the expected translation for each
annotated term. A regression test runs `Glossary.lookup` over all test-set terms and
asserts that glossary hits return the exact expected canonical translation. This
guards against curation regressions: an accidental edit to a high-value term is
caught before deployment.

---

## 8. Ordered Task List

Tasks are sequenced so each one unblocks the next; tests are written first.

| # | Task | Output |
|---|------|--------|
| 1 | Write normalisation utility `glossary/normalise.py` (Arabic + English rules) | `normalise.py` + unit tests |
| 2 | Write failing unit tests for `Glossary.lookup` (all cases in §7.1) | Test file |
| 3 | Author Postgres schema: `glossary_terms`, `glossary_term_history`, indexes, trigger | Migration SQL file |
| 4 | Apply schema to Supabase project (dev environment) | Live DB |
| 5 | Implement `Glossary.lookup` to make unit tests pass (pure Python, no DB yet) | `glossary/lookup.py` |
| 6 | Wire `Glossary.lookup` to Supabase DB; run integration tests | Passing integration tests |
| 7 | Compile EN<->AR seed CSV (~50–100 terms, Phase-1 priority domains) | `data/seed/glossary_en_ar_seed.csv` |
| 8 | Write and run `scripts/seed_glossary.py`; verify idempotence test passes | Seeded DB + test |
| 9 | Implement bulk-fetch endpoint (`GET /glossary`) with ETag caching | Endpoint + integration test |
| 10 | Write accuracy regression test against hand-labelled test set | Regression test |
| 11 | Document `Glossary.lookup` interface for Iona (prompt injection format, bulk fetch contract) | Interface notes in this file |
| 12 | Kian review: schema soundness, index strategy, normalisation completeness | Review sign-off |

---

## 9. Risks and Open Questions

### R1 — Arabic normalisation completeness (HIGH)
The normalisation rules in §2.2 cover the most common variants but Arabic typography
has additional complications: ligatures, Unicode presentation forms (FB50–FDFF,
FE70–FEFF), and OCR engines sometimes emitting presentation-form codepoints rather
than canonical Arabic block codepoints. **Action:** add a presentation-form stripping
step to `normalise()` and test against real OCR output from Nour's adapter before
seeding.

### R2 — OCR term fragmentation (MEDIUM)
If the OCR engine splits a multi-word term across two `Region` objects (e.g. "damp"
and "proof course" as separate regions), phrase-level lookup will miss. This is a
coordination risk with Nour. **Action:** agree on whether Nour's adapter can
merge adjacent short regions before passing to Iona, or whether Iona/Matt must
handle fuzzy multi-region term assembly.

### R3 — Arabic morphological coverage (MEDIUM)
Phase 1 uses synonym entries for common inflected forms. For high-term-count domains
(MEP, structural) this may not scale. **Decision gate:** if miss rate on real drawings
exceeds ~20% after Phase 1 seeding, add an Arabic stemmer (e.g. Farasa or NLTK Arabic
stemmer) to the normalisation path. Do not add it before that threshold — stemming
introduces false matches.

### R4 — Translation direction asymmetry (LOW-MEDIUM)
EN->AR and AR->EN are separate glossary rows. There is a risk of one direction being
updated without the other, creating inconsistency. **Action:** add a DB constraint
or curator UI validation that flags unpaired updates (one direction updated, other not).

### R5 — Seed quality (MEDIUM)
The initial ~50-100 terms are only as good as the sources and the expert review.
A single wrong architectural translation is worse than a miss (Iona falls back to LLM
on a miss; a wrong glossary entry overrides the LLM). **Action:** all seed entries
start `status='draft'`; a domain expert must explicitly set each to `active`.
Expert review is a Phase-1 gate, not a Phase-2 nice-to-have.

### R6 — Supabase free-tier limits (LOW at Phase 1)
At Phase 1 scale (< 1,000 terms, < 10 concurrent users), Supabase free tier is
sufficient. The glossary store itself adds negligible load. Monitor if bulk-fetch
frequency grows with user scale; add HTTP caching (Cache-Control) before DB-level
optimisation.

### Open question — bilingual term display
The spec §9 requires a "click-to-locate glossary" in the frontend. Zoriaz needs to
know if `Glossary.lookup` returns only the canonical translation or also the source
term, domain, and synonyms for the panel. **Proposed:** the bulk-fetch response
returns the full row minus `notes` and internal fields; `Glossary.lookup` returns
only `canonical_term` as specified. Zoriaz reads from the bulk-fetch payload, not
from individual lookup calls.

---

## Interfaces consumed by other components

| Consumer | What they call | What they get |
|----------|---------------|---------------|
| Iona (Translator) | `Glossary.lookup(term, src, tgt)` or bulk fetch | `canonical_term` (str) or `None` |
| Vivek (API/Backend) | Bulk-fetch endpoint at job-start | Full active glossary slice for the language pair |
| Zoriaz (Frontend) | Bulk-fetch (via Vivek's API) | Term + translation + domain for glossary panel |

The Glossary Store does **not** call any other component's interface. It is a
leaf node in the dependency graph.

---

## Appendix A — Sample seed terms (EN -> AR)

A representative sample of the initial seed list. Full list in
`data/seed/glossary_en_ar_seed.csv` (to be created in Task 7).

| English term | Arabic translation | Domain | Synonyms |
|---|---|---|---|
| screed | طبقة التسوية | finishes | levelling screed |
| soffit | السطح السفلي | structural | underside |
| damp-proof course | الطبقة العازلة للرطوبة | waterproofing | DPC |
| blinding | طبقة الخرسانة العادية | concrete | blinding concrete |
| reinforced concrete | الخرسانة المسلحة | structural | RCC, RC |
| pile cap | رأس الخازوق | structural | — |
| retaining wall | الجدار الاستنادي | structural | — |
| cavity wall | جدار التجويف | masonry | — |
| lintel | العتب | structural | — |
| coping | الطنف | masonry | coping stone |
| parapet | الجدار الواقي | structural | — |
| expansion joint | فاصل التمدد | structural | movement joint |
| waterproofing membrane | غشاء العزل المائي | waterproofing | — |
| aggregate | الركام | concrete | coarse aggregate |
| formwork | الشدة الخشبية | concrete | shuttering |

*This sample is indicative only. The real seed CSV will be compiled with expert review
(see §3.1 and Risk R5).*
