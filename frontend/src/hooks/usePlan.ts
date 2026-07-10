import { z } from 'zod'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { studyPlanSchema } from '@/lib/schemas/studyPlan'

const planStatusSchema = z.object({
  ready: z.boolean(),
  study_plan: studyPlanSchema.nullable(),
})

/**
 * GET /students/{id}/plan is NOT job-polled — it returns {ready, study_plan}
 * synchronously (see backend/routes.py::get_plan's docstring: 200 with
 * ready=false is a real Flow in an incomplete state, not a 404). This
 * polls on an interval only while ready is false, distinct from
 * useJobPoll's job-record polling used for the POST /plan kickoff itself.
 */
export function usePlanStatus(studentId: string, token: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['plan-status', studentId],
    queryFn: () => api.get(`/students/${studentId}/plan`, planStatusSchema, token),
    enabled: (options?.enabled ?? true) && !!token,
    retry: false,
    refetchInterval: (query) => (query.state.data?.ready ? false : 3000),
    refetchIntervalInBackground: true,
  })
}
