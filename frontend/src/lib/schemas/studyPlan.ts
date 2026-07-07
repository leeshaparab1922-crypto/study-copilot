import { z } from 'zod'

/**
 * Mirrors crewai_core/models/study_plan.py::EntryStatus. Deliberately does
 * NOT include "missed" — that's a derived, read-time-only display value
 * (see deriveDisplayStatus below), never stored or settable.
 */
export const entryStatusSchema = z.enum(['not_started', 'in_progress', 'completed'])
export type EntryStatus = z.infer<typeof entryStatusSchema>

/** The 4th display-only value, "missed" — never a real EntryStatus, only
 * ever the return value of deriveDisplayStatus. */
export type DisplayStatus = EntryStatus | 'missed'

/** Mirrors crewai_core/models/study_plan.py::StudyPlanEntry */
export const studyPlanEntrySchema = z.object({
  subject: z.string(),
  topic_name: z.string(),
  hours_allocated: z.number(),
  status: entryStatusSchema,
})
export type StudyPlanEntry = z.infer<typeof studyPlanEntrySchema>

/**
 * Mirrors crewai_core/entry_status.py::entry_display_status exactly: a day
 * strictly before today whose entry is still not_started/in_progress reads
 * as "missed"; everything else (including any date >= today, or a
 * completed entry regardless of date) keeps its stored status as-is.
 * today defaults to the real client date (ISO YYYY-MM-DD) for the same
 * testability-via-override convention the Python side uses.
 */
export function deriveDisplayStatus(
  dayDate: string,
  status: EntryStatus,
  today: string = new Date().toISOString().slice(0, 10),
): DisplayStatus {
  if (dayDate < today && (status === 'not_started' || status === 'in_progress')) {
    return 'missed'
  }
  return status
}

/** Mirrors crewai_core/models/study_plan.py::DayPlan */
export const dayPlanSchema = z.object({
  date: z.string(), // ISO YYYY-MM-DD
  entries: z.array(studyPlanEntrySchema),
})
export type DayPlan = z.infer<typeof dayPlanSchema>

/** Mirrors crewai_core/models/study_plan.py::StudyPlan */
export const studyPlanSchema = z.object({
  days: z.array(dayPlanSchema),
})
export type StudyPlan = z.infer<typeof studyPlanSchema>
