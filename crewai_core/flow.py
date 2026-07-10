"""Step 4: Flow wiring for Steps 2-3 (Syllabus Analyst + Academic Planner /
Plan Generator), per Section 2.4 of the build prompt.

@start(): two parallel entry points —
    - analyze_all_syllabi: runs the Syllabus Analyst Crew once per subject
      in the input set, CONCURRENTLY (reuses the asyncio.gather pattern from
      run_syllabus_analyst.py).
    - parse_calendar: runs the Academic Planner Crew once (calendar parsing
      only, per deviation #4 in CLAUDE.md).

@listen(and_(...)): once BOTH entry points have completed, generate_plan
fires — computes the deterministic day/hour budget (scheduling.py), runs the
Plan Generator Crew once per subject CONCURRENTLY, and merges the per-subject
plans into one StudyPlan spanning all subjects (state.study_plan).

Guardrail-exhaustion handling: SyllabusAnalystCrew / PlanGeneratorCrew raise
on exhausted guardrail retries (CrewAI's own behavior per Section 3.2 — an
unvalidated output must never silently continue). This Flow does not catch
those exceptions; letting them propagate halts the Flow run and surfaces the
failure explicitly, per Section 3.2.

generate_quiz(subject_name, topic_name): the Assessment Designer is now
triggered on demand by direct student request for one (subject, topic) pair
— NOT tied to any day in the study plan (this replaced the original
day-indexed simulate_day() design; confirmed with user). It is a plain async
method, NOT @start()/@listen()/@router() — called directly by the CLI
whenever a student requests a quiz. It only produces the quiz; it does not
record/score attempts.

score_attempt(attempt): Step 6 — Performance & Weak-Topic Tracker (Section
2.3). A plain, synchronous, deterministic method (NOT a Crew/agent, per
Section 2.3 and the project's ground rules) — appends the QuizAttempt to
state.quiz_history, then recomputes state.weak_topics for that
(subject, topic) pair using crewai_core/performance_tracker.py's rollup
logic (last N=5 attempts, Not Started/Struggling/Improving/Mastered
thresholds confirmed with user). Called directly by the CLI (or a test
script) with attempt data — there is no real answer-submission UI/backend
yet (frontend/backend remain out of scope per Section 4).

Step 7 (Plan Optimizer, Section 2.2 #4): score_attempt() ends with a
conditional check — if the just-updated (subject, topic) pair's rollup
status is Struggling, it calls _maybe_trigger_plan_optimizer(), which runs
PlanOptimizerCrew ONCE across ALL subjects (not per-subject) and replaces
the remaining (>= today) days of state.study_plan with the revision.

DEVIATION from Section 2.4's literal wording: Section 2.4 says this
conditional trigger should be a CrewAI @router(). Verified directly against
the installed crewai package (inspect.getsource(router)) that @router() only
fires as part of the automatic @start()/@listen()/@router() event graph
during flow.kickoff() — it cannot be attached to score_attempt(), which (by
Step 5/6's own design, confirmed with user) is a plain method invoked
imperatively AFTER kickoff() completes, not part of that graph. Restructuring
score_attempt() back into the graph would reopen Step 6's already-verified
design for no functional benefit. Confirmed with user: implement the
threshold check as a plain conditional in score_attempt() instead — same
practical effect (a bounded, conditional trigger, not a re-plan on every
attempt), just not literally CrewAI's @router() primitive.

check_wellbeing(): Step 8 — Wellbeing Monitor (Section 2.3 #6). A plain,
synchronous, deterministic method (NOT a Crew/agent) that runs
independently of score_attempt()/generate_quiz(), triggered by its own CLI
flag (--check-wellbeing) or an HTTP route, matching Section 2.3 #6's
framing that this "runs independently of the daily quiz loop." Detection is
threshold-based ONLY (crewai_core/wellbeing_monitor.py): flags when >=7
real calendar days have passed since the most recent QuizAttempt anywhere
in state.quiz_history — the only real-world timestamp this project has,
since on-demand quizzes (deviation #8) and the dropped pace concept
(decision #13) leave no clean way to compute Section 2.3 #6's literal
"completion frequency"/"pace vs. plan" inputs.

acknowledge_wellbeing_flag(flag_id, reviewer_note): human review of a flag
is asynchronous, not a synchronous console pause. check_wellbeing() used to
call a SEPARATE method decorated with CrewAI's @human_feedback(...) (a
genuine, console-blocking human-in-the-loop mechanism, per Section 3.5) —
removed once this Flow started being served over HTTP, since there is no
terminal attached to an HTTP request for a person to type into, and
blocking a request/worker on console input() would hang it indefinitely.
The flag is now recorded immediately by check_wellbeing() and a human
acknowledges it later via this method, decoupled from the request that
raised it.
"""

import asyncio
import json
from datetime import date

from crewai.flow.flow import Flow, and_, listen, start
from crewai.flow.persistence import persist

from crewai_core.crews.academic_planner.crew import AcademicPlannerCrew
from crewai_core.crews.academic_planner.scheduling import allocate_days_to_subjects
from crewai_core.crews.assessment_designer.crew import AssessmentDesignerCrew
from crewai_core.crews.plan_generator.crew import PlanGeneratorCrew
from crewai_core.crews.plan_optimizer.crew import PlanOptimizerCrew
from crewai_core.crews.syllabus_analyst.crew import SyllabusAnalystCrew
from crewai_core.flow_id import derive_flow_id
from crewai_core.models.calendar import CalendarStructure
from crewai_core.models.flow_state import StudyPlanFlowState
from crewai_core.models.plan_revision import PlanRevision
from crewai_core.models.quiz import QuizSet
from crewai_core.models.quiz_attempt import QuizAttempt
from crewai_core.models.study_plan import DayPlan, EntryStatus, StudyPlan, StudyPlanEntry
from crewai_core.models.syllabus import SyllabusStructure
from crewai_core.models.weak_topic import TopicStatus, WeakTopicUpdate
from crewai_core.models.wellbeing_flag import WellbeingFlag
from crewai_core.performance_tracker import rollup_topic_status
from crewai_core.wellbeing_monitor import (
    check_inactivity_flag,
    check_missed_days_flag,
    current_missed_day_streak,
)


def merge_subject_plans(subject_plans: list[StudyPlan]) -> StudyPlan:
    """Union each subject's DayPlan.entries onto the same date, since the
    scheduling budget guarantees no two subjects were ever assigned
    overlapping hours on the same day."""

    entries_by_date: dict[str, list] = {}
    for plan in subject_plans:
        for day_plan in plan.days:
            entries_by_date.setdefault(day_plan.date, []).extend(day_plan.entries)

    merged_days = [
        DayPlan(date=day, entries=entries) for day, entries in sorted(entries_by_date.items())
    ]
    return StudyPlan(days=merged_days)


async def _analyze_subject(subject_entry: dict) -> SyllabusStructure:
    print(f"=== Starting syllabus analysis: {subject_entry['subject']} ===")
    crew_instance = SyllabusAnalystCrew(raw_syllabus=subject_entry)
    output = await crew_instance.crew().kickoff_async(
        inputs={"raw_syllabus_json": crew_instance.raw_syllabus_text}
    )
    print(f"=== Finished syllabus analysis: {subject_entry['subject']} ===")
    return output.pydantic


async def _generate_subject_plan(
    subject_syllabus: SyllabusStructure,
    day_budget: list[tuple[str, float]],
    calendar: CalendarStructure,
) -> StudyPlan:
    print(f"=== Starting plan generation: {subject_syllabus.subject} ===")
    plan_crew = PlanGeneratorCrew(
        subject_syllabus=subject_syllabus, day_budget=day_budget, calendar=calendar
    )
    result = await plan_crew.crew().kickoff_async(
        inputs={
            "subject_name": plan_crew.subject_name,
            "subject_syllabus_json": plan_crew.subject_syllabus_text,
            "day_budget_json": plan_crew.day_budget_text,
            "exams_and_deadlines_json": plan_crew.exams_and_deadlines_text,
        }
    )
    print(f"=== Finished plan generation: {subject_syllabus.subject} ===")
    return result.pydantic


async def _generate_topic_quiz(
    subject_name: str, topic_name: str, syllabus: SyllabusStructure
) -> QuizSet:
    print(f"=== Starting quiz generation: {subject_name} / {topic_name} ===")
    quiz_crew = AssessmentDesignerCrew(
        subject_name=subject_name, topic_name=topic_name, syllabus=syllabus
    )
    result = await quiz_crew.crew().kickoff_async(
        inputs={
            "subject_name": quiz_crew.subject_name,
            "topic_name": quiz_crew.topic_name,
            "subject_syllabus_json": syllabus.model_dump_json(),
        }
    )
    print(f"=== Finished quiz generation: {subject_name} / {topic_name} ===")
    return result.pydantic


def split_remaining_days(study_plan: StudyPlan, today: str) -> tuple[list[DayPlan], list[DayPlan]]:
    """Split a StudyPlan's days into (past_days, remaining_days), where
    remaining = date >= today (ISO string comparison, safe since all dates
    are YYYY-MM-DD). Confirmed with user: real wall-clock today is the
    cutoff — past days are left untouched by the Plan Optimizer."""

    past_days = [d for d in study_plan.days if d.date < today]
    remaining_days = [d for d in study_plan.days if d.date >= today]
    return past_days, remaining_days


def apply_plan_revision(past_days: list[DayPlan], revision: PlanRevision) -> StudyPlan:
    """Rebuild the full StudyPlan: untouched past days + the optimizer's
    revised remaining days, sorted by date."""

    all_days = past_days + revision.days
    return StudyPlan(days=sorted(all_days, key=lambda d: d.date))


async def _optimize_remaining_plan(
    remaining_days: list[DayPlan],
    all_syllabi: list[SyllabusStructure],
    weak_topics: list[WeakTopicUpdate],
    term_end: str,
    missed_day_streak: int = 0,
) -> PlanRevision:
    print("\n=== Starting plan optimization (Struggling topic detected) ===")
    optimizer_crew = PlanOptimizerCrew(
        remaining_days=remaining_days,
        all_syllabi=all_syllabi,
        weak_topics=weak_topics,
        term_end=term_end,
        missed_day_streak=missed_day_streak,
    )
    result = await optimizer_crew.crew().kickoff_async(
        inputs={
            "remaining_plan_json": optimizer_crew.remaining_plan_text,
            "all_syllabi_json": optimizer_crew.all_syllabi_text,
            "weak_topics_json": optimizer_crew.weak_topics_text,
            "missed_day_context": optimizer_crew.missed_day_context_text,
        }
    )
    print("=== Finished plan optimization ===")
    return result.pydantic


@persist()
class StudyPlanFlow(Flow[StudyPlanFlowState]):
    """One Flow instance per student. See module docstring for wiring."""

    def __init__(
        self,
        student_id: str,
        raw_syllabi: list[dict] | None = None,
        raw_calendar: dict | None = None,
        pre_analyzed_syllabi: list[SyllabusStructure] | None = None,
        _initial_state: StudyPlanFlowState | None = None,
        **kwargs,
    ):
        """student_id: required. Deterministically derives this Flow's
        persisted state id (crewai_core/flow_id.py's derive_flow_id) so the
        same student_id always maps to the same underlying CrewAI SQLite
        flow_uuid — this is what lets backend/registry.py's "start over"
        replace semantics and (Step 2) rehydration-after-restart both work
        without a separate id lookup table.

        pre_analyzed_syllabi: already-converted SyllabusStructure objects
        (e.g. from backend/routes.py's single syllabus-conversion step,
        which already ran its own guardrail-checked extraction). When
        given, analyze_all_syllabi() uses these directly and does NOT call
        SyllabusAnalystCrew again — re-running that crew on data that's
        already in clean SyllabusStructure shape wouldn't validate
        anything: its guardrail compares its own output back against its
        own input, which passes trivially when the input is already
        correct. raw_syllabi is still required and used for state.grade in
        that case; when pre_analyzed_syllabi is None (e.g. the CLI's raw
        fixture JSON), behavior is unchanged — one SyllabusAnalystCrew call
        per entry in raw_syllabi, exactly as before.

        raw_syllabi / raw_calendar are optional (default None) ONLY to
        support Step 2's rehydration path (backend/registry.py's get(),
        reconstructing a Flow from a persisted SQLiteFlowPersistence state
        after a process restart, where the original raw inputs were never
        persisted — only the already-parsed SyllabusStructure/
        CalendarStructure survive in state.syllabi/state.calendar). Every
        NORMAL (non-rehydration) call site — backend/registry.py's
        create_or_replace, crewai_core/run_flow.py's CLI entrypoint — still
        always supplies real raw_syllabi/raw_calendar; this default only
        matters for a rehydrated-for-reading Flow that will never call
        kickoff_async() again (the only methods that read
        self._raw_syllabi/self._raw_calendar are the @start() methods
        analyze_all_syllabi/parse_calendar, which a rehydrated Flow never
        re-invokes). Chose this "optional params" approach over a separate
        factory classmethod because it doesn't weaken required-ness for
        the normal path (both params are still required in practice by
        every real caller) and avoids a second code path for constructing
        the same class.

        _initial_state: internal-only, used exclusively by
        backend/registry.py's rehydration path to pass an already-built
        StudyPlanFlowState (loaded from SQLite) straight through as this
        Flow's initial_state, instead of building a fresh one from
        student_id. Leading underscore signals "not a normal public
        constructor argument" — normal callers never pass this.
        """

        if _initial_state is not None:
            initial_state = _initial_state
        else:
            initial_state = StudyPlanFlowState(
                id=derive_flow_id(student_id), student_id=student_id
            )
        super().__init__(initial_state=initial_state, **kwargs)
        self._raw_syllabi = raw_syllabi if raw_syllabi is not None else []
        self._raw_calendar = raw_calendar if raw_calendar is not None else {}
        self._pre_analyzed_syllabi = pre_analyzed_syllabi

    @start()
    async def analyze_all_syllabi(self) -> list[SyllabusStructure]:
        if self._pre_analyzed_syllabi is not None:
            results = list(self._pre_analyzed_syllabi)
        else:
            results = list(
                await asyncio.gather(
                    *(_analyze_subject(entry) for entry in self._raw_syllabi)
                )
            )
        self.state.syllabi = results
        if self._raw_syllabi:
            self.state.grade = self._raw_syllabi[0].get("grade", "")
        print(f"\nDone analyzing {len(results)} subjects.\n")
        return results

    @start()
    def parse_calendar(self) -> CalendarStructure:
        planner_crew = AcademicPlannerCrew(raw_calendar=self._raw_calendar)
        result = planner_crew.crew().kickoff(
            inputs={"raw_calendar_json": planner_crew.raw_calendar_text}
        )
        calendar = result.pydantic
        self.state.calendar = calendar
        print("\n=== CalendarStructure ===")
        print(calendar.model_dump_json(indent=2))
        return calendar

    @listen(and_(analyze_all_syllabi, parse_calendar))
    async def generate_plan(self) -> StudyPlan:
        all_syllabi = self.state.syllabi
        calendar = self.state.calendar

        print("\nComputing per-subject day/hour budget...")
        budget = allocate_days_to_subjects(calendar, all_syllabi)
        for subject, days in budget.items():
            print(f"  {subject}: {len(days)} days, {sum(h for _, h in days):.1f}h total")

        subject_plans = await asyncio.gather(
            *(
                _generate_subject_plan(subject_syllabus, budget[subject_syllabus.subject], calendar)
                for subject_syllabus in all_syllabi
            )
        )

        print("\nMerging per-subject plans into one StudyPlan...")
        merged = merge_subject_plans(list(subject_plans))
        self.state.study_plan = merged
        return merged

    async def generate_quiz(self, subject_name: str, topic_name: str) -> QuizSet:
        """Generate one on-demand quiz for a student-requested (subject,
        topic) pair — not tied to any day in the study plan (replaces the
        original day-indexed simulate_day() design; confirmed with user).

        The requested topic only needs to exist somewhere in that subject's
        syllabus (state.syllabi) — it does not need to have been reached by
        the study plan yet. Performance Tracker scoring of the resulting
        QuizSet is Step 6, not yet built.

        Not a @start()/@listen()/@router() method — this is a plain method
        invoked directly by the CLI (or, later, a real backend endpoint)
        whenever a student requests a quiz.
        """
        if not self.state.syllabi:
            raise RuntimeError("generate_quiz() called before syllabi were analyzed.")

        try:
            syllabus = next(s for s in self.state.syllabi if s.subject == subject_name)
        except StopIteration:
            known_subjects = sorted({s.subject for s in self.state.syllabi})
            raise ValueError(
                f"Unknown subject '{subject_name}' — known subjects: {known_subjects}"
            )

        print(f"\n=== Generating on-demand quiz: {subject_name} / {topic_name} ===")
        return await _generate_topic_quiz(subject_name, topic_name, syllabus)

    async def score_attempt(self, attempt: QuizAttempt) -> WeakTopicUpdate:
        """Step 6 — Performance & Weak-Topic Tracker (Section 2.3). Records
        the attempt, recomputes the rollup status for that (subject, topic)
        pair, then (Step 7) conditionally triggers the Plan Optimizer if
        that pair just became Struggling. See module docstring for why this
        is a plain conditional check rather than a literal @router().
        """
        if not attempt.attempted_at:
            attempt = attempt.model_copy(update={"attempted_at": date.today().isoformat()})
        self.state.quiz_history.append(attempt)

        prior_attempts_for_topic = [
            a
            for a in self.state.quiz_history
            if a.subject == attempt.subject and a.topic_name == attempt.topic_name
        ]
        updated_status = rollup_topic_status(
            attempt.subject, attempt.topic_name, prior_attempts_for_topic
        )

        self.state.weak_topics = [
            wt
            for wt in self.state.weak_topics
            if not (wt.subject == attempt.subject and wt.topic_name == attempt.topic_name)
        ]
        self.state.weak_topics.append(updated_status)

        print(
            f"\n=== Scored attempt: {attempt.subject} / {attempt.topic_name} — "
            f"{attempt.correct_count}/{attempt.total_questions} "
            f"({attempt.accuracy:.0%}), {'PASSED' if attempt.passed else 'FAILED'} "
            f"(80%+ threshold) ==="
        )
        print(
            f"=== Rollup status: {updated_status.subject} / {updated_status.topic_name} -> "
            f"{updated_status.status.value} "
            f"(last {updated_status.attempts_considered} attempt(s), "
            f"{updated_status.accuracy:.0%} accuracy) ==="
        )

        if updated_status.status == TopicStatus.STRUGGLING:
            await self._maybe_trigger_plan_optimizer()

        return updated_status

    async def _maybe_trigger_plan_optimizer(self) -> None:
        """Step 7 (Section 2.2 #4). Threshold confirmed with user: fires as
        soon as ANY (subject, topic) pair is Struggling (checked by the
        caller, score_attempt(), before calling this). Revises only the
        remaining (>= today) days of state.study_plan; past days untouched.
        No-ops if there's no study_plan yet or no remaining days left.
        """
        if self.state.study_plan is None or not self.state.calendar:
            print(
                "\n=== Skipping plan optimization: study_plan/calendar not "
                "ready yet ==="
            )
            return

        today = date.today().isoformat()
        past_days, remaining_days = split_remaining_days(self.state.study_plan, today)

        if not remaining_days:
            print("\n=== Skipping plan optimization: no remaining days left in the term ===")
            return

        # Task 6: enrich the optimizer's context with the student's current
        # missed-day streak (computed against the FULL plan, past days
        # included, since the streak looks backward from today — not a
        # new trigger, purely informational context on top of the
        # existing Struggling-topic trigger this method is already inside.
        missed_day_streak = current_missed_day_streak(self.state.study_plan, today=today)

        revision = await _optimize_remaining_plan(
            remaining_days=remaining_days,
            all_syllabi=self.state.syllabi,
            weak_topics=self.state.weak_topics,
            term_end=self.state.calendar.term_end,
            missed_day_streak=missed_day_streak,
        )

        self.state.study_plan = apply_plan_revision(past_days, revision)
        print(
            f"\n=== Plan re-optimized: {len(past_days)} past day(s) untouched, "
            f"{len(revision.days)} remaining day(s) revised ==="
        )

    def check_wellbeing(self) -> list[WellbeingFlag]:
        """Step 8 — Wellbeing Monitor (Section 2.3 #6). Plain, deterministic
        threshold checks (NOT a Crew/agent, NOT sentiment/tone analysis).
        Runs independently of score_attempt()/generate_quiz() — invoked
        directly by the CLI's --check-wellbeing flag, or an HTTP route
        (confirmed with user).

        TWO independent checks (Task 5 added the second): quiz inactivity
        (check_inactivity_flag) and a missed-scheduled-day streak
        (check_missed_days_flag, crewai_core/wellbeing_monitor.py). Neither
        replaces the other — a student can trigger either, both, or
        neither in the same call. Returns a list (0, 1, or 2 flags) rather
        than a single Optional, since both can genuinely fire at once; each
        produced flag is appended to state.wellbeing_flags independently
        (no merging/deduplication).

        Human review is asynchronous (no console pause here — this must be
        safe to call from inside an HTTP request, which has no terminal for
        a person to type into): a person reviews and acknowledges each flag
        later via acknowledge_wellbeing_flag(), decoupled from the request
        that raised it.

        Returns an empty list if no flag was warranted.
        """
        flags = [
            f
            for f in (
                check_inactivity_flag(self.state.quiz_history),
                check_missed_days_flag(self.state.study_plan),
            )
            if f is not None
        ]
        if flags:
            self.state.wellbeing_flags.extend(flags)
            for flag in flags:
                print(f"\n=== WELLBEING FLAG: {flag.reason} ===")
        else:
            print("\n=== Wellbeing check: no flag warranted ===")
        return flags

    def acknowledge_wellbeing_flag(self, flag_id: str, reviewer_note: str) -> WellbeingFlag:
        """A human's asynchronous acknowledgment of a previously-raised
        WellbeingFlag (see check_wellbeing()). Raises ValueError if flag_id
        does not match any flag in state.wellbeing_flags for this student."""
        for i, flag in enumerate(self.state.wellbeing_flags):
            if flag.id == flag_id:
                acknowledged = flag.model_copy(
                    update={"acknowledged": True, "reviewer_note": reviewer_note}
                )
                self.state.wellbeing_flags[i] = acknowledged
                return acknowledged
        raise ValueError(f"No wellbeing flag found with id '{flag_id}'.")

    def set_entry_status(
        self, date_str: str, subject: str, topic_name: str, status: EntryStatus
    ) -> StudyPlanEntry:
        """Toggle one StudyPlanEntry's status by (date, subject, topic_name).
        A plain, synchronous, deterministic method (NOT a Crew/agent) — same
        category as score_attempt()/check_wellbeing(). "missed" is never a
        settable value here (see EntryStatus/entry_status.py): it is derived
        at read time only, never stored, so it cannot be passed as `status`.

        Raises ValueError if state.study_plan is not ready yet, or if no
        entry matches the given (date, subject, topic_name) triple — mirrors
        generate_quiz()'s unknown-subject ValueError convention, so callers
        map this the same way (422 in the backend route).
        """
        if self.state.study_plan is None:
            raise ValueError("No study plan exists yet for this student.")

        for day_plan in self.state.study_plan.days:
            if day_plan.date != date_str:
                continue
            for i, entry in enumerate(day_plan.entries):
                if entry.subject == subject and entry.topic_name == topic_name:
                    updated = entry.model_copy(update={"status": status})
                    day_plan.entries[i] = updated
                    return updated

        raise ValueError(
            f"No study plan entry found for date={date_str!r}, subject={subject!r}, "
            f"topic_name={topic_name!r}."
        )
