import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { useJobPoll } from '@/hooks/useJobPoll'
import { studyPlanSchema } from '@/lib/schemas/studyPlan'
import { emptyCalendar } from '@/lib/schemas/calendar'
import type { RawSubjectSyllabus } from '@/lib/schemas/syllabus'
import { SubjectForm } from '@/components/plan/SubjectForm'
import { PendingSubjectList } from '@/components/plan/PendingSubjectList'
import { CalendarForm } from '@/components/plan/CalendarForm'
import { JobStatus } from '@/components/shared/JobStatus'
import { ErrorBanner } from '@/components/shared/ErrorBanner'

type Context = { studentId: string; token: string | null }

export function PlanBuilder() {
  const { studentId, token } = useOutletContext<Context>()
  const navigate = useNavigate()
  const [subjects, setSubjects] = useState<RawSubjectSyllabus[]>([])
  const [calendar, setCalendar] = useState(emptyCalendar())

  const planJob = useJobPoll({
    startPath: `/students/${studentId}/plan`,
    resultSchema: studyPlanSchema,
    token,
  })

  const canSubmit = subjects.length > 0 && calendar.term_start && calendar.term_end && !planJob.isRunning

  function handleSubmit() {
    planJob.start({ subjects, raw_calendar: calendar })
  }

  if (planJob.isDone) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 480 }}>
        <h1 style={{ fontSize: 26 }}>Plan created</h1>
        <p style={{ color: 'var(--ink-soft)' }}>
          Your study plan for {subjects.length} subject{subjects.length === 1 ? '' : 's'} is ready.
        </p>
        <button type="button" className="primary-button" style={{ alignSelf: 'flex-start' }} onClick={() => navigate('/plan/calendar')}>
          View calendar →
        </button>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32, maxWidth: 720 }}>
      <header>
        <h1 style={{ fontSize: 28, marginBottom: 6 }}>Build your study plan</h1>
        <p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>
          Add each subject as you have it — pasted text in any format works. Then set your calendar and generate the plan.
        </p>
      </header>

      <section>
        <h2 style={{ fontSize: 16, marginBottom: 14, color: 'var(--ink-soft)', fontWeight: 600 }}>Subjects</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <SubjectForm onAdd={(subject) => setSubjects((prev) => [...prev, subject])} />
          <PendingSubjectList subjects={subjects} onRemove={(i) => setSubjects((prev) => prev.filter((_, idx) => idx !== i))} />
        </div>
      </section>

      <section>
        <h2 style={{ fontSize: 16, marginBottom: 14, color: 'var(--ink-soft)', fontWeight: 600 }}>Calendar</h2>
        <CalendarForm calendar={calendar} onChange={setCalendar} />
      </section>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <button type="button" onClick={handleSubmit} disabled={!canSubmit} className="primary-button" style={{ alignSelf: 'flex-start' }}>
          Generate study plan
        </button>
        {planJob.startError && <ErrorBanner error={planJob.startError} />}
        {planJob.isRunning && (
          <JobStatus job={planJob.job} pendingLabel="Reading your syllabi and building the plan — this can take a minute…" />
        )}
        {planJob.isFailed && <JobStatus job={planJob.job} />}
      </section>
    </div>
  )
}
