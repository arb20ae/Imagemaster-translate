"""Canonical cross-component data contract for Imagemaster-Translate (Phase 1).

THIS MODULE IS THE SINGLE SOURCE OF TRUTH for every shape that crosses a
component boundary. It supersedes the schema sections in all component plans
(docs/components/*). It encodes the rulings in docs/team/kian-technical-review.md
§2 (canonical contract) and B1-B4 (blocking issues), ratified by the Abdo+lead
review (docs/team/abdo-lead-review.md).

Owners may change a model ONLY via a version bump + Kian/Abdo sign-off.

Coordinate space (binding, ruling B1)
-------------------------------------
All bounding boxes are expressed in PRE-PROCESSED (post-Omar) image pixel space:
top-left origin, x increases right, y increases down, absolute pixels. The
frontend displays the pre-processed image (`ImageRef.processed_url`) so overlays
align with NO client-side transform. The original upload is retained but is not
the Phase-1 display surface.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Controlled vocabularies
# --------------------------------------------------------------------------- #
class UncertainReason(str, Enum):
    """Why a region's translation is flagged uncertain (owned by Iona).

    Distinct from `low_confidence` (owned by Nour, OCR-side). A region may be
    `uncertain` for a translation-side reason even when OCR confidence is high.
    """

    UNRECOGNIZED_DOMAIN_TERM = "unrecognized_domain_term"
    LOW_OCR_CONFIDENCE = "low_ocr_confidence"
    AMBIGUOUS = "ambiguous"
    PARSE_ERROR = "parse_error"
    TRANSLATION_FAILED = "translation_failed"


class JobStatus(str, Enum):
    """Async job lifecycle (ruling B4 — frozen to the orchestrator's six states).

    The frontend collapses {preprocessing, ocr, translating} into one "processing"
    spinner but must NOT hardcode a literal "processing" status value.
    """

    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    OCR = "ocr"
    TRANSLATING = "translating"
    DONE = "done"
    FAILED = "failed"


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
class BBox(BaseModel):
    """A bounding box in pre-processed image pixel space (see module docstring).

    Single rotation field `angle` (ruling B2) — there is NO separate `is_rotated`
    boolean. `angle == 0.0` means upright. Field names are `w`/`h`, NOT
    `width`/`height`.
    """

    x: float = Field(..., description="Left edge, pixels, pre-processed space.")
    y: float = Field(..., description="Top edge, pixels, pre-processed space.")
    w: float = Field(..., ge=0, description="Width in pixels.")
    h: float = Field(..., ge=0, description="Height in pixels.")
    angle: float = Field(
        0.0, description="Rotation in degrees clockwise; 0.0 = upright."
    )


# --------------------------------------------------------------------------- #
# Region — the internal pipeline object (Nour -> Iona -> Solove)
# --------------------------------------------------------------------------- #
class Region(BaseModel):
    """One detected annotation as it flows through the pipeline.

    Field ownership (who is authoritative for writing each field):
      - Nour (OCR adapter): text, bbox, confidence, lang, region_index,
        low_confidence
      - Iona (translator):  translation, translation_confidence, uncertain,
        uncertain_reason, glossary_hit, canonical_term
    """

    # --- OCR-owned (Nour) ---
    region_index: int = Field(
        ..., ge=0, description="0-based ordering in document reading order."
    )
    text: str = Field(..., description="Raw OCR text, UTF-8 (RTL preserved as-is).")
    bbox: BBox
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Raw OCR confidence; ALWAYS transmitted."
    )
    lang: Optional[str] = Field(
        None, description="BCP-47 detected language; null if undetected (never omitted)."
    )
    low_confidence: bool = Field(
        ...,
        description="Authoritative OCR low-confidence flag (ruling B3). Computed "
        "once by Nour against a benchmark-calibrated threshold (default 0.75).",
    )

    # --- Translation-owned (Iona) ---
    translation: Optional[str] = Field(
        None, description="Translated text; null on partial failure."
    )
    translation_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Null if the engine provides no score."
    )
    uncertain: bool = Field(
        False, description="Translation-side uncertainty flag (owned by Iona)."
    )
    uncertain_reason: Optional[UncertainReason] = None
    glossary_hit: bool = Field(
        False, description="True if a glossary term was applied to this region."
    )
    canonical_term: Optional[str] = Field(
        None, description="The canonical glossary term used, if any."
    )


# --------------------------------------------------------------------------- #
# Wire/API result object (Vivek/Solove -> Zoriaz frontend)
# --------------------------------------------------------------------------- #
class ImageRef(BaseModel):
    """The image the frontend displays. `processed_url` is the PRE-PROCESSED image
    (ruling B1); `width`/`height` are its pixel dimensions and define the space
    every bbox lives in."""

    processed_url: str = Field(..., description="Short-lived signed URL (processed image).")
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)


class ResultRegion(BaseModel):
    """A region as exposed on the wire. `translation` is FLAT here (ruling B2);
    Solove may store it relationally but the API flattens it. Phase-2 multi-language
    becomes a `translations: list[...]` change (a versioned change, not Phase 1)."""

    region_id: str
    region_index: int = Field(..., ge=0)
    text: str
    lang: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: BBox
    translation: Optional[str] = None
    translation_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    low_confidence: bool
    uncertain: bool = False
    uncertain_reason: Optional[UncertainReason] = None
    glossary_hit: bool = False
    canonical_term: Optional[str] = None


class ResultStats(BaseModel):
    region_count: int = Field(..., ge=0)
    low_confidence_count: int = Field(..., ge=0)
    glossary_hit_rate: float = Field(..., ge=0.0, le=1.0)


class JobResult(BaseModel):
    """GET /api/v1/jobs/{job_id}/results — returned only when status == done."""

    job_id: str
    status: JobStatus = JobStatus.DONE
    src_lang: str = Field(..., description="BCP-47, e.g. 'en'.")
    tgt_lang: str = Field(..., description="BCP-47, e.g. 'ar'.")
    image: ImageRef
    regions: list[ResultRegion]
    stats: ResultStats


class JobStatusResponse(BaseModel):
    """GET /api/v1/jobs/{job_id} — lightweight status poll."""

    job_id: str
    status: JobStatus
    created_at: str = Field(..., description="ISO-8601.")
    updated_at: str = Field(..., description="ISO-8601.")
    src_lang: str
    tgt_lang: str
    stage_detail: Optional[str] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Glossary (Matt store -> Iona translator)  [resolves Kian N4]
# --------------------------------------------------------------------------- #
class GlossaryEntry(BaseModel):
    """One curated architectural term mapping. Shared shape consumed by Iona and
    produced by Matt's bulk fetch (resolves the N4 field-name mismatch)."""

    src_term: str
    tgt_term: str
    src_lang: str = Field(..., description="BCP-47.")
    tgt_lang: str = Field(..., description="BCP-47.")
    domain: Optional[str] = Field(None, description="e.g. 'structure', 'finishes'.")
    synonyms: list[str] = Field(default_factory=list)
    context: Optional[str] = Field(None, description="Usage note shown to the model.")
    version: int = Field(1, ge=1, description="Row version; feeds cache invalidation.")
