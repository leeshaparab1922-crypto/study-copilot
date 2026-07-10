import { z } from 'zod'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import { tokenResponseSchema } from '@/lib/schemas/auth'
import { syllabusStructureSchema } from '@/lib/schemas/syllabus'
import { clearStoredToken, getStoredToken, setStoredToken } from '@/lib/token'

const syllabiSchema = z.array(syllabusStructureSchema)

async function mintToken(studentId: string): Promise<string> {
  const response = await api.post('/auth/token', tokenResponseSchema, { student_id: studentId })
  setStoredToken(studentId, response.token)
  return response.token
}

/**
 * Resolves the Bearer token asserting ownership of studentId (see
 * backend/auth.py::require_owner). Checks localStorage first (via
 * getStoredToken) so a page reload doesn't re-mint a token every time; only
 * calls POST /auth/token — which mints a token for whatever student_id is
 * given, no credential check (see backend/routes.py's docstring) — when
 * none is cached yet.
 *
 * A cached token can go stale without the student_id changing at all: the
 * backend's signing secret is only stable across restarts if
 * STUDENT_TOKEN_SECRET is set in .env (see backend/tokens.py) — without it,
 * every backend restart generates a fresh ephemeral secret, and every
 * previously-issued token then fails verification with a 401 even though
 * the token itself is well-formed. Rather than requiring a manual
 * localStorage clear + reload whenever that happens, the cached token is
 * validated with a cheap real request (GET /students/{id}/syllabi) before
 * being trusted; a 401 there clears the stale entry and mints a fresh one
 * transparently. A 404 (genuinely-unknown student, no syllabi yet) is NOT
 * an auth failure — it means the token is valid, so it's treated as a
 * successful validation, not a reason to re-mint.
 *
 * staleTime: Infinity because a token doesn't need re-fetching once
 * obtained for a given studentId within a session (same convention as
 * this codebase's other read hooks that don't need to auto-refresh).
 */
export function useAuthToken(studentId: string) {
  return useQuery({
    queryKey: ['auth-token', studentId],
    queryFn: async () => {
      const cached = getStoredToken(studentId)
      if (!cached) return mintToken(studentId)

      try {
        await api.get(`/students/${studentId}/syllabi`, syllabiSchema, cached)
        return cached
      } catch (err) {
        if (err instanceof ApiError && err.httpStatus === 401) {
          clearStoredToken(studentId)
          return mintToken(studentId)
        }
        // Any other outcome (404 unknown student, network hiccup on this
        // validation GET) means the failure is unrelated to auth — keep
        // using the cached token rather than needlessly re-minting.
        return cached
      }
    },
    staleTime: Infinity,
  })
}
