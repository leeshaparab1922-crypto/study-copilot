"""Function-based guardrail for the Syllabus Extractor task.

Unlike syllabus_analyst's guardrail (exact, bidirectional, normalized
substring matching against clean structured JSON), this guardrail's input is
free-form, inconsistently formatted text — a pasted book index, OCR output,
etc. Text-based fidelity matching is inherently weaker than JSON diffing, so
this guardrail is deliberately narrower in scope: it catches clear
hallucination, bad weightage math, and subject/content mismatch. It does NOT
try to enforce perfect topic/sub-topic classification — ambiguous cases are
expected to come through flagged source_confidence="uncertain" rather than
retried into oblivion.

Checks, in order:
  1. Schema validation (SyllabusDraft.model_validate).
  2. subject_mismatch: bool the agent must set on the draft itself, since a
     student may paste text under the wrong subject entirely — one where
     every extracted item is still a faithful pull from the source text
     (so plain fidelity matching alone wouldn't catch it). If True, this is
     a hard rejection: there is no reviewable partial value in a
     wrong-subject draft, unlike an ambiguous per-topic classification.
  3. Hallucination catch: every unit_name/topic_name/sub_topic must have
     SOME plausible (normalized, substring/token-overlap) match somewhere
     in raw_index_text. Only a total absence of match fails the guardrail
     — near-misses are allowed through (expected to be marked "uncertain"
     by the agent, though the guardrail does not enforce that labeling).
     This is the check that catches an agent inventing a placeholder unit
     (e.g. "Unspecified Unit", "Miscellaneous") to make weightage math
     add up — confirmed via a live run where exactly this happened and was
     caught here (see the task prompt's explicit ban on this too).
  4. Weightage math:
     - The sum of all NON-estimated (weightage_is_estimated=False) values
       must not exceed 100 by itself — if it does, this is bad/inconsistent
       source data (or a misread) and must not be silently rescaled; retry.
     - The full sum (estimated + non-estimated) must equal 100 (+/- 0.01).
"""

import re
from typing import Any

from crewai import TaskOutput

from crewai_core.models.syllabus_draft import SyllabusDraft

WEIGHTAGE_SUM_TOLERANCE = 0.01


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())


def _plausible_match(candidate: str, normalized_source: str) -> bool:
    """Looser than an exact substring check: also accepts token-overlap, so
    reasonably-classified real-world text (reworded/re-punctuated headings)
    isn't treated as hallucinated just because it isn't a verbatim substring."""

    normalized_candidate = _normalize(candidate)
    if not normalized_candidate:
        return True

    if normalized_candidate in normalized_source:
        return True

    tokens = [t for t in normalized_candidate.split() if len(t) > 2]
    if not tokens:
        return normalized_candidate in normalized_source
    matched = sum(1 for t in tokens if t in normalized_source)
    return (matched / len(tokens)) >= 0.5


def make_syllabus_extractor_guardrail(subject_name: str, raw_index_text: str):
    """Build a guardrail bound to one extraction request's subject and
    raw source text."""

    normalized_source = _normalize(raw_index_text)

    def guardrail(result: TaskOutput) -> tuple[bool, Any]:
        try:
            draft = SyllabusDraft.model_validate(
                result.pydantic if result.pydantic is not None else result.json_dict
            )
        except Exception as exc:
            return False, f"Output did not match SyllabusDraft schema: {exc}"

        if draft.subject_mismatch:
            reason = draft.subject_mismatch_reason or "no reason given"
            return False, (
                f"Source text does not appear to match subject '{subject_name}': "
                f"{reason}. This is a hard rejection — a wrong-subject draft has "
                "no reviewable partial value."
            )

        problems: list[str] = []

        for unit in draft.units:
            if not _plausible_match(unit.unit_name, normalized_source):
                problems.append(
                    f"Unit '{unit.unit_name}' has no plausible match anywhere in the "
                    "source text — do not invent placeholder units (e.g. 'Unspecified "
                    "Unit', 'Miscellaneous') to make weightage percentages add up."
                )
            for topic in unit.topics:
                if not _plausible_match(topic.topic_name, normalized_source):
                    problems.append(
                        f"Topic '{topic.topic_name}' (unit '{unit.unit_name}') has no "
                        "plausible match anywhere in the source text — do not invent "
                        "content not present in the raw index."
                    )
                for sub_topic in topic.sub_topics:
                    if not _plausible_match(sub_topic, normalized_source):
                        problems.append(
                            f"Sub-topic '{sub_topic}' (topic '{topic.topic_name}') has no "
                            "plausible match anywhere in the source text — do not invent "
                            "content not present in the raw index."
                        )

        non_estimated_sum = sum(
            u.weightage_percent for u in draft.units if not u.weightage_is_estimated
        )
        if non_estimated_sum > 100 + WEIGHTAGE_SUM_TOLERANCE:
            problems.append(
                f"Weightage values extracted directly from the source text sum to "
                f"{non_estimated_sum}, which already exceeds 100 — report values "
                "exactly as found in the text rather than rescaling/normalizing them; "
                "re-check the source text for a misread."
            )

        total_sum = sum(u.weightage_percent for u in draft.units)
        if draft.units and abs(total_sum - 100.0) > WEIGHTAGE_SUM_TOLERANCE:
            problems.append(
                f"Unit weightage_percent values sum to {total_sum}, but must sum to "
                "100 once estimated fallback values are included for any unit "
                "without a stated weightage."
            )

        if problems:
            return False, "; ".join(problems)

        return True, draft

    return guardrail
