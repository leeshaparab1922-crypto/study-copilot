import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { z } from 'zod'
import { api, ApiError } from '@/lib/api'
import { jobIdResponseSchema, jobSchema, type Job } from '@/lib/schemas/job'

/**
 * The shared pattern every mutating endpoint in backend/routes.py follows:
 * POST returns 202 + {job_id} immediately, and the real success/failure
 * (including which HTTP status a failure maps to — see
 * backend/errors.py::classify_job_exception) is only knowable once the
 * background job's coroutine finishes. Callers must poll
 * GET /jobs/{job_id} rather than getting a result synchronously from the
 * POST — see backend/routes.py's module docstring.
 *
 * This hook wraps that whole lifecycle: call `start(body)` to kick off the
 * POST, then it automatically polls the resulting job_id until status
 * leaves "pending", exposing the same states a caller cares about (job
 * pending/done/failed) without every page re-implementing the polling
 * loop.
 */
export function useJobPoll<TResult>(options: {
  /** POST path returning {job_id}, e.g. `/students/${id}/plan` */
  startPath: string
  /** Schema for the job's `result` field once status is "done". */
  resultSchema: z.ZodType<TResult>
  /** Polling interval while status is "pending". */
  pollIntervalMs?: number
  /** Bearer token for the startPath POST (see backend/auth.py's
   * require_owner — startPath always addresses a student_id). GET
   * /jobs/{job_id} itself has no student_id param and is not
   * ownership-guarded, so it needs no token. */
  token?: string | null
}) {
  const queryClient = useQueryClient()
  const jobResultSchema = jobSchema(options.resultSchema)

  const startMutation = useMutation({
    mutationFn: (body?: unknown) => api.post(options.startPath, jobIdResponseSchema, body, options.token),
  })

  const jobId = startMutation.data?.job_id

  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.get(`/jobs/${jobId}`, jobResultSchema),
    enabled: jobId !== undefined,
    // Jobs run real LLM calls (tens of seconds) — a student switching tabs
    // to check something else while a plan/quiz generates is the normal
    // case, not the exception, so polling must not stall just because the
    // tab lost focus/visibility (browsers throttle background-tab timers
    // heavily otherwise — confirmed via a live browser test where a
    // backgrounded automation tab's poll stalled ~65s+ without this).
    refetchIntervalInBackground: true,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === undefined || status === 'pending') {
        return options.pollIntervalMs ?? 1000
      }
      return false
    },
  })

  function reset() {
    if (jobId) {
      queryClient.removeQueries({ queryKey: ['job', jobId] })
    }
    startMutation.reset()
  }

  const job: Job<TResult> | undefined = jobQuery.data

  return {
    /** Kick off the job. body is JSON-serialized as the POST body. */
    start: startMutation.mutate,
    /** True from the moment `start` is called until the job resolves. */
    isRunning: startMutation.isPending || (jobId !== undefined && job?.status === 'pending'),
    /** The job record once polling has begun (undefined before the first poll response). */
    job,
    /** Set once the initial POST itself fails (e.g. network error, 4xx from the route itself, not the job). */
    startError: startMutation.error as ApiError | null,
    /** Convenience: true once job.status === "done". */
    isDone: job?.status === 'done',
    /** Convenience: true once job.status === "failed". */
    isFailed: job?.status === 'failed',
    reset,
  }
}
