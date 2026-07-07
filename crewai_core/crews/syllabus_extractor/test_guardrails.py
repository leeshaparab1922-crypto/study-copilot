"""Pytest coverage for make_syllabus_extractor_guardrail's decision logic —
no real LLM calls, mirrors backend/test_routes.py's approach of exercising
real guardrail code against hand-built TaskOutput-like results.

Scenarios (per the spec): full stated weightage, partial stated weightage
(mixed real + fallback), no stated weightage (full fallback), stated
weightage exceeding 100, an invented/hallucinated topic, and a subject/
content mismatch.

Run with: uv run pytest crewai_core/crews/syllabus_extractor/test_guardrails.py
"""

from types import SimpleNamespace

from crewai_core.crews.syllabus_extractor.guardrails import (
    make_syllabus_extractor_guardrail,
)
from crewai_core.models.syllabus_draft import (
    SyllabusDraft,
    SyllabusDraftTopic,
    SyllabusDraftUnit,
)

RAW_INDEX_TEXT = """
Mathematics - Grade 10 Index

1. Real Numbers (10%)
   1.1 Euclid's Division Lemma
   1.2 Irrational Numbers

2. Polynomials (20%)
   2.1 Zeroes of a Polynomial
   2.2 Division Algorithm for Polynomials

3. Pair of Linear Equations in Two Variables
   3.1 Graphical Method
   3.2 Substitution Method

4. Triangles
   4.1 Similar Triangles
   4.2 Pythagoras Theorem
"""


def _fake_output(draft: SyllabusDraft):
    return SimpleNamespace(pydantic=draft, json_dict=None)


def _guardrail(subject_name: str = "Mathematics", raw_index_text: str = RAW_INDEX_TEXT):
    return make_syllabus_extractor_guardrail(subject_name, raw_index_text)


def _topic(name: str, sub_topics=None) -> SyllabusDraftTopic:
    return SyllabusDraftTopic(topic_name=name, sub_topics=sub_topics or [])


def test_full_stated_weightage_passes():
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=40,
                weightage_is_estimated=False,
                topics=[_topic("Euclid's Division Lemma"), _topic("Irrational Numbers")],
            ),
            SyllabusDraftUnit(
                unit_name="Polynomials",
                weightage_percent=60,
                weightage_is_estimated=False,
                topics=[_topic("Zeroes of a Polynomial")],
            ),
        ],
    )
    ok, result = _guardrail()(_fake_output(draft))
    assert ok is True
    assert result is draft


def test_partial_stated_weightage_mixed_fallback_passes():
    # Real Numbers=10 (stated), Polynomials=20 (stated); remaining 70 split
    # equally across the two unstated units (Triangles + Linear Equations) = 35 each.
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=10,
                weightage_is_estimated=False,
                topics=[_topic("Euclid's Division Lemma")],
            ),
            SyllabusDraftUnit(
                unit_name="Polynomials",
                weightage_percent=20,
                weightage_is_estimated=False,
                topics=[_topic("Zeroes of a Polynomial")],
            ),
            SyllabusDraftUnit(
                unit_name="Pair of Linear Equations in Two Variables",
                weightage_percent=35,
                weightage_is_estimated=True,
                topics=[_topic("Graphical Method")],
            ),
            SyllabusDraftUnit(
                unit_name="Triangles",
                weightage_percent=35,
                weightage_is_estimated=True,
                topics=[_topic("Similar Triangles")],
            ),
        ],
    )
    ok, result = _guardrail()(_fake_output(draft))
    assert ok is True
    assert result is draft


def test_no_stated_weightage_full_fallback_passes():
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=25,
                weightage_is_estimated=True,
                topics=[_topic("Euclid's Division Lemma")],
            ),
            SyllabusDraftUnit(
                unit_name="Polynomials",
                weightage_percent=25,
                weightage_is_estimated=True,
                topics=[_topic("Zeroes of a Polynomial")],
            ),
            SyllabusDraftUnit(
                unit_name="Pair of Linear Equations in Two Variables",
                weightage_percent=25,
                weightage_is_estimated=True,
                topics=[_topic("Graphical Method")],
            ),
            SyllabusDraftUnit(
                unit_name="Triangles",
                weightage_percent=25,
                weightage_is_estimated=True,
                topics=[_topic("Similar Triangles")],
            ),
        ],
    )
    ok, result = _guardrail()(_fake_output(draft))
    assert ok is True
    assert result is draft


def test_stated_weightage_exceeding_100_fails():
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=70,
                weightage_is_estimated=False,
                topics=[_topic("Euclid's Division Lemma")],
            ),
            SyllabusDraftUnit(
                unit_name="Polynomials",
                weightage_percent=60,
                weightage_is_estimated=False,
                topics=[_topic("Zeroes of a Polynomial")],
            ),
        ],
    )
    ok, error = _guardrail()(_fake_output(draft))
    assert ok is False
    assert "exceeds 100" in error


def test_final_sum_not_100_fails():
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=10,
                weightage_is_estimated=False,
                topics=[_topic("Euclid's Division Lemma")],
            ),
            SyllabusDraftUnit(
                unit_name="Polynomials",
                weightage_percent=20,
                weightage_is_estimated=True,
                topics=[_topic("Zeroes of a Polynomial")],
            ),
        ],
    )
    ok, error = _guardrail()(_fake_output(draft))
    assert ok is False
    assert "must sum to" in error


def test_invented_topic_fails():
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=100,
                weightage_is_estimated=True,
                topics=[_topic("Quantum Field Theory Basics")],
            ),
        ],
    )
    ok, error = _guardrail()(_fake_output(draft))
    assert ok is False
    assert "no plausible match" in error


def test_invented_placeholder_unit_fails():
    # Regression test for a real failure observed in a live run: the model
    # invented a "leftover" unit (e.g. "Unspecified Unit") purely to make
    # its own weightage percentages add up to 100, rather than only
    # redistributing weightage across units that are genuinely in the
    # source text.
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=10,
                weightage_is_estimated=False,
                topics=[_topic("Euclid's Division Lemma")],
            ),
            SyllabusDraftUnit(
                unit_name="Unspecified Unit 1",
                weightage_percent=90,
                weightage_is_estimated=True,
                topics=[
                    SyllabusDraftTopic(
                        topic_name="Unspecified Topics", sub_topics=[], source_confidence="uncertain"
                    )
                ],
            ),
        ],
    )
    ok, error = _guardrail()(_fake_output(draft))
    assert ok is False
    assert "no plausible match" in error
    assert "Unspecified Unit 1" in error


def test_subject_mismatch_fails():
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[],
        subject_mismatch=True,
        subject_mismatch_reason="Source text is a history essay about the French Revolution.",
    )
    ok, error = _guardrail()(_fake_output(draft))
    assert ok is False
    assert "does not appear to match subject" in error
    assert "French Revolution" in error


def test_uncertain_confidence_topic_with_plausible_match_passes():
    # A reworded heading (token-overlap, not exact substring) should still
    # be accepted — the guardrail doesn't force retries chasing exact
    # fidelity on ambiguous real-world formatting.
    draft = SyllabusDraft(
        grade="10",
        subject="Mathematics",
        units=[
            SyllabusDraftUnit(
                unit_name="Real Numbers",
                weightage_percent=100,
                weightage_is_estimated=True,
                topics=[
                    SyllabusDraftTopic(
                        topic_name="Division Lemma of Euclid",
                        sub_topics=[],
                        source_confidence="uncertain",
                    )
                ],
            ),
        ],
    )
    ok, result = _guardrail()(_fake_output(draft))
    assert ok is True
    assert result is draft
