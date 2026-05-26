# Project Review — Abdo (PM) + Lead

**Authors:** Abdo (Project Manager) & Claude (Lead)
**Date:** 2026-05-26
**Reviewed:** the spec, the team charter, all 7 component plans, and Kian's technical review.
**Purpose:** Best-practice review of all the work and the proposed plan; issue a go/no-go decision and the path to implementation.

---

## 1. Decision: CONDITIONAL GO

The seven component plans are individually strong, the architecture is sound, and
the tech choices are consistent. **We do not start coding yet.** We ratify Kian's
verdict: the plans were written in isolation and **diverged on the shared data
contract**, including one high-severity coordinate-space defect (Kian B1) that
would silently break every overlay if shipped.

**Gate to GREEN:** complete the four-step "Contract Freeze" in §3 below. That is a
paper exercise measured in hours, not days. Once done, implementation is approved.

We fully **adopt Kian's rulings B1–B4 and recommendations N1–N9 as binding.** This
review does not re-litigate them; it adds the process, sequencing, ownership, and
acceptance discipline a PM is responsible for.

---

## 2. What the review process itself taught us (root cause)

The divergence wasn't sloppiness — it was a **process gap**: we parallelized seven
specialists against an under-specified interface (spec §3 named the interfaces but
not their field-level schema). Lesson, applied immediately below:

> **Contract-first, then parallel.** Shared interfaces are frozen as code *before*
> independent work resumes. Parallelism is only safe across a stable contract.

This is also the single most valuable thing the multi-agent exercise produced: it
surfaced the integration risk on paper, for the price of seven plan documents,
instead of after a month of code. That is the exercise working as intended.

---

## 3. The Contract Freeze (the only thing blocking GREEN)

Owner: **Vivek**, reviewed by **Kian + Abdo**. Sequence:

1. **Vivek** encodes Kian §2 (canonical `Region`, wire result object, job-status
   enum, coordinate space) as Pydantic models in `tests/contracts/`. This module is
   the **single source of truth**; Nour, Iona, Solove, Zoriaz import or mirror it.
2. **Omar + Vivek** resolve the normalized-image format and **DPI floor** (Omar's
   upscale cap vs Nour's ≥300 DPI expectation, Kian N6/per-component) — this blocks
   Solove's region schema.
3. **Matt** publishes the canonical `GlossaryEntry` shape that **Iona** consumes
   (Kian N4); Iona adds `glossary_hit`/`canonical_term` to her output (N5).
4. Each specialist makes the **one-line edit** to their plan pointing at the frozen
   contract (no rewrites — just adopt the canonical names). Kian + Abdo sign off.

When all four are done, the contract is frozen and any later change requires a
version bump + Kian/Abdo approval.

---

## 4. Best-practice build sequence (after freeze)

We mandate a **walking skeleton first**, not component-by-component perfection. This
is the highest-leverage best practice for a pipeline system: prove the *integration*
end-to-end before deepening any one stage.

**Stage 0 — Walking skeleton (vertical slice).** Upload → pre-process (pass-through)
→ OCR (stub returns fixed regions) → translate (stub echoes) → store → frontend
renders the glossary view, all against the frozen contract. Owner: Vivek coordinates;
every specialist supplies a trivial stub. *Exit:* a real image round-trips and the
UI shows placeholder regions correctly positioned. This validates B1/B2/B3/B4 in
running code before real effort is spent.

**Stage 1 — Deepen along the critical path** (dependency order):

```
Omar (pre-proc) ─▶ Nour (OCR + engine A/B) ─▶ Iona (translate)
        ▲                    ▲                      ▲
   Matt (glossary) ──────────┘                      │
   Solove (store) ◀── Vivek (orchestration) ───────┘
   Zoriaz (frontend) ◀── Solove read API
```

Critical path is **Omar → Nour → Iona** (each consumes the previous), gated by the
**shared Arabic test set** (see §5). Matt, Solove, Vivek, and Zoriaz can deepen in
parallel once their contract dependency is met.

**Stage 2 — Accuracy hardening:** run Nour's engine A/B against the test set, tune
Omar's pre-processing by CER ablation, select the OCR engine, seed/curate Matt's
glossary from real misses. *Exit:* end-to-end CER ≤ 0.15 on the Arabic set (§5).

---

## 5. PM action items (owners assigned)

| # | Item | Owner | Why it's a PM item |
|---|------|-------|--------------------|
| A1 | **Build the hand-labelled test set** (≥20 real drawings: ≥10 Arabic, mix of photos + scans), define label format | **Abdo** (curate) + Omar/Nour (format) | Referenced by 4 plans, owned by none (Kian gap). Blocks the accuracy bar. |
| A2 | **One CER number, one set:** Phase-1 acceptance **CER ≤ 0.15 end-to-end** on the selected engine; Nour's <0.10 is an internal engine-selection goal; bbox IoU/rotation are Phase-2 gates | Abdo | Resolves Omar(0.15)/Nour(0.10) target conflict (N6). |
| A3 | Make Nour's **Arabic escalation path** (pre-proc → ensemble → fine-tune PaddleOCR) visible and budgeted before engine selection | Abdo + Nour | Central project risk; needs a decision owner. |
| A4 | Assign **multi-region term fragmentation** to a single owner (Nour: merge adjacent same-line short regions) | Abdo | Triple-hedged, unowned (N9). |
| A5 | Confirm **YAGNI deferrals** stay out of Phase 1: DZI tiling (cap upload at 10 MP, serve `processed_url` directly), webhooks, multi-page PDF, char-level boxes | Abdo | Scope control. |

## 6. Definition of Done (every component)

A component is "done" only when: (1) it implements the **frozen contract** exactly;
(2) it has tests written first (TDD) with the API/engine mocked; (3) for Omar/Nour,
it reports measured accuracy against the shared test set; (4) Kian has reviewed it;
(5) it integrates green in the walking-skeleton harness. **No "it works" claim
without evidence** (per `verification-before-completion`).

## 7. Risk register (top risks, with owners)

| Risk | Severity | Owner | Mitigation |
|------|----------|-------|------------|
| Arabic OCR accuracy on noisy scans | **High** | Nour | Engine A/B + Omar pre-proc + benchmark gate + escalation path (A3) |
| Contract drift recurring | High (now mitigated) | Vivek | Contract-first freeze (§3); `tests/contracts/` as single source |
| Coordinate-space misalignment (B1) | High | Solove + Zoriaz | Display processed image; one coordinate space (ruled) |
| Per-use API cost at scale | Medium | Vivek/Iona | Prompt caching (Iona), per-user quotas, swappable stages for later self-host |
| Trust/liability of a wrong translation | Medium | Lead/Abdo | Position as learning aid; surface confidence; codes link-not-reproduce |
| Unclear monetization | Medium | Lead/Abdo | MVP doubles as demand validation across the scaling ladder before heavy spend |

## 8. Strengths confirmed

- Architecture honours the swappable-stage pipeline; no hidden coupling beyond the
  (now-fixed) schema drift.
- Async job model with partial-failure handling is correct (user always gets max
  usable output).
- The moat (Matt's curated, versioned, miss-driven glossary) and the cost discipline
  (Iona's prompt caching) are genuine best-practice differentiators.
- Scaling ladder is designed in (stateless workers, RLS multi-tenancy, quotas) — not
  bolted on. No rewrite needed between solo → university tiers.
- Legal caveat (no full building-code text) respected; no scope creep into Phase 2+
  beyond inert, well-marked hooks.

## 9. Next step

Execute the **Contract Freeze (§3)**. On sign-off, this moves from planning to
implementation, and the next artifact is a written implementation plan (the
`writing-plans` workflow) built around the walking-skeleton-first sequence in §4.
