# HANDOFF / RESUME — Imagemaster-Translate

> **FRESH SESSION? START HERE.** Read this whole file, then `docs/team/CONTRACT.md` and
> `docs/team/feasibility-review.md`. That's enough to resume with full context. This file
> is auto-loaded by a `SessionStart` hook when this folder is opened as the project.

**Last updated:** 2026-05-26

---

## 1. What this project is
A web tool that OCRs international architectural detail drawings and **translates the text
annotations** (English↔Arabic first), shown as a side-by-side, click-to-locate **glossary**
(Phase 1). Later phases: in-place overlay + building-codes reference (P2), explain/teach
(P3), standards cross-reference (P4), experimental DWG reconstruction (P5). Audience:
students, lecturers, tutors, contractors. Business model: undecided — MVP doubles as
demand validation.

## 2. Environment & gotchas (READ — saves real time)
- **Project folder:** `\\Homex\home\DEVproject\Career master\Imagemaster-translate`
  (NOT `Image master`, which is empty). It's a subfolder of "Career master", which
  separately holds an unrelated "Career Master Gamified Productivity" app — don't mix them.
- **GitHub remote:** https://github.com/arb20ae/Imagemaster-translate.git (branch `main`).
- **Python:** the Bash tool's `python` hits a broken Windows Store stub. Use the real one
  via the **PowerShell tool**: `C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe`.
  Run tests with `$env:PYTHONPATH=<repo>; & $py -m pytest <repo>\tests\... -q`.
- **UNC path quirks:** git needs `safe.directory` set (already done); git warns
  "LF→CRLF" (harmless); pytest can't write its cache to the network drive (harmless warning).
- **Auto-resume hook** lives in `.claude/settings.json` (SessionStart → cats this file).

## 3. Status
- ✅ Design spec, 9-persona team (`agents/`), 7 component plans.
- ✅ Technical review + PM review + independent feasibility review — all done.
- ✅ **Canonical contract FROZEN & tested** (`tests/contracts/contracts.py`, `pytest` 5/5).
- ✅ Continuity system: this file + `agents/*.md` notes + git + auto-resume hook.
- ⛔ **No application code yet** (only the contract layer + tests).

## 4. Map of the repo
- `README.md` — overview + doc index.
- `docs/superpowers/specs/2026-05-26-...-design.md` — design + SWOT.
- `docs/team/CONTRACT.md` + `tests/contracts/contracts.py` — **frozen contract (authoritative)**.
- `docs/team/kian-technical-review.md` — technical review (rulings B1–B4).
- `docs/team/abdo-lead-review.md` — PM/lead review & decision.
- `docs/team/feasibility-review.md` — independent feasibility audit (**important**).
- `agents/` — per-agent role, skills, and dated working-notes log (incl. contract-alignment TODOs).
- `docs/components/` — detailed per-component plans (note: some still describe pre-freeze
  schema; the contract supersedes them — see alignment notes in `agents/`).

## 5. Key decisions already made (don't re-litigate)
- Bboxes in **pre-processed image pixel space**; frontend renders `image.processed_url` (B1).
- One region schema: `bbox{x,y,w,h,angle}` (not width/height; one angle field), flat
  `translation`, `text`, `region_index`, `lang` (B2).
- Raw `confidence` always on the wire; Nour owns `low_confidence`; Iona owns `uncertain` (B3).
- Job-status enum frozen: `queued|preprocessing|ocr|translating|done|failed` (B4).
- Accuracy bar: **end-to-end CER ≤ 0.15** on a shared Arabic test set.
- Pre-proc: 300 DPI target, 2× upscale cap, PNG output, `low_res_warning` below ~200 DPI.
- API prefix `/api/v1`; external `job_id` = UUID; shared `GlossaryEntry` shape.

## 6. ⚠ What the OWNER (human) must do — these block progress
1. **Acquire + hand-label a real Arabic test set** (~15–20 drawings: mix of phone photos +
   scans). Gates the spike, engine selection, the accuracy bar, and glossary seeding.
2. **Set hard billing spend caps** on any OCR/Claude API accounts BEFORE the first call.

## 7. RECOMMENDED NEXT STEP (per feasibility review)
**Run the Arabic-OCR spike FIRST** — before building the app:
- Throwaway script. NO backend/DB/queue/frontend. Feed the real Arabic drawings through
  2–3 OCR engines (Google Document AI / Azure Document Intelligence / Mistral OCR), with
  and without Omar's pre-processing. Measure **CER**.
- **Decision gate: GO / PIVOT / STOP.** Only build the walking skeleton if CER clears ~0.15.
- Then build the **thinnest** walking skeleton (synchronous, no queue, local storage —
  defer Redis/RQ, Supabase RLS/multi-tenancy, quotas, DZI tiling per the feasibility cuts),
  then deepen along **Omar → Nour → Iona**.
- Before app code: apply the contract-alignment fixes in `agents/zoriaz.md`, `agents/iona.md`,
  `agents/solove.md`.

## 8. How to work this project
- Refresh this file at the end of a work session: say **"update the handoff."**
- Resume after a reset: the hook auto-loads this file; just say what you want to do.
  (Manual fallback: *"read HANDOFF.md and continue."*)
- Optional not-yet-set-up automations: auto-commit-on-Stop hook (free); daily `/schedule`
  snapshot (billed).
