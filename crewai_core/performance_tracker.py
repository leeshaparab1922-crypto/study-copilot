"""Step 6: Performance & Weak-Topic Tracker (Section 2.3 of the master
prompt). Plain, deterministic Python — NOT a Crew/agent, per Section 2.3
and the project's ground rules.

Two responsibilities, both rule-based thresholds only, no ML:

1. classify_answer(): per-question classification (fast/slow x
   correct/wrong -> mastered / confusion-resolved / guessing / genuine
   confusion). "Fast" = response_time_seconds <= FAST_THRESHOLD_SECONDS
   (30s, confirmed with user), "slow" = above it.

2. rollup_topic_status(): rolls up the last N=5 attempts for one
   (subject, topic) pair into Not Started / Struggling / Improving /
   Mastered (thresholds confirmed with user):
     - Not Started: 0 attempts yet.
     - Mastered: last N attempts, >=90% accuracy.
     - Improving: last N attempts, >70% accuracy (Section 2.3's own example,
       locked in as the real threshold — see decision #8 in
       01-status-and-decisions.md).
     - Struggling: everything else with >=1 attempt (this covers both the
       explicit <=50% case and the 50-70% gap the user's tiered-% answer
       didn't explicitly name — "not yet clearing Improving" reads as
       Struggling, the natural 4th bucket).

A QuizAttempt is one whole-quiz submission (all questions from one QuizSet
answered together), per decision confirmed with user — NOT one attempt per
question. The 80%+ pass/fail label (decision #11) is computed per-attempt
via QuizAttempt.passed, independent of the per-(subject,topic) rollup here.
"""

from enum import Enum

from crewai_core.models.quiz_attempt import QuestionAnswer, QuizAttempt
from crewai_core.models.weak_topic import TopicStatus, WeakTopicUpdate

FAST_THRESHOLD_SECONDS = 30.0
ROLLUP_WINDOW = 5
MASTERED_THRESHOLD = 0.90
IMPROVING_THRESHOLD = 0.70
STRUGGLING_THRESHOLD = 0.50


class AnswerClassification(str, Enum):
    MASTERED_SIGNAL = "mastered_signal"  # fast + correct
    CONFUSION_RESOLVED = "confusion_resolved"  # slow + correct
    GUESSING = "guessing"  # fast + wrong
    GENUINE_CONFUSION = "genuine_confusion"  # slow + wrong — highest-priority flag


def classify_answer(answer: QuestionAnswer) -> AnswerClassification:
    is_fast = answer.response_time_seconds <= FAST_THRESHOLD_SECONDS
    if answer.correct:
        return AnswerClassification.MASTERED_SIGNAL if is_fast else AnswerClassification.CONFUSION_RESOLVED
    return AnswerClassification.GUESSING if is_fast else AnswerClassification.GENUINE_CONFUSION


def rollup_topic_status(
    subject: str, topic_name: str, attempts: list[QuizAttempt]
) -> WeakTopicUpdate:
    """attempts must already be filtered to this (subject, topic) pair and
    ordered oldest-first; only the last ROLLUP_WINDOW are considered."""

    if not attempts:
        return WeakTopicUpdate(
            subject=subject,
            topic_name=topic_name,
            status=TopicStatus.NOT_STARTED,
            attempts_considered=0,
            accuracy=0.0,
        )

    recent = attempts[-ROLLUP_WINDOW:]
    total_correct = sum(a.correct_count for a in recent)
    total_questions = sum(a.total_questions for a in recent)
    accuracy = total_correct / total_questions if total_questions else 0.0

    if accuracy >= MASTERED_THRESHOLD:
        status = TopicStatus.MASTERED
    elif accuracy > IMPROVING_THRESHOLD:
        status = TopicStatus.IMPROVING
    else:
        status = TopicStatus.STRUGGLING

    return WeakTopicUpdate(
        subject=subject,
        topic_name=topic_name,
        status=status,
        attempts_considered=len(recent),
        accuracy=accuracy,
    )
