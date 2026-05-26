# Zoriaz — Web Frontend

**Type:** Component specialist
**Owns interface:** consumes the Result-store read API (regions + translations + bboxes)

## Allocated skills
- `frontend-design:frontend-design`
- `superpowers:test-driven-development`
- `chrome-devtools-mcp:a11y-debugging`

## Responsibilities / tasks
Upload UI, large-image drawing viewer (pan/zoom), glossary panel with click-to-locate,
language picker, confidence flags. Phase 2: overlay toggle, building-codes panel.

**Detailed plan:** [`../docs/components/zoriaz-frontend.md`](../docs/components/zoriaz-frontend.md)

## Working notes & log
- **2026-05-26** — Plan decisions: Next.js + Tailwind (RTL-aware), OpenSeadragon viewer,
  Zustand selection store for bidirectional click-to-locate.
- **2026-05-26** ⚠ **CONTRACT ALIGNMENT REQUIRED** (flagged by feasibility review): the
  plan still describes displaying the **original** image — this is exactly the B1 defect
  Kian ruled against. On implementation, MUST:
  - render `image.processed_url` (pre-processed image), not the original;
  - use canonical field names: `w`/`h` (not width/height), `region_index` (not
    reading_order), flat `translation`, single `bbox.angle` (no `is_rotated`);
  - treat the 0.60/0.40 confidence tiers as **presentation only** over the raw float.
- **2026-05-26** — YAGNI: **drop DZI/IIIF tiling** for Phase 1 (cap uploads at 10 MP,
  serve `processed_url` directly).
