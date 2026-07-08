import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useCreateQuiz, useSubmitAttempt } from '@/hooks/useQuiz'
import { useSyllabi } from '@/hooks/useSyllabi'
import { QuestionCard, type QuestionAnswerDraft } from '@/components/quiz/QuestionCard'
import { QuizResult } from '@/components/quiz/QuizResult'
import { JobStatus } from '@/components/shared/JobStatus'
import { ErrorBanner } from '@/components/shared/ErrorBanner'

type Context = { studentId: string; token: string | null }

export function Quiz() {
  const { studentId, token } = useOutletContext<Context>()
  const [subject, setSubject] = useState('')
  const [topic, setTopic] = useState('')
  const [answers, setAnswers] = useState<QuestionAnswerDraft[]>([])

  const createQuiz = useCreateQuiz(studentId, token)
  const submitAttempt = useSubmitAttempt(studentId, token)
  const syllabiQuery = useSyllabi(studentId, token)

  const quiz = createQuiz.job?.result
  const syllabi = useMemo(() => syllabiQuery.data ?? [], [syllabiQuery.data])

  // Every topic (flattened across units) for the currently-selected subject,
  // in syllabus order — the same source generate_quiz() validates against,
  // so a dropdown pick can never hit the unknown-subject/topic error paths.
  const topicsForSubject = useMemo(() => {
    const syllabus = syllabi.find((s) => s.subject === subject)
    if (!syllabus) return []
    return syllabus.units.flatMap((unit) => unit.topics.map((t) => t.topic_name))
  }, [syllabi, subject])

  // Reset the topic whenever the subject changes so a stale topic from a
  // different subject's list can never be submitted.
  useEffect(() => {
    setTopic('')
  }, [subject])

  function handleRequest() {
    setAnswers([])
    createQuiz.start({ subject: subject.trim(), topic: topic.trim() })
  }

  function handleAnswer(answer: QuestionAnswerDraft) {
    const nextAnswers = [...answers, answer]
    setAnswers(nextAnswers)

    if (quiz && nextAnswers.length === quiz.questions.length) {
      submitAttempt.start({
        subject: quiz.subject,
        topic_name: quiz.topic_name,
        answers: nextAnswers,
      })
    }
  }

  function handleRestart() {
    createQuiz.reset()
    submitAttempt.reset()
    setAnswers([])
    setSubject('')
    setTopic('')
  }

  if (submitAttempt.isDone && submitAttempt.job?.result) {
    const correctCount = answers.filter((a) => a.correct).length
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <QuizResult result={submitAttempt.job.result} correctCount={correctCount} total={answers.length} />
        <button type="button" className="primary-button" style={{ alignSelf: 'flex-start' }} onClick={handleRestart}>
          Take another quiz
        </button>
      </div>
    )
  }

  if (submitAttempt.isRunning) {
    return <JobStatus job={submitAttempt.job} pendingLabel="Scoring your attempt…" />
  }

  if (submitAttempt.isFailed) {
    return <JobStatus job={submitAttempt.job} />
  }

  if (quiz && answers.length < quiz.questions.length) {
    return (
      <div style={{ maxWidth: 560 }}>
        <QuestionCard
          key={answers.length}
          question={quiz.questions[answers.length]}
          index={answers.length}
          total={quiz.questions.length}
          onAnswer={handleAnswer}
        />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 480 }}>
      <header>
        <h1 style={{ fontSize: 28, marginBottom: 6 }}>Take a quiz</h1>
        <p style={{ color: 'var(--ink-soft)', fontSize: 14 }}>
          Request questions on any topic from your syllabus, any time — it doesn't need to be a day the plan has reached yet.
        </p>
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {syllabiQuery.isLoading && <p style={{ fontSize: 14, color: 'var(--ink-soft)' }}>Loading your subjects…</p>}
        {syllabiQuery.isError && <ErrorBanner error="Couldn't load your subjects — try refreshing the page." />}
        {!syllabiQuery.isLoading && !syllabiQuery.isError && syllabi.length === 0 && (
          <p style={{ fontSize: 14, color: 'var(--ink-soft)' }}>
            No subjects yet — build a study plan first, then come back here to request a quiz.
          </p>
        )}

        <label>
          <span className="field-label">Subject</span>
          <select value={subject} onChange={(e) => setSubject(e.target.value)} className="field-input" disabled={syllabi.length === 0}>
            <option value="">Select a subject…</option>
            {syllabi.map((s) => (
              <option key={s.subject} value={s.subject}>
                {s.subject}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="field-label">Topic</span>
          <select value={topic} onChange={(e) => setTopic(e.target.value)} className="field-input" disabled={!subject}>
            <option value="">Select a topic…</option>
            {topicsForSubject.map((topicName) => (
              <option key={topicName} value={topicName}>
                {topicName}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={handleRequest}
          disabled={!subject.trim() || !topic.trim() || createQuiz.isRunning}
          className="primary-button"
          style={{ alignSelf: 'flex-start' }}
        >
          Generate quiz
        </button>
        {createQuiz.startError && <ErrorBanner error={createQuiz.startError} />}
        {createQuiz.isRunning && <JobStatus job={createQuiz.job} pendingLabel="Writing your quiz…" />}
        {createQuiz.isFailed && <JobStatus job={createQuiz.job} />}
      </div>
    </div>
  )
}
