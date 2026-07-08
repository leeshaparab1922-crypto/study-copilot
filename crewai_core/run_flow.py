"""Step 4/5 CLI: runs StudyPlanFlow end-to-end (Syllabus Analyst + Academic
Planner/Plan Generator wired via @start()/@listen(and_(...)), @persist'd to
local SQLite), then prints the resulting state.study_plan.

Per Section 2.1, @persist here is only so a Flow run can be inspected/resumed
between CLI invocations during development — this CLI always starts a fresh
StudyPlanFlow (confirmed with user); resume-by-ID plumbing is not built yet
since there's no re-entrant step to resume into until Steps 6-8 exist.

--quiz SUBJECT TOPIC: after the fresh kickoff completes, also generates an
on-demand quiz for that exact (subject, topic) pair, requested directly by
the student — NOT tied to any day in the study plan (this replaced the
original --simulate-day N design; confirmed with user). Runs in the SAME
invocation as the fresh kickoff — no flow-id resume plumbing yet.

--score-sample-attempt SUBJECT TOPIC ACCURACY (Step 6, dev/test only): feeds
a synthetic QuizAttempt through the Performance Tracker (score_attempt) so
state.quiz_history/state.weak_topics can be inspected without a real
answer-submission mechanism (none exists yet — frontend/backend remain out
of scope per Section 4). ACCURACY is a 0-1 fraction of questions answered
correctly out of a fixed synthetic 20-question quiz; all "correct" answers
get response_time_seconds=15 (fast), all "wrong" ones get
response_time_seconds=45 (slow), retries=0 — a simple fixture, not a claim
about a real student's behavior. If this attempt's rollup lands on
Struggling, score_attempt() (Step 7) automatically triggers the Plan
Optimizer and reprints the revised study_plan.

--check-wellbeing (Step 8): runs the Wellbeing Monitor threshold check
independently (NOT tied to --score-sample-attempt — confirmed with user,
Section 2.3 #6 frames this as independent of the quiz loop). If a flag is
warranted, it is recorded to state.wellbeing_flags and printed; review is
asynchronous (see StudyPlanFlow.acknowledge_wellbeing_flag), not a
blocking console prompt.

--backdate-last-attempt-days N (Step 8, dev/test only): after any attempt is
scored this run, rewrites its attempted_at to N days before today, purely so
--check-wellbeing's 7-day inactivity threshold can actually be exercised in
one CLI invocation without waiting real days. Not a claim about a real
student's behavior.

Usage:
    uv run python -m crewai_core.run_flow
    uv run python -m crewai_core.run_flow --quiz "Mathematics" "Polynomials"
    uv run python -m crewai_core.run_flow --score-sample-attempt "Mathematics" "Polynomials" 0.8
    uv run python -m crewai_core.run_flow --check-wellbeing
    uv run python -m crewai_core.run_flow --score-sample-attempt "Mathematics" "Polynomials" 0.8 --backdate-last-attempt-days 10 --check-wellbeing
"""

import sys

if sys.stdout.encoding.lower() != "utf-8":
    # Windows cp1252 console can't print CrewAI's UTF-8 log output (box-drawing chars, etc.)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import argparse
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from crewai_core.flow import StudyPlanFlow
from crewai_core.models.quiz_attempt import QuestionAnswer, QuizAttempt

FIXTURES_DIR = Path(__file__).parent / "fixtures"

SAMPLE_ATTEMPT_QUESTION_COUNT = 20


def _build_sample_attempt(subject: str, topic: str, accuracy: float) -> QuizAttempt:
    correct_count = round(SAMPLE_ATTEMPT_QUESTION_COUNT * accuracy)
    answers = []
    for i in range(SAMPLE_ATTEMPT_QUESTION_COUNT):
        is_correct = i < correct_count
        answers.append(
            QuestionAnswer(
                question_text=f"Sample question {i + 1}",
                selected_option_index=0,
                correct=is_correct,
                response_time_seconds=15.0 if is_correct else 45.0,
                retries=0,
            )
        )
    return QuizAttempt(subject=subject, topic_name=topic, answers=answers)


async def _run(
    quiz_request: tuple[str, str] | None,
    sample_attempt_request: tuple[str, str, float] | None,
    backdate_last_attempt_days: int | None,
    check_wellbeing: bool,
) -> None:
    with open(FIXTURES_DIR / "sample_syllabi.json", encoding="utf-8") as f:
        raw_syllabi = json.load(f)

    with open(FIXTURES_DIR / "sample_calendar.json", encoding="utf-8") as f:
        raw_calendar = json.load(f)

    flow = StudyPlanFlow(
        student_id="cli-student", raw_syllabi=raw_syllabi, raw_calendar=raw_calendar
    )
    await flow.kickoff_async()

    print(f"\n=== Flow state ID (for SQLite inspection): {flow.state.id} ===")
    print(f"=== Merged StudyPlan ({len(flow.state.study_plan.days)} days) ===")
    print(flow.state.study_plan.model_dump_json(indent=2))

    if quiz_request is not None:
        subject_name, topic_name = quiz_request
        quiz = await flow.generate_quiz(subject_name, topic_name)
        print(f"\n=== QuizSet for {quiz.subject} / {quiz.topic_name} — {len(quiz.questions)} questions ===")
        print(quiz.model_dump_json(indent=2))

    if sample_attempt_request is not None:
        subject_name, topic_name, accuracy = sample_attempt_request
        attempt = _build_sample_attempt(subject_name, topic_name, accuracy)
        await flow.score_attempt(attempt)
        print(f"\n=== StudyPlan after scoring (in case Plan Optimizer fired) ===")
        print(flow.state.study_plan.model_dump_json(indent=2))

        if backdate_last_attempt_days is not None:
            backdated = (date.today() - timedelta(days=backdate_last_attempt_days)).isoformat()
            flow.state.quiz_history[-1] = flow.state.quiz_history[-1].model_copy(
                update={"attempted_at": backdated}
            )
            print(
                f"\n=== Dev/test only: backdated last attempt's attempted_at to "
                f"{backdated} ({backdate_last_attempt_days} days ago) ==="
            )

    if check_wellbeing:
        flags = flow.check_wellbeing()
        if flags:
            for flag in flags:
                print(f"\n=== Wellbeing check result: FLAGGED — {flag.reason} ===")
        else:
            print("\n=== Wellbeing check result: no flag ===")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quiz",
        type=str,
        nargs=2,
        default=None,
        metavar=("SUBJECT", "TOPIC"),
        help="Request an on-demand quiz for one exact (subject, topic) pair.",
    )
    parser.add_argument(
        "--score-sample-attempt",
        type=str,
        nargs=3,
        default=None,
        metavar=("SUBJECT", "TOPIC", "ACCURACY"),
        help=(
            "Dev/test only: feed a synthetic QuizAttempt (fixed 20 questions) "
            "at the given accuracy (0-1) through the Step 6 Performance Tracker."
        ),
    )
    parser.add_argument(
        "--check-wellbeing",
        action="store_true",
        help=(
            "Run the Step 8 Wellbeing Monitor threshold check. If a flag is "
            "warranted, blocks on a real console human-in-the-loop prompt."
        ),
    )
    parser.add_argument(
        "--backdate-last-attempt-days",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Dev/test only: after --score-sample-attempt, rewrite that "
            "attempt's attempted_at to N days ago, so --check-wellbeing's "
            "7-day threshold can be exercised without waiting real days."
        ),
    )
    args = parser.parse_args()

    quiz_request = tuple(args.quiz) if args.quiz is not None else None
    sample_attempt_request = None
    if args.score_sample_attempt is not None:
        subject, topic, accuracy_str = args.score_sample_attempt
        sample_attempt_request = (subject, topic, float(accuracy_str))

    asyncio.run(
        _run(
            quiz_request,
            sample_attempt_request,
            args.backdate_last_attempt_days,
            args.check_wellbeing,
        )
    )


if __name__ == "__main__":
    main()
