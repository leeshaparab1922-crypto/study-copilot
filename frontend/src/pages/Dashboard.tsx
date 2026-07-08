import { useOutletContext, Link } from 'react-router-dom'
import { usePlanStatus } from '@/hooks/usePlan'
import { ApiError } from '@/lib/api'

type Context = { studentId: string; token: string | null }

const QUICK_LINKS = [
  { to: '/plan/build', title: 'Build a study plan', desc: 'Paste in each subject’s syllabus and set your calendar.' },
  { to: '/quiz', title: 'Take a quiz', desc: 'Request questions on any topic, any time.' },
  { to: '/analytics', title: 'View analytics', desc: 'Hours and topics by subject.' },
  { to: '/wellbeing', title: 'Wellbeing check', desc: 'Review inactivity flags.' },
]

export function Dashboard() {
  const { studentId, token } = useOutletContext<Context>()
  const planStatus = usePlanStatus(studentId, token)

  const noPlanYet = planStatus.error instanceof ApiError && planStatus.error.httpStatus === 404

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      <header>
        <h1 style={{ fontSize: 30, marginBottom: 6 }}>Welcome back</h1>
        <p style={{ color: 'var(--ink-soft)', fontSize: 15 }}>
          Signed in as <span className="tabular" style={{ fontFamily: 'var(--font-mono)' }}>{studentId}</span>
        </p>
      </header>

      <section
        className="stagger-item"
        style={{
          background: 'var(--paper-raised)',
          border: '1px solid var(--line)',
          borderRadius: 12,
          padding: 24,
          boxShadow: 'var(--shadow-soft)',
        }}
      >
        <h2 style={{ fontSize: 18, marginBottom: 10 }}>Study plan status</h2>
        {planStatus.isLoading && <p style={{ color: 'var(--ink-soft)' }}>Checking…</p>}
        {noPlanYet && (
          <p style={{ color: 'var(--ink-soft)' }}>
            No study plan yet.{' '}
            <Link to="/plan/build" style={{ color: 'var(--accent)', fontWeight: 600 }}>
              Build one now
            </Link>
            .
          </p>
        )}
        {planStatus.data && !planStatus.data.ready && (
          <p style={{ color: 'var(--ink-soft)' }}>Your plan is being generated — this can take a minute.</p>
        )}
        {planStatus.data?.ready && planStatus.data.study_plan && (
          <p>
            Your plan covers{' '}
            <strong className="tabular">{planStatus.data.study_plan.days.length}</strong> day
            {planStatus.data.study_plan.days.length === 1 ? '' : 's'}.{' '}
            <Link to="/plan/calendar" style={{ color: 'var(--accent)', fontWeight: 600 }}>
              View calendar
            </Link>
          </p>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: 16, marginBottom: 14, color: 'var(--ink-soft)', fontWeight: 600 }}>
          Quick links
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: 14,
          }}
        >
          {QUICK_LINKS.map((link, i) => (
            <Link
              key={link.to}
              to={link.to}
              className="stagger-item"
              style={{
                animationDelay: `${i * 60}ms`,
                display: 'block',
                padding: 18,
                borderRadius: 10,
                border: '1px solid var(--line)',
                background: 'var(--paper-raised)',
                textDecoration: 'none',
                color: 'var(--ink)',
                boxShadow: 'var(--shadow-soft)',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{link.title}</div>
              <div style={{ fontSize: 13, color: 'var(--ink-soft)' }}>{link.desc}</div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
