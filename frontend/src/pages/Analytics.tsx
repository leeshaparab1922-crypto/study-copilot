import { useOutletContext } from 'react-router-dom'
import { usePlanStatus } from '@/hooks/usePlan'
import { ApiError } from '@/lib/api'
import { BarChart } from '@/components/shared/BarChart'

type Context = { studentId: string; token: string | null }

export function Analytics() {
  const { studentId, token } = useOutletContext<Context>()
  const planStatus = usePlanStatus(studentId, token)

  if (planStatus.isLoading) {
    return <p style={{ color: 'var(--ink-soft)' }}>Loading…</p>
  }

  const notFound = planStatus.error instanceof ApiError && planStatus.error.httpStatus === 404
  if (notFound || !planStatus.data?.ready || !planStatus.data.study_plan) {
    return (
      <div>
        <h1 style={{ fontSize: 28, marginBottom: 8 }}>Analytics</h1>
        <p style={{ color: 'var(--ink-soft)' }}>No study plan yet — build one first to see your breakdown.</p>
      </div>
    )
  }

  const plan = planStatus.data.study_plan
  const hoursBySubject = new Map<string, number>()
  const topicsBySubject = new Map<string, Set<string>>()

  for (const day of plan.days) {
    for (const entry of day.entries) {
      hoursBySubject.set(entry.subject, (hoursBySubject.get(entry.subject) ?? 0) + entry.hours_allocated)
      const topics = topicsBySubject.get(entry.subject) ?? new Set<string>()
      topics.add(entry.topic_name)
      topicsBySubject.set(entry.subject, topics)
    }
  }

  const subjects = Array.from(hoursBySubject.keys()).sort()
  const hoursData = subjects.map((subject) => ({ label: subject, value: Math.round(hoursBySubject.get(subject)! * 10) / 10 }))
  const topicsData = subjects.map((subject) => ({ label: subject, value: topicsBySubject.get(subject)!.size }))

  const totalHours = hoursData.reduce((sum, d) => sum + d.value, 0)
  const totalTopics = topicsData.reduce((sum, d) => sum + d.value, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32, maxWidth: 640 }}>
      <header>
        <h1 style={{ fontSize: 28, marginBottom: 6 }}>Analytics</h1>
        <p style={{ color: 'var(--ink-soft)', fontSize: 14 }} className="tabular">
          {subjects.length} subject{subjects.length === 1 ? '' : 's'} · {totalHours}h planned · {totalTopics} topic
          {totalTopics === 1 ? '' : 's'}
        </p>
      </header>

      <section>
        <h2 style={{ fontSize: 16, marginBottom: 14, color: 'var(--ink-soft)', fontWeight: 600 }}>Study hours by subject</h2>
        <BarChart data={hoursData} unit="h" />
      </section>

      <section>
        <h2 style={{ fontSize: 16, marginBottom: 14, color: 'var(--ink-soft)', fontWeight: 600 }}>Topics planned by subject</h2>
        <BarChart data={topicsData} unit="" />
      </section>

      <section>
        <h2 style={{ fontSize: 16, marginBottom: 14, color: 'var(--ink-soft)', fontWeight: 600 }}>Summary</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--line)' }}>
                <th style={{ textAlign: 'left', padding: '8px 10px', color: 'var(--ink-soft)', fontWeight: 600 }}>Subject</th>
                <th style={{ textAlign: 'right', padding: '8px 10px', color: 'var(--ink-soft)', fontWeight: 600 }}>Hours</th>
                <th style={{ textAlign: 'right', padding: '8px 10px', color: 'var(--ink-soft)', fontWeight: 600 }}>Topics</th>
              </tr>
            </thead>
            <tbody>
              {subjects.map((subject) => (
                <tr key={subject} style={{ borderBottom: '1px solid var(--line)' }}>
                  <td style={{ padding: '8px 10px' }}>{subject}</td>
                  <td className="tabular" style={{ padding: '8px 10px', textAlign: 'right' }}>
                    {Math.round(hoursBySubject.get(subject)! * 10) / 10}
                  </td>
                  <td className="tabular" style={{ padding: '8px 10px', textAlign: 'right' }}>
                    {topicsBySubject.get(subject)!.size}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
