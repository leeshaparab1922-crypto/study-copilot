import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { getOrCreateStudentId, setStudentId } from '@/lib/studentId'
import { useAuthToken } from '@/hooks/useAuthToken'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/plan/build', label: 'Build Plan' },
  { to: '/plan/calendar', label: 'Study Calendar' },
  { to: '/quiz', label: 'Quiz' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/wellbeing', label: 'Wellbeing' },
]

export function AppShell() {
  const [studentId, setStudentIdState] = useState(() => getOrCreateStudentId())
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(studentId)
  const authToken = useAuthToken(studentId)
  const token = authToken.data ?? null

  useEffect(() => {
    setDraft(studentId)
  }, [studentId])

  function commitStudentId() {
    const trimmed = draft.trim()
    if (trimmed) {
      setStudentId(trimmed)
      setStudentIdState(trimmed)
    }
    setEditing(false)
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '240px 1fr',
        minHeight: '100vh',
      }}
    >
      <aside
        style={{
          borderRight: '1px solid var(--line)',
          background: 'var(--paper-raised)',
          padding: '28px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 28,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 21,
              fontWeight: 600,
              letterSpacing: '-0.01em',
            }}
          >
            Study Copilot
          </div>
          <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginTop: 2 }}>
            Adaptive study planning
          </div>
        </div>

        <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              style={({ isActive }) => ({
                display: 'block',
                padding: '9px 12px',
                borderRadius: 7,
                fontSize: 14,
                fontWeight: isActive ? 600 : 500,
                color: isActive ? 'var(--accent-contrast)' : 'var(--ink-soft)',
                background: isActive ? 'var(--accent)' : 'transparent',
                textDecoration: 'none',
                transition: 'background 0.15s ease, color 0.15s ease',
              })}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div style={{ marginTop: 'auto' }}>
          <div
            style={{
              fontSize: 11,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--ink-faint)',
              marginBottom: 6,
              fontWeight: 600,
            }}
          >
            Student
          </div>
          {editing ? (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commitStudentId}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitStudentId()
                if (e.key === 'Escape') {
                  setDraft(studentId)
                  setEditing(false)
                }
              }}
              style={{
                width: '100%',
                padding: '7px 9px',
                borderRadius: 6,
                border: '1px solid var(--line-strong)',
                background: 'var(--paper)',
                color: 'var(--ink)',
                fontSize: 13,
                fontFamily: 'var(--font-mono)',
              }}
            />
          ) : (
            <button
              onClick={() => setEditing(true)}
              title="Click to change"
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '7px 9px',
                borderRadius: 6,
                border: '1px dashed var(--line-strong)',
                background: 'transparent',
                color: 'var(--ink)',
                fontSize: 13,
                fontFamily: 'var(--font-mono)',
                cursor: 'pointer',
              }}
            >
              {studentId}
            </button>
          )}
        </div>
      </aside>

      <main style={{ padding: '36px 44px', maxWidth: 960 }}>
        <Outlet context={{ studentId, token }} />
      </main>
    </div>
  )
}
