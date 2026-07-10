const STORAGE_KEY_PREFIX = 'study-copilot:auth-token:'

/** A token asserts ownership of exactly one studentId (see
 * backend/auth.py::require_owner) — storage MUST be keyed per studentId, not
 * a single shared key, otherwise switching the active student in the
 * sidebar (frontend/src/lib/studentId.ts) leaves the previous student's
 * token cached and sent for the new student's requests, which
 * require_owner correctly rejects as a 403 (confirmed live: this was
 * originally a single global key and broke exactly this way). Minted by
 * POST /auth/token (see useAuthToken.ts) and cached here so it survives a
 * page reload without re-issuing on every visit. */
export function getStoredToken(studentId: string): string | null {
  return localStorage.getItem(STORAGE_KEY_PREFIX + studentId)
}

export function setStoredToken(studentId: string, token: string): void {
  localStorage.setItem(STORAGE_KEY_PREFIX + studentId, token)
}

export function clearStoredToken(studentId: string): void {
  localStorage.removeItem(STORAGE_KEY_PREFIX + studentId)
}
