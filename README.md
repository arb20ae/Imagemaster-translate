# Imagemaster-Translate

A web tool that uses OCR to read **international architectural detail drawings**
and translate their text annotations — helping students, lecturers, tutors, and
contractors understand drawings produced under unfamiliar languages and standards.

- **Phase 1 (MVP):** translate annotations (English ↔ Arabic first) and present a
  side-by-side, click-to-locate **glossary** view.
- **Phase 2:** in-place translation **overlay** + **building-codes reference** for
  the drawing's country of origin.
- **Phase 3+:** explain/teach the detail → standards cross-reference → experimental
  DWG/DXF reconstruction.

## Documentation

| Doc | What it is |
|-----|------------|
| [`docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`](docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md) | The design spec (vision, phasing, architecture, scaling ladder, SWOT) |
| [`docs/team/TEAM.md`](docs/team/TEAM.md) | Team charter — specialists, skills, roles, tasks |
| [`docs/team/CONTRACT.md`](docs/team/CONTRACT.md) | **Frozen** canonical cross-component data contract (single source of truth) |
| [`docs/team/kian-technical-review.md`](docs/team/kian-technical-review.md) | Technical/architecture review |
| [`docs/team/abdo-lead-review.md`](docs/team/abdo-lead-review.md) | PM + lead best-practice review & decision |
| [`docs/components/`](docs/components/) | One Phase-1 plan per pipeline component |

## Architecture (Phase 1)

```
Upload → Pre-process → OCR (text + bboxes) → Glossary-aware Translation
       → Result store → Glossary view   (Phase 2 → Overlay + Building codes)
```

Each stage sits behind a clean, swappable interface. The data that crosses those
boundaries is frozen in [`docs/team/CONTRACT.md`](docs/team/CONTRACT.md) and encoded
as Pydantic models in [`tests/contracts/`](tests/contracts/).

## Status

Planning complete and reviewed. Contract frozen. Next: walking-skeleton vertical
slice, then deepen along the Omar → Nour → Iona critical path.
