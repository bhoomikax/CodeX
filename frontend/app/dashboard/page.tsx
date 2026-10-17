"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  apiRequest,
  LEARNER_STORAGE_KEY,
  type LearnerProgress,
  type PatternProgress,
  type RevisionTask,
} from "../practice/api";

function readStoredLearnerId(): string {
  try {
    return window.localStorage.getItem(LEARNER_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function storeLearnerId(value: string) {
  try {
    window.localStorage.setItem(LEARNER_STORAGE_KEY, value);
  } catch {
    // The dashboard remains usable when browser storage is unavailable.
  }
}

function formatDate(value: string | null): string {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function masteryTone(score: number): string {
  if (score < 40) return "bg-rose-500";
  if (score <= 70) return "bg-amber-500";
  return "bg-emerald-500";
}

function PatternCard({
  pattern,
  label,
}: {
  pattern: PatternProgress;
  label?: string;
}) {
  const score = Math.min(100, Math.max(0, pattern.mastery_score));

  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-slate-900">{pattern.pattern_name}</h3>
          <p className="mt-1 text-xs text-slate-500">
            {pattern.total_attempts} {pattern.total_attempts === 1 ? "attempt" : "attempts"}
            {" · "}{pattern.accuracy_percentage}% accuracy
          </p>
        </div>
        <div className="flex items-center gap-2">
          {label && (
            <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700">
              {label}
            </span>
          )}
          <span className="text-lg font-bold tabular-nums text-slate-900">
            {pattern.mastery_score.toFixed(0)}%
          </span>
        </div>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-label={`${pattern.pattern_name} mastery`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
      >
        <div
          className={`h-full rounded-full transition-all ${masteryTone(score)}`}
          style={{ width: `${score}%` }}
        />
      </div>
      <Link
        href={`/practice?pattern_id=${pattern.pattern_id}`}
        className="mt-3 inline-flex text-sm font-semibold text-indigo-700 hover:text-indigo-900 hover:underline"
      >
        Practice this pattern
        <span className="sr-only">: {pattern.pattern_name}</span>
      </Link>
    </div>
  );
}

export default function DashboardPage() {
  const [learnerId, setLearnerId] = useState("");
  const [activeLearnerId, setActiveLearnerId] = useState("");
  const [progress, setProgress] = useState<LearnerProgress | null>(null);
  const [revisions, setRevisions] = useState<RevisionTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [progressError, setProgressError] = useState("");
  const [revisionError, setRevisionError] = useState("");
  const [learnerIdError, setLearnerIdError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function restoreLearnerId() {
      const savedId = await Promise.resolve(readStoredLearnerId());
      if (!cancelled && savedId) {
        setLearnerId(savedId);
        setActiveLearnerId(savedId);
      }
    }

    void restoreLearnerId();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeLearnerId) return;
    let cancelled = false;

    async function loadDashboard() {
      setLoading(true);
      setProgress(null);
      setRevisions([]);
      setProgressError("");
      setRevisionError("");

      const query = `?user_id=${encodeURIComponent(activeLearnerId)}`;
      const [progressResult, revisionResult] = await Promise.allSettled([
        apiRequest<LearnerProgress>(`/progress/${query}`),
        apiRequest<RevisionTask[]>(`/revisions/${query}`),
      ]);

      if (cancelled) return;
      if (progressResult.status === "fulfilled") {
        setProgress(progressResult.value);
      } else {
        setProgressError(
          progressResult.reason instanceof Error
            ? progressResult.reason.message
            : "Could not load learner progress.",
        );
      }
      if (revisionResult.status === "fulfilled") {
        setRevisions(revisionResult.value);
      } else {
        setRevisionError(
          revisionResult.reason instanceof Error
            ? revisionResult.reason.message
            : "Revision tasks are currently unavailable.",
        );
      }
      setLoading(false);
    }

    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [activeLearnerId, reloadVersion]);

  const overallMastery = useMemo(() => {
    if (!progress?.patterns.length) return null;
    const total = progress.patterns.reduce(
      (sum, pattern) => sum + pattern.mastery_score,
      0,
    );
    return total / progress.patterns.length;
  }, [progress]);

  function loadLearner(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLearnerIdError("");
    const parsedId = Number(learnerId);
    if (!Number.isInteger(parsedId) || parsedId <= 0) {
      setLearnerIdError("Enter a valid positive learner ID.");
      return;
    }
    const normalizedId = String(parsedId);
    storeLearnerId(normalizedId);
    setLearnerId(normalizedId);
    setActiveLearnerId(normalizedId);
    setReloadVersion((version) => version + 1);
  }

  const weakestPattern = progress?.weakest_pattern ?? null;
  const strongestPattern = progress?.strongest_pattern ?? null;

  return (
    <main className="min-h-screen bg-[#f5f6f8] px-4 py-8 text-slate-900 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-indigo-600">
              CodeX · Your learning
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
              Progress dashboard
            </h1>
            <p className="mt-2 max-w-2xl text-slate-600">
              Review your evaluated practice, pattern mastery, and revision tasks.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="Main navigation">
            <Link
              href="/practice"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium transition hover:border-indigo-400"
            >
              Practice
            </Link>
            <Link
              href="/recommendations"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium transition hover:border-indigo-400"
            >
              Next problem
            </Link>
            <Link
              href="/revisions"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium transition hover:border-indigo-400"
            >
              Revisions
            </Link>
            <Link
              href="/"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium transition hover:border-indigo-400"
            >
              Home
            </Link>
          </nav>
        </header>

        <form
          onSubmit={loadLearner}
          className="mb-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-end"
        >
          <label className="block flex-1 text-sm font-semibold text-slate-700">
            Learner ID
            <input
              type="number"
              min="1"
              step="1"
              value={learnerId}
              onChange={(event) => setLearnerId(event.target.value)}
              placeholder="Enter your learner ID"
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-normal"
              required
            />
          </label>
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-60"
          >
            {loading ? "Loading…" : "View progress"}
          </button>
        </form>
        {learnerIdError && (
          <p className="mb-5 text-sm text-red-700" role="alert">{learnerIdError}</p>
        )}

        {!activeLearnerId && (
          <section className="rounded-2xl border border-indigo-100 bg-white p-8 text-center shadow-sm">
            <h2 className="text-xl font-bold">Start with your learner ID</h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">
              Create a learner from the practice page or enter the ID you already use there.
              Your dashboard reads progress saved by the backend.
            </p>
            <Link
              href="/practice"
              className="mt-5 inline-flex rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
            >
              Go to practice
            </Link>
          </section>
        )}

        {activeLearnerId && loading && (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-slate-600" role="status">
            Loading progress from the backend…
          </div>
        )}

        {activeLearnerId && !loading && progressError && (
          <section className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800" role="alert">
            <h2 className="font-bold">Progress is unavailable</h2>
            <p className="mt-1">{progressError}</p>
            <p className="mt-2">
              Check that the backend is running, that the learner ID exists, and that BACKEND_API_URL is configured.
            </p>
          </section>
        )}

        {activeLearnerId && !loading && progress && (
          <div className="space-y-6">
            <section aria-label="Progress summary" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Total attempts</p>
                <p className="mt-2 text-3xl font-bold tabular-nums">{progress.total_attempts}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {progress.correct_attempts} correct
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Accuracy</p>
                <p className="mt-2 text-3xl font-bold tabular-nums">
                  {progress.total_attempts ? `${progress.accuracy_percentage}%` : "—"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {progress.total_attempts ? "Across evaluated attempts" : "No attempts yet"}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Overall mastery</p>
                <p className="mt-2 text-3xl font-bold tabular-nums">
                  {overallMastery === null ? "—" : `${overallMastery.toFixed(0)}%`}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {overallMastery === null ? "Build mastery by practicing" : "Average across practiced patterns"}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Patterns practiced</p>
                <p className="mt-2 text-3xl font-bold tabular-nums">{progress.patterns.length}</p>
                <p className="mt-1 text-xs text-slate-500">With recorded attempts</p>
              </div>
            </section>

            {progress.total_attempts === 0 ? (
              <section className="rounded-2xl border border-indigo-100 bg-white p-7 shadow-sm">
                <h2 className="text-xl font-bold">Your progress starts with one attempt</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  There are no saved submissions for this learner yet. Choose an evaluable problem
                  to start building real mastery and activity history.
                </p>
                <Link
                  href="/practice"
                  className="mt-4 inline-flex rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
                >
                  Start practicing
                </Link>
              </section>
            ) : (
              <>
                <section className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-rose-100 bg-white p-5 shadow-sm">
                    <p className="text-xs font-semibold uppercase tracking-wide text-rose-700">Focus area</p>
                    {weakestPattern ? (
                      <>
                        <h2 className="mt-2 text-xl font-bold">{weakestPattern.pattern_name}</h2>
                        <p className="mt-1 text-sm text-slate-600">
                          {weakestPattern.mastery_score.toFixed(0)}% mastery · {weakestPattern.accuracy_percentage}% accuracy
                        </p>
                        <Link
                          href={`/practice?pattern_id=${weakestPattern.pattern_id}`}
                          className="mt-4 inline-flex font-semibold text-indigo-700 hover:underline"
                        >
                          Practice your weakest pattern →
                        </Link>
                      </>
                    ) : (
                      <p className="mt-2 text-sm text-slate-600">No pattern mastery data is available yet.</p>
                    )}
                  </div>
                  <div className="rounded-2xl border border-emerald-100 bg-white p-5 shadow-sm">
                    <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Strongest pattern</p>
                    {strongestPattern ? (
                      <>
                        <h2 className="mt-2 text-xl font-bold">{strongestPattern.pattern_name}</h2>
                        <p className="mt-1 text-sm text-slate-600">
                          {strongestPattern.mastery_score.toFixed(0)}% mastery · {strongestPattern.accuracy_percentage}% accuracy
                        </p>
                        <Link
                          href={`/practice?pattern_id=${strongestPattern.pattern_id}`}
                          className="mt-4 inline-flex font-semibold text-indigo-700 hover:underline"
                        >
                          Keep building this pattern →
                        </Link>
                      </>
                    ) : (
                      <p className="mt-2 text-sm text-slate-600">No pattern mastery data is available yet.</p>
                    )}
                  </div>
                </section>

                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                  <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
                    <div>
                      <h2 className="text-xl font-bold">Pattern mastery</h2>
                      <p className="mt-1 text-sm text-slate-500">Scores and accuracy from your saved attempts</p>
                    </div>
                    <span className="text-xs text-slate-500">Mastery</span>
                  </div>
                  {progress.patterns.length ? (
                    <div className="grid gap-3 md:grid-cols-2">
                      {progress.patterns.map((pattern) => (
                        <PatternCard
                          key={pattern.pattern_id}
                          pattern={pattern}
                          label={
                            pattern.pattern_id === weakestPattern?.pattern_id
                              ? "Focus"
                              : pattern.pattern_id === strongestPattern?.pattern_id
                                ? "Strong"
                                : undefined
                          }
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                      No pattern-level progress is available yet.
                    </p>
                  )}
                </section>

                <div className="grid gap-6 lg:grid-cols-2">
                  <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <div>
                        <h2 className="text-xl font-bold">Recent activity</h2>
                        <p className="mt-1 text-sm text-slate-500">Your latest evaluated submissions</p>
                      </div>
                    </div>
                    {progress.recent_submissions.length ? (
                      <ol className="divide-y divide-slate-100">
                        {progress.recent_submissions.map((submission) => (
                          <li key={submission.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                            <div className="min-w-0">
                              <p className="truncate font-semibold text-slate-900">{submission.problem_title}</p>
                              <p className="mt-1 text-xs text-slate-500">
                                {submission.pattern_name} · {submission.language} · {formatDate(submission.submitted_at)}
                              </p>
                            </div>
                            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                              submission.is_correct
                                ? "bg-emerald-50 text-emerald-800"
                                : "bg-rose-50 text-rose-800"
                            }`}>
                              {submission.status}
                            </span>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                        No recent submissions are available.
                      </p>
                    )}
                  </section>

                  <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                    <div className="mb-4">
                      <h2 className="text-xl font-bold">Revision tasks</h2>
                      <p className="mt-1 text-sm text-slate-500">Due reviews selected from your mastery records</p>
                    </div>
                    {revisionError ? (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="status">
                        Revision tasks are unavailable: {revisionError}
                      </div>
                    ) : revisions.length ? (
                      <ol className="space-y-3">
                        {revisions.map((task) => (
                          <li key={task.pattern_id} className="rounded-xl border border-slate-200 p-4">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div>
                                <h3 className="font-semibold">{task.pattern_name}</h3>
                                <p className="mt-1 text-xs text-slate-500">
                                  Due {formatDate(task.due_at)} · {task.mastery_score.toFixed(0)}% mastery
                                </p>
                              </div>
                              <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">
                                {task.difficulty}
                              </span>
                            </div>
                            <p className="mt-3 text-sm text-slate-600">{task.reason}</p>
                            <Link
                              href={`/practice?pattern_id=${task.pattern_id}&problem_id=${task.problem_id}`}
                              className="mt-3 inline-flex text-sm font-semibold text-indigo-700 hover:underline"
                            >
                              Review {task.problem_title} →
                            </Link>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                        No revision tasks are due right now.
                      </p>
                    )}
                  </section>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
