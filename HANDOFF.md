# HANDOFF / RESUME — Imagemaster-Translate

**Purpose:** the single document to read to resume work after a context reset. If you
are a fresh session: **read this file first, then `docs/team/CONTRACT.md` and
`docs/team/feasibility-review.md`**, and you have everything you need.

**Last updated:** 2026-05-26

---

## 1. What this project is
A web tool that OCRs international architectural detail drawings and **translates the
text annotations** (English↔Arabic first), shown as a side-by-side, click-to-locate
**glossary** (Phase 1). Later: in-place overlay + building-codes reference (P2),
explain/teach (P3), standards cross-ref (P4), DWG reconstruction (P5).

## 2. Where everything lives
- **Project folder:** `\\Homex\home\DEVproject\Career master\Imagemaster-translate`
- **GitHub:** https://github.com/arb20ae/Imagemaster-translate (branch `main`)
- **Map of docs:** see `README.md`. Key files:
  - `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md` — design + SWOT
  - `docs/team/CONTRACT.md` + `tests/contracts/contracts.py` — **frozen canonical contract (authoritative)**
  - `docs/team/kian-technical-review.md` — technical review
  - `docs/team/abdo-lead-review.md` — PM/lead review & decision
  - `docs/team/feasibility-review.md` — independent feasibility audit (**read this**)
  - `agents/` — per-agent role, skills, and working notes
  - `docs/components/` — detailed per-component plans

## 3. Status (as of last update)
- ✅ Design spec written & approved.
- ✅ 9-persona team defined (`agents/`); 7 component plans written.
- ✅ Technical review done; **canonical contract FROZEN** and verified (`pytest` 5/5 pass).
- ✅ Independent feasibility audit done → **CONDITIONAL GO** with re-sequencing.
- ⛔ **No application code yet** (only the contract layer + tests).

## 4. Key decisions already made (don't re-litigate)
- Bboxes live in **pre-processed image pixel space**; frontend renders `processed_url` (B1).
- One canonical region schema: `w/h`, single `bbox.angle`, flat `translation` (B2).
- Raw `confidence` always on wire; Nour owns `low_confidence`, Iona owns `uncertain` (B3).
- Frozen job-status enum: `queued|preprocessing|ocr|translating|done|failed` (B4).
- Accuracy bar: **end-to-end CER ≤ 0.15** on a shared Arabic test set.
- Pre-proc: 300 DPI target, 2× cap, PNG, `low_res_warning` < ~200 DPI.

## 5. ⚠ Open decisions / what the OWNER must do (from feasibility audit)
1. **Acquire + hand-label a real Arabic test set** (~15–20 drawings, photos + scans). Gates everything. Human task.
2. **Set hard billing spend caps** on any OCR/Claude accounts before the first API call.
3. Decide automation for the handoff/auto-markdown system (see §7 — pending your choice).

## 6. Recommended NEXT STEP (changed by the feasibility audit)
**Run the Arabic-OCR spike FIRST**, before building the app:
- Throwaway script, no backend/DB/queue. Feed real Arabic drawings through 2–3 OCR
  engines (Google Document AI / Azure DI / Mistral OCR), with and without Omar's
  pre-processing. Measure **CER**.
- **Decision gate: GO / PIVOT / STOP.** Only build the walking skeleton if CER clears ~0.15.
- Then: thinnest walking skeleton (synchronous, no queue, local storage), then deepen
  along Omar → Nour → Iona.

Before coding the app, apply the contract-alignment fixes flagged in each agent's notes
(`agents/zoriaz.md`, `agents/iona.md`, `agents/solove.md` especially).

## 7. Continuity system (this file + automation)
- This `HANDOFF.md` + git history + the `agents/*.md` notes are the durable memory.
- ✅ **Auto-resume is ACTIVE.** A `SessionStart` hook in `.claude/settings.json` auto-loads
  this file into context at the start of every new session **opened in this project folder**
  (`Career master/Imagemaster-translate`). No command needed.
- To **refresh** this file's contents, ask: *"update the handoff"* (the hook loads whatever
  this file says, so keep it current at the end of a work session).
- Optional, not yet set up: auto-commit-on-Stop hook, and a daily `/schedule` snapshot.
- Manual fallback (always works): *"read HANDOFF.md and continue."*
