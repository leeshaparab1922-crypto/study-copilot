import { useJobPoll } from './useJobPoll'
import { quizSetSchema } from '@/lib/schemas/quiz'
import { attemptResultSchema } from '@/lib/schemas/job'

export function useCreateQuiz(studentId: string, token: string | null) {
  return useJobPoll({
    startPath: `/students/${studentId}/quiz`,
    resultSchema: quizSetSchema,
    token,
  })
}

export function useSubmitAttempt(studentId: string, token: string | null) {
  return useJobPoll({
    startPath: `/students/${studentId}/attempts`,
    resultSchema: attemptResultSchema,
    token,
  })
}
