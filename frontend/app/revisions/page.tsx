"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  apiRequest,
  LEARNER_STORAGE_KEY,
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
    // The learner ID remains usable for this page session.
  }
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "full",
    timeStyle: "short",
  }).format(date);
}

export default function RevisionsPage() {
  const [learnerId, setLearnerId] = useState("");
  const [activeLearnerId, setActiveLearnerId] = useState("");
  const [tasks, setTasks] = useState<RevisionTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [learnerIdError, setLearnerIdError] = useState("");
  const [reloadVersion, setReloadVersion] = useState(0);

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

    async function loadRevisions() {
      setLoading(true);
      setTasks([]);
      setError("");
      try {
        const result = await apiRequest<RevisionTask[]>(
          `/revisions/?user_id=${encodeURIComponent(activeLearnerId)}`,
        );
        if (!cancelled) setTasks(result);
      } catch (requestError) {
        if (!cancelled) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Could not load revision tasks.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadRevisions();
    return () => {
      cancelled = true;
    };
  }, [activeLearnerId, reloadVersion]);

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

  return (
    <main className="min-h-screen bg-[#f5f6f8] px-4 py-8 text-slate-900 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-indigo-600">
              CodeX · Spaced practice
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
              Revision tasks
            </h1>
            <p className="mt-2 max-w-2xl text-slate-600">
              Review patterns when their saved revision dates are due.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="Main navigation">
            <Link href="/dashboard" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400">
              Dashboard
            </Link>
            <Link href="/recommendations" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400">
              Recommendations
            </Link>
            <Link href="/practice" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400">
              Practice
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
              required
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-normal"
            />
          </label>
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-60"
          >
            {loading ? "Loading…" : "Check revisions"}
          </button>
        </form>
        {learnerIdError && <p className="mb-5 text-sm text-red-700" role="alert">{learnerIdError}</p>}

        {!activeLearnerId && (
          <section className="rounded-2xl border border-indigo-100 bg-white p-8 text-center shadow-sm">
            <h2 className="text-xl font-bold">Choose a learner to view revisions</h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">
              Use the learner ID saved on your practice page, or create a learner there first.
            </p>
            <Link href="/practice" className="mt-5 inline-flex rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700">
              Go to practice
            </Link>
          </section>
        )}
        {activeLearnerId && loading && (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-slate-600" role="status">
            Loading due revisions…
          </div>
        )}
        {activeLearnerId && !loading && error && (
          <section className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800" role="alert">
            <h2 className="font-bold">Revision tasks are unavailable</h2>
            <p className="mt-1">{error}</p>
            <p className="mt-2">Check that the backend is running and the learner ID exists.</p>
          </section>
        )}
        {activeLearnerId && !loading && !error && tasks.length === 0 && (
          <section className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <h2 className="text-xl font-bold">Nothing is due right now</h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">
              There are no due revision tasks with available evaluable problems for this learner.
              Keep practicing and check back when a saved revision date is reached.
            </p>
            <Link href="/practice" className="mt-5 inline-flex rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700">
              Continue practicing
            </Link>
          </section>
        )}
        {activeLearnerId && !loading && !error && tasks.length > 0 && (
          <ol className="space-y-4">
            {tasks.map((task) => (
              <li key={task.pattern_id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                      Revision due {formatDate(task.due_at)}
                    </p>
                    <h2 className="mt-2 text-xl font-bold">{task.pattern_name}</h2>
                    <p className="mt-1 text-sm text-slate-600">
                      {task.mastery_score.toFixed(0)}% mastery
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <span className="rounded-full bg-indigo-50 px-3 py-1 text-sm font-semibold text-indigo-800">
                      {task.difficulty}
                    </span>
                    <span className="rounded-full bg-amber-50 px-3 py-1 text-sm font-semibold text-amber-800">
                      Priority {task.priority.toFixed(0)}
                    </span>
                  </div>
                </div>
                <div className="mt-4 rounded-xl bg-slate-50 p-4">
                  <h3 className="text-sm font-semibold">Why review this pattern?</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">{task.reason}</p>
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold text-slate-900">{task.problem_title}</p>
                  <Link
                    href={`/practice?pattern_id=${task.pattern_id}&problem_id=${task.problem_id}`}
                    className="inline-flex rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-700"
                  >
                    Start revision
                  </Link>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </main>
  );
}
