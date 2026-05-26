# Zoriaz — Web Frontend Component Plan (Phase 1)

**Owner:** Zoriaz  
**Date:** 2026-05-26  
**Ref spec:** `docs/superpowers/specs/2026-05-26-architectural-drawing-translator-design.md`  
**Ref team:** `docs/team/TEAM.md`  
**Status:** Draft — pending review by Kian and Abdo

---

## 1. Component Responsibilities & Screens

### Screen A — Upload Screen

Single-purpose landing screen. Allows the user to:
- Select or drag-and-drop a drawing image (JPEG, PNG, TIFF, PDF-first-page).
- Choose source language and target language via a language picker (Phase-1 pair: EN ↔ AR).
- Submit the job and enter a loading/polling state.

Upload is fire-and-forget from the frontend's perspective: the frontend POSTs the
image + language selection to the backend (Vivek's API), receives a `job_id`, then
polls for status.

### Screen B — Results Screen (the core Phase-1 view)

Two-panel layout:

| Panel | Content |
|-------|---------|
| Left (drawing viewer, ~65% width) | The original drawing rendered in a large-image tile viewer. Bounding boxes are drawn as an SVG overlay. The bbox matching the active glossary entry is highlighted. |
| Right (glossary panel, ~35% width) | Scrollable list of translation pairs, ordered by reading order (top-to-bottom of drawing). Each row shows: original text, translated text, confidence indicator, and a "locate" affordance. |

Clicking a glossary row pans/zooms the viewer to that region's bbox and highlights it.
Clicking a highlighted bbox on the drawing scrolls the glossary panel to that row.

### Component Tree

```
<App>
  <LanguagePicker />          — sits in the top bar, persistent
  <UploadScreen>
    <DropZone />
    <SubmitButton />
    <JobProgressIndicator />
  </UploadScreen>
  <ResultsScreen>
    <DrawingViewer>           — wraps OpenSeadragon instance
      <BboxOverlay />         — SVG layer over the tile viewer
    </DrawingViewer>
    <GlossaryPanel>
      <GlossaryRow />         — one per region, repeated
    </GlossaryPanel>
  </ResultsScreen>
</App>
```

---

## 2. Data Contract Required from the Result Store (Solove)

This is the exact JSON shape the frontend requires. Solove's and Vivek's APIs MUST
return this structure (or a superset of it — additional fields are tolerated).

### 2a. Job Status Response

Polled at `GET /api/jobs/{job_id}`:

```json
{
  "job_id": "string (UUID)",
  "status": "queued | processing | done | failed",
  "error_message": "string | null",
  "image_url": "string (presigned URL to the original image, available once queued)",
  "created_at": "ISO-8601 datetime",
  "updated_at": "ISO-8601 datetime"
}
```

The `image_url` must be a stable URL the browser can load directly (presigned S3/GCS
URL or equivalent). It must be available as soon as the job is created — the viewer
loads the image independently of OCR completion.

### 2b. Job Results Response

Fetched at `GET /api/jobs/{job_id}/results` once `status === "done"`:

```json
{
  "job_id": "string (UUID)",
  "source_lang": "string (BCP-47, e.g. 'en', 'ar')",
  "target_lang": "string (BCP-47)",
  "image_width_px": "integer — natural pixel width of the stored image",
  "image_height_px": "integer — natural pixel height of the stored image",
  "regions": [
    {
      "region_id": "string (UUID or stable opaque ID)",
      "reading_order": "integer — 0-based, used to sort the glossary panel",
      "source_text": "string — OCR-extracted text",
      "translated_text": "string — glossary-aware translation",
      "ocr_confidence": "float 0.0–1.0 — confidence from the OCR engine",
      "translation_confidence": "float 0.0–1.0 | null — optional; from translator",
      "bbox": {
        "x": "float — left edge, in image-pixel coordinates",
        "y": "float — top edge, in image-pixel coordinates",
        "width": "float — bbox width in image pixels",
        "height": "float — bbox height in image pixels"
      },
      "is_rotated": "boolean — true if the OCR engine detected rotated text",
      "rotation_angle_deg": "float | null — degrees clockwise if is_rotated is true"
    }
  ]
}
```

**Coordinate system note:** All bbox values use the natural pixel coordinate space of
the stored image (top-left origin, y increasing downward). The viewer normalises these
to viewport coordinates at render time. This avoids the frontend needing to know
anything about pre-processing resizing.

**Confidence thresholds (frontend uses):**
- `ocr_confidence < 0.60` → display a warning flag on that row (orange).
- `ocr_confidence < 0.40` → display an error flag (red); add a tooltip: "Low-confidence
  OCR — verify against the original drawing."
- `translation_confidence` (if present) < 0.70 → display an information badge.

Thresholds are configurable in a frontend constants file; they do not belong in the
API contract.

---

## 3. Tech Choices

### React + Next.js (App Router)

**Why:** Spec calls it out directly. Next.js gives server-side rendering for the
results page (important for initial load speed on large glossary payloads), built-in
image optimisation, and a file-based routing structure that maps cleanly onto the two
screens. The App Router's `use client` / `use server` split lets the glossary data be
streamed server-side while the drawing viewer mounts client-side only (it requires
the DOM and canvas).

### OpenSeadragon for the drawing viewer

**Why architectural drawings specifically:**
- Architectural drawings scanned at useful resolution are 15–80+ MP images.
  Rendering them as a plain `<img>` or canvas blob causes multi-second paints, memory
  spikes, and broken mobile experiences.
- OpenSeadragon uses the IIIF/DZI tile protocol: the server slices the image into
  zoom-level tiles; the viewer fetches only the tiles currently visible at the current
  zoom level. This keeps initial load under 200 KB regardless of source resolution.
- Smooth mouse/touch pan and zoom is its core feature.
- It is mature (10+ years), MIT-licensed, has a React wrapper (`react-openseadragon`
  or a thin custom hook), and exposes a canvas overlay API that lets us draw the SVG
  bbox layer in image-coordinate space, which is exactly what click-to-locate needs.

**Alternative considered:** Leaflet.js. Also viable for tiled images but has weaker
canvas overlay support and is more map-centric in its API semantics.

**Image tiling:** The backend (Vivek / Solove) must generate DZI tiles on job
completion and expose them at a tile endpoint. This is a backend responsibility;
the frontend only needs `GET /api/jobs/{job_id}/tiles/info.json` (the DZI descriptor).
A fallback `image_url` is used for small images below a threshold (< 4 MP).

### State management

Zustand (lightweight, no boilerplate). Two stores:

- `useJobStore` — `{ jobId, status, imageMeta, regions }` — fetched once on results
  page load, then static.
- `useSelectionStore` — `{ activeRegionId | null }` — drives the viewer highlight and
  glossary scroll synchronisation. This is the only live-updating state.

### Styling

Tailwind CSS. RTL-capable (important for Arabic glossary text). Add `dir="rtl"` to
the glossary column when `target_lang === "ar"`.

---

## 4. Click-to-Locate: Mapping Glossary Entry to Highlighted Bbox

### Glossary → Viewer

1. User clicks a `<GlossaryRow>` for `region_id = "abc"`.
2. `useSelectionStore.setActive("abc")` is called.
3. `<BboxOverlay>` re-renders: the SVG `<rect>` for `"abc"` gets class `highlighted`
   (thick amber border, semi-transparent amber fill).
4. `<DrawingViewer>` subscribes to `activeRegionId`; when it changes, it calls
   `viewer.viewport.fitBounds(convertBboxToViewport(bbox))` with a smooth animation
   (`immediately: false`). This pans and zooms the canvas so the highlighted bbox
   is centred and fills approximately 30% of the viewer height.

### Viewer → Glossary

1. User clicks on a visible bbox rect in the SVG overlay (pointer-events: all on
   `<rect>` elements, none on the SVG container).
2. Click handler calls `useSelectionStore.setActive(region_id)`.
3. `<GlossaryPanel>` subscribes to `activeRegionId`; when it changes it calls
   `glossaryRowRefs[activeRegionId].current.scrollIntoView({ behavior: 'smooth',
   block: 'center' })`.

### Coordinate conversion

```
viewportX = bbox.x / image_width_px
viewportY = bbox.y / image_height_px
viewportW = bbox.width / image_width_px
viewportH = bbox.height / image_height_px
```

OpenSeadragon's `viewport.fitBounds` accepts normalised 0–1 coordinates.
`image_width_px` and `image_height_px` come from the results response (§2b).

---

## 5. Accessibility & Responsive Considerations

### Accessibility

- Language picker renders a `<label>` + `<select>` (not a custom dropdown) for
  keyboard/screen-reader compatibility.
- `<GlossaryRow>` is a `<li>` inside a `<ul aria-label="Translation glossary">`.
  Each row has `role="button" tabIndex={0}` with keyboard `Enter`/`Space` handling.
- Active row gets `aria-pressed="true"`.
- Confidence flags use `aria-label` (e.g., "Low OCR confidence") in addition to
  colour coding; never colour-only.
- Drawing viewer has `aria-label="Architectural drawing — use arrow keys to pan"`.
  We add OpenSeadragon keyboard navigation by default.
- Focus management: after click-to-locate, focus is moved to the active glossary row
  (viewer is non-focusable canvas; the row is the actionable element).

### Responsive

- Desktop (≥1024 px): two-panel side-by-side layout (65/35 split).
- Tablet (768–1023 px): two-panel stacked (viewer top, glossary bottom), viewer
  height capped at 55 vh.
- Mobile (< 768 px): tab-based navigation; "Drawing" tab shows full-width viewer;
  "Glossary" tab shows full-width list. Active region indicator persists across tabs
  (a small badge count on the Glossary tab).
- Arabic (`dir="rtl"`): the panel order swaps (glossary left, drawing right) on
  desktop; tab labels use Arabic text; all spacing uses logical properties
  (`margin-inline-start`, not `margin-left`).

---

## 6. TDD / Testing Approach

### Unit tests (Vitest + React Testing Library)

- `<GlossaryRow>`: renders source text, translated text, confidence badge; fires
  selection callback on click and Enter key.
- `<BboxOverlay>`: given N regions, renders N `<rect>` elements; active region gets
  `highlighted` class; inactive regions do not.
- `useSelectionStore`: setActive updates state; null clears selection.
- Coordinate conversion utility (`bboxToViewport`): pure function, trivially testable
  against fixed inputs.
- Confidence flag logic: returns correct flag variant for given float inputs.

### Integration tests (Vitest + MSW for API mocking)

- Upload flow: drop a file → POST fires → poll resolves → redirect to results page.
- Results page: job results response populates glossary panel with correct count of
  rows; selecting row 3 calls `fitBounds` on the viewer mock.
- Low-confidence region: `ocr_confidence = 0.35` → red flag rendered with correct
  `aria-label`.

### End-to-end (Playwright, run against a dev server with fixture data)

- Upload a fixture PNG → wait for results → click glossary row 1 → assert viewer
  panned (assert bbox highlight class present).
- RTL check: with `target_lang = "ar"`, assert glossary panel has `dir="rtl"`.
- Keyboard navigation: Tab to row 2, press Enter, assert `aria-pressed="true"`.

### No OCR/translation tests here

The frontend tests use fixture data (a canned `results` JSON payload). Accuracy of
OCR or translation is tested by Nour and Iona respectively.

---

## 7. Phase-2 Hooks

The following extension points are scaffolded in Phase 1 but left inactive:

### Overlay toggle

- A disabled `<OverlayToggleButton>` is present in the viewer toolbar (visually
  greyed out, `aria-disabled="true"`, tooltip: "Coming soon — Phase 2").
- `<BboxOverlay>` already accepts a prop `mode: "highlight" | "overlay"`. Phase 1
  only uses `"highlight"`. Phase 2 wires `"overlay"` to render translated text
  inside each bbox using the stored position data (no new API call needed).
- The `translated_text` and `bbox` fields are already in the Phase-1 data contract.

### Building-codes panel

- A hidden `<CodesPanel>` component stub exists in the component tree, conditionally
  rendered when `feature.codesPanel` flag is true (default false).
- When Vivek adds `country_of_origin` and `applicable_codes` fields to the job
  results response, the panel can display them with no structural change.
- The Phase-1 results response schema is forward-compatible: unknown top-level fields
  are ignored.

---

## 8. Ordered Task List

| # | Task | Produces | Depends on |
|---|------|---------|------------|
| 1 | Scaffold Next.js app with Tailwind, Zustand, ESLint, Prettier, Vitest | Repo skeleton | — |
| 2 | Write fixture `job-status.json` and `job-results.json` matching §2 contract | Test fixtures | Agree contract with Solove/Vivek |
| 3 | Build `<UploadScreen>`: DropZone, language picker, submit, polling (TDD) | Upload flow | Vivek: `POST /api/jobs` + status poll endpoint stubs |
| 4 | Build `useSelectionStore` + `bboxToViewport` utility (TDD) | State + coord utils | — |
| 5 | Integrate OpenSeadragon: `<DrawingViewer>` with tile loader + DZI fallback | Viewer renders | Solove: `image_url` + tile endpoint; confirm DZI format |
| 6 | Build `<BboxOverlay>` SVG layer (TDD — unit tests with fixture regions) | Bbox rendering | Task 4, 5 |
| 7 | Build `<GlossaryPanel>` + `<GlossaryRow>` (TDD — unit + a11y checks) | Glossary list | Task 4 |
| 8 | Wire click-to-locate bidirectionally | Interactive link | Task 5, 6, 7 |
| 9 | Implement confidence flag rendering + aria labels | Confidence UX | Task 7 |
| 10 | RTL / Arabic layout pass (Tailwind logical props, `dir` attribute) | Arabic support | Task 7, 8 |
| 11 | Responsive layout pass (mobile tab view, tablet stack) | Mobile support | Task 6, 7 |
| 12 | Playwright E2E tests against fixture dev server | E2E coverage | Tasks 1–11 |
| 13 | Phase-2 stubs: `<OverlayToggleButton>` disabled, `<CodesPanel>` hidden | Hooks in place | Task 5, 7 |
| 14 | Accessibility audit (axe-core via `@axe-core/react`) and fix findings | a11y sign-off | All above |

---

## 9. Risks & Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Solove's result store returns bboxes in a different coordinate system (normalised vs pixel) | Medium | High — broken overlay alignment | Agree and lock the §2b contract before any viewer work starts (Task 2) |
| DZI tile generation is not implemented by Vivek/Solove in Phase 1 | Medium | Medium — large images fail | Build fallback: if `tiles/info.json` returns 404, load `image_url` directly; cap upload to 10 MP in Phase 1 |
| OpenSeadragon `fitBounds` animation feels sluggish on first click (cold tile cache) | Low | Low | Pre-fetch tiles around region 0 on results page load |
| Arabic RTL glossary + LTR drawing panel causes layout confusion on narrow screens | Medium | Medium | Design RTL-specific Tailwind variants early; test on a real Arabic fixture |
| `react-openseadragon` wrapper may lag behind OpenSeadragon core releases | Low | Low | Use a thin custom hook wrapping vanilla OSD instead of the wrapper library |

### Open Questions (must be resolved before Task 3)

1. **Tile endpoint format:** Will Solove/Vivek expose a DZI-compatible tile endpoint,
   or a IIIF Image API endpoint? (OpenSeadragon supports both; we need to know which.)
2. **Coordinate system confirmation:** Solove must confirm bboxes are stored and
   returned in natural-image-pixel coordinates (not normalised, not pre-processor
   output dimensions).
3. **Image URL auth:** Are `image_url` presigned URLs time-limited? If so, what TTL?
   The viewer fetches tiles on-demand; a 15-minute TTL could expire mid-session.
4. **Job polling interval:** Should the frontend use HTTP polling (e.g., every 3 s) or
   will Vivek provide a WebSocket / SSE channel for job status updates?
5. **Maximum upload file size:** What limit does the backend enforce? The frontend
   needs to match it with a client-side validation error.
6. **`translation_confidence` field:** Is this guaranteed present or optional? The
   contract above marks it nullable (`float | null`). Iona should confirm.
