import { z } from 'zod'

/** Mirrors backend/routes.py's POST /auth/token response. */
export const tokenResponseSchema = z.object({
  token: z.string(),
  student_id: z.string(),
})
export type TokenResponse = z.infer<typeof tokenResponseSchema>
