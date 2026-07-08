import { z } from 'zod'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { syllabusStructureSchema } from '@/lib/schemas/syllabus'

const syllabiSchema = z.array(syllabusStructureSchema)

/**
 * GET /students/{id}/syllabi is NOT job-polled — it's a plain synchronous
 * read of flow.state.syllabi (same pattern as usePlanStatus). Used to back
 * subject/topic dropdowns on the Quiz page instead of free-text entry.
 */
export function useSyllabi(studentId: string, token: string | null, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['syllabi', studentId],
    queryFn: () => api.get(`/students/${studentId}/syllabi`, syllabiSchema, token),
    enabled: (options?.enabled ?? true) && !!token,
    retry: false,
  })
}
