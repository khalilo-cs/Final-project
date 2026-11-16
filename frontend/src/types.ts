export type { User } from "./api";
export interface Course { id: string; name: string; code: string; faculty_id: string; semester: string | null; year: number | null }
export interface Project {
  id: string; title: string; description: string | null; student_id: string; course_id: string;
  programming_languages: string[]; frameworks: string[]; has_report: boolean; has_database: boolean;
  status: string; analysis_error: string | null; submitted_at: string;
}
export interface AdviceItem { category: string; title: string; evidence: string; priority?: "critical" | "high" | "medium" | "low" }
export interface Fix { id: string; file: string; line: number; type: string; title: string; explanation: string; kind: "patch" | "suggestion"; diff: string | null; example: string | null }
export interface Advice {
  strengths: AdviceItem[]; weaknesses: AdviceItem[]; improvements: AdviceItem[];
  fixes: Fix[] | null; applied_fixes: { fix_id: string; file: string; line: number; title: string; applied_at: string }[];
  summary: { summary: string; written_by: string } | null;
}
export interface Breakdown { criterion: string; label_ar: string; weight: number; score: number | null; points: number | null; justification: string | null }
export interface Alert { type: string; severity: string; message: string; message_ar?: string; project_id: string; project_title: string; course_id: string }
export interface Grade {
  project_id: string; status: string; suggested_total: number | null; coverage: number; missing_criteria: string[];
  breakdown: Breakdown[]; final_total: number | null; faculty_notes: string | null; graded_at: string | null; alerts: Alert[];
}
export interface Question { text: string; type: string; level: number; related_file: string | null; related_lines: string | null; code: string | null }
export interface QA {
  id: string; number: number; type: string; level: number; source: string; question: string; related_file: string | null;
  answer: string; score: number; verdict: string; confidence: number; provider_scores: Record<string, number>; reasoning: string | null; response_seconds: number | null;
}
export interface VivaState {
  session_id: string; project_id: string; status: string; language: string; level: number; question_number: number; max_questions: number;
  current_question: Question | null; overall_score: number | null; providers: string[]; transcript?: QA[];
  seconds_left?: number; paused_seconds?: number; interruptions?: number; pauses?: { from: string; to: string; seconds: number; credited: number }[];
}
