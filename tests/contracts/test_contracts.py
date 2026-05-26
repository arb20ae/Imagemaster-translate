"""Smoke tests for the canonical contract.

Validates that the authoritative example from Kian's review (§2.3) round-trips
through the frozen models, and that the ruling-level invariants hold. Run with:

    pytest tests/contracts/test_contracts.py
"""

from tests.contracts.contracts import (
    BBox,
    GlossaryEntry,
    JobResult,
    JobStatus,
    Region,
    UncertainReason,
)

# The canonical wire example from docs/team/kian-technical-review.md §2.3.
CANONICAL_RESULT = {
    "job_id": "0b3c1f2a-0000-4000-8000-000000000000",
    "status": "done",
    "src_lang": "en",
    "tgt_lang": "ar",
    "image": {
        "processed_url": "https://signed.example/processed.png",
        "width": 3508,
        "height": 2480,
    },
    "regions": [
        {
            "region_id": "r-0",
            "region_index": 0,
            "text": "reinforced concrete slab",
            "lang": "en",
            "confidence": 0.97,
            "bbox": {"x": 412, "y": 88, "w": 340, "h": 28, "angle": 0.0},
            "translation": "بلاطة خرسانة مسلحة",
            "translation_confidence": 0.94,
            "low_confidence": False,
            "uncertain": False,
            "uncertain_reason": None,
            "glossary_hit": True,
            "canonical_term": "reinforced concrete",
        }
    ],
    "stats": {"region_count": 1, "low_confidence_count": 0, "glossary_hit_rate": 1.0},
}


def test_canonical_wire_result_validates():
    result = JobResult.model_validate(CANONICAL_RESULT)
    assert result.status is JobStatus.DONE
    assert result.image.processed_url.endswith("processed.png")
    region = result.regions[0]
    assert region.bbox.w == 340  # canonical name is `w`, not `width`
    assert region.bbox.angle == 0.0  # single rotation field, no is_rotated
    assert region.translation == "بلاطة خرسانة مسلحة"


def test_bbox_uses_w_h_not_width_height():
    bbox = BBox(x=0, y=0, w=10, h=5)
    dumped = bbox.model_dump()
    assert "w" in dumped and "h" in dumped
    assert "width" not in dumped and "height" not in dumped


def test_region_confidence_always_present_and_bounded():
    region = Region(
        region_index=0,
        text="screed",
        bbox=BBox(x=1, y=2, w=3, h=4),
        confidence=0.5,
        lang=None,  # null allowed, never omitted
        low_confidence=True,
    )
    assert 0.0 <= region.confidence <= 1.0
    assert region.lang is None
    # Translation-side fields default cleanly before Iona runs.
    assert region.translation is None
    assert region.uncertain is False


def test_uncertain_reason_vocabulary():
    region = Region(
        region_index=1,
        text="???",
        bbox=BBox(x=0, y=0, w=1, h=1),
        confidence=0.2,
        low_confidence=True,
        uncertain=True,
        uncertain_reason=UncertainReason.LOW_OCR_CONFIDENCE,
    )
    assert region.uncertain_reason == UncertainReason.LOW_OCR_CONFIDENCE


def test_glossary_entry_shared_shape():
    entry = GlossaryEntry(
        src_term="screed",
        tgt_term="طبقة فرش",
        src_lang="en",
        tgt_lang="ar",
        domain="finishes",
        synonyms=["floor screed"],
        context="cementitious leveling layer",
    )
    assert entry.version == 1
    assert "floor screed" in entry.synonyms
