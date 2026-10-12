const API_PREFIX = "/api/backend";
const REQUEST_TIMEOUT_MS = 45_000;
export const LEARNER_STORAGE_KEY = "patterniq.learnerId";

export interface SampleCase {
  input: string;
  expected_output: string;
}

export interface Problem {
  id: number;
  title: string;
  difficulty: string;
  description: string | null;
  url?: string | null;
  pattern_id: number;
  test_cases_available: boolean;
  sample_cases: SampleCase[];
}

export interface Pattern {
  id: number;
  name: string;
}

export interface User {
  id: number;
  name: string;
  email: string;
}

export interface Submission {
  id: number;
  user_id: number;
  problem_id: number;
  is_correct: boolean;
  status: string;
  evaluation_details: {
    error?: string | null;
    failed_test?: number | null;
    actual_output?: string | null;
    feedback?: { explanation: string; hint: string; correction: string; provider: string };
  } | null;
  mastery?: Mastery | null;
  mistake?: Mistake | null;
  recommendation?: Recommendation | null;
}

export interface Mastery {
  user_id: number;
  pattern_id: number;
  mastery_score: number;
  confidence_score?: number;
  total_attempts?: number;
  correct_attempts?: number;
  consecutive_correct?: number;
}

export interface Mistake {
  id: number;
  submission_id: number;
  category: string;
  explanation: string | null;
  correction: string | null;
}

export interface Recommendation {
  problem_id: number;
  title: string;
  difficulty: string;
  pattern: string;
  reason: string;
  priority: number;
}

export interface PatternProgress {
  pattern_id: number;
  pattern_name: string;
  mastery_score: number;
  confidence_score: number;
  retention_score: number;
  total_attempts: number;
  correct_attempts: number;
  accuracy_percentage: number;
  consecutive_correct: number;
}

export interface RecentSubmission {
  id: number;
  problem_id: number;
  problem_title: string;
  pattern_id: number;
  pattern_name: string;
  language: string;
  status: string;
  is_correct: boolean;
  submitted_at: string | null;
}

export interface LearnerProgress {
  user_id: number;
  total_attempts: number;
  correct_attempts: number;
  accuracy_percentage: number;
  patterns: PatternProgress[];
  strongest_pattern: PatternProgress | null;
  weakest_pattern: PatternProgress | null;
  recent_submissions: RecentSubmission[];
}

export interface RevisionTask {
  pattern_id: number;
  pattern_name: string;
  mastery_score: number;
  due_at: string;
  problem_id: number;
  problem_title: string;
  difficulty: string;
  reason: string;
  priority: number;
}

interface ValidationItem {
  loc?: Array<string | number>;
  msg?: string;
}

function describeFailure(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = (detail as ValidationItem[])
        .map((item) => {
          const field = item.loc?.filter((part) => part !== "body").join(".");
          return field ? `${field}: ${item.msg ?? "invalid"}` : item.msg;
        })
        .filter(Boolean);
      if (messages.length) return messages.join("; ");
    }
  }
  if (status === 503) return "Evaluation is unavailable right now. Check the backend judge configuration.";
  if (status === 502) return "The evaluation service could not complete the request. Please try again.";
  return `Request failed with status ${status}`;
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError")) {
      throw new Error(
        "The request timed out before the judge finished. The attempt may still have been recorded; wait a moment before trying again.",
      );
    }
    throw new Error("Could not reach the backend. Check that it is running and BACKEND_API_URL is correct.");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(describeFailure(response.status, body));
  }

  return response.json() as Promise<T>;
}
