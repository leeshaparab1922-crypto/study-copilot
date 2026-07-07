import { z } from 'zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import { wellbeingFlagSchema, type WellbeingFlag } from '@/lib/schemas/wellbeing'

/**
 * POST /wellbeing-check returns a LIST of flags synchronously — not
 * job-polled, since it's plain deterministic threshold checks
 * (crewai_core/wellbeing_monitor.py), not an LLM call. Two independent
 * checks run every call (quiz inactivity, missed-scheduled-day streak);
 * either, both, or neither can produce a flag, hence a list (was a single
 * nullable flag before the second check existed) — empty array means
 * nothing was warranted.
 *
 * The backend has no GET list endpoint for flag HISTORY — check and ack
 * are the only two operations; check only ever returns flags from the
 * checks that just ran (freshly created), not a running history. The page
 * below only ever shows "the flag(s) from your last check."
 */
export function useWellbeingCheck(studentId: string) {
  return useMutation<WellbeingFlag[], ApiError>({
    mutationFn: () => api.post(`/students/${studentId}/wellbeing-check`, z.array(wellbeingFlagSchema)),
  })
}

export function useWellbeingAck(studentId: string) {
  const queryClient = useQueryClient()
  return useMutation<WellbeingFlag, ApiError, { flag_id: string; reviewer_note: string }>({
    mutationFn: (body) => api.post(`/students/${studentId}/wellbeing-ack`, wellbeingFlagSchema, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wellbeing-check', studentId] })
    },
  })
}
