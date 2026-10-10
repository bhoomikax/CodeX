const API_PREFIX = "/api/backend";

export interface Problem {
  id: number;
  title: string;
  difficulty: string;
  description: string | null;
  pattern_id: number;
}

export interface Pattern {
  id: number;
  name: string;
}

export interface Submission {
  id: number;
  user_id: number;
  problem_id: number;
  is_correct: boolean;
}

export interface Mastery {
  user_id: number;
  pattern_id: number;
  mastery_score: number;
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

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}
