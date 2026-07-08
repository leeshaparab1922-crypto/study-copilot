import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import { studyPlanEntrySchema, type EntryStatus, type StudyPlanEntry } from '@/lib/schemas/studyPlan'

type SetEntryStatusBody = {
  date: string
  subject: string
  topic_name: string
  status: EntryStatus
}

/**
 * PATCH /students/{id}/plan/entries returns the updated StudyPlanEntry
 * synchronously — not job-polled, since this is plain state mutation with
 * no Crew/LLM call involved (see backend/routes.py::set_entry_status).
 * Invalidates the plan-status query on success so PlanCalendar's next
 * render reflects the change (same invalidation pattern as useWellbeingAck).
 */
export function useSetEntryStatus(studentId: string, token: string | null) {
  const queryClient = useQueryClient()
  return useMutation<StudyPlanEntry, ApiError, SetEntryStatusBody>({
    mutationFn: (body) =>
      api.patch(`/students/${studentId}/plan/entries`, studyPlanEntrySchema, body, token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan-status', studentId] })
    },
  })
}
