"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  apiRequest,
  LEARNER_STORAGE_KEY,
  type Recommendation,
} from "../practice/api";

const NO_RECOMMENDATION_MESSAGE =
  "No problems with usable test cases are available";

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

export default function RecommendationsPage() {
  const [learnerId, setLearnerId] = useState("");
  const [activeLearnerId, setActiveLearnerId] = useState("");
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [isEmpty, setIsEmpty] = useState(false);
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

    async function loadRecommendation() {
      setLoading(true);
      setRecommendation(null);
      setIsEmpty(false);
      setError("");
      try {
        const result = await apiRequest<Recommendation>(
          `/recommendations/?user_id=${encodeURIComponent(activeLearnerId)}`,
        );
        if (!cancelled) setRecommendation(result);
      } catch (requestError) {
        if (!cancelled) {
          const message =
            requestError instanceof Error
              ? requestError.message
              : "Could not load a recommendation.";
          if (message === NO_RECOMMENDATION_MESSAGE) {
            setIsEmpty(true);
          } else {
            setError(message);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadRecommendation();
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
              CodeX · Adaptive practice
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
              Your next problem
            </h1>
            <p className="mt-2 max-w-2xl text-slate-600">
              A deterministic recommendation based on your saved mastery and practice history.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="Main navigation">
            <Link href="/dashboard" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400">
              Dashboard
            </Link>
            <Link href="/revisions" className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400">
              Revisions
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
            {loading ? "Loading…" : "Get recommendation"}
          </button>
        </form>
        {learnerIdError && <p className="mb-5 text-sm text-red-700" role="alert">{learnerIdError}</p>}

        {!activeLearnerId && (
          <section className="rounded-2xl border border-indigo-100 bg-white p-8 text-center shadow-sm">
            <h2 className="text-xl font-bold">Choose a learner to personalize practice</h2>
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
            Loading your recommendation…
          </div>
        )}
        {activeLearnerId && !loading && error && (
          <section className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800" role="alert">
            <h2 className="font-bold">Recommendation is unavailable</h2>
            <p className="mt-1">{error}</p>
            <p className="mt-2">Check that the backend is running and the learner ID exists.</p>
          </section>
        )}
        {activeLearnerId && !loading && isEmpty && (
          <section className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
            <h2 className="text-xl font-bold">No evaluable problems available</h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">
              The backend has no available problems with usable test cases to recommend right now.
            </p>
            <Link href="/practice" className="mt-5 inline-flex rounded-lg border border-indigo-200 px-5 py-2.5 text-sm font-semibold text-indigo-700 hover:bg-indigo-50">
              Browse practice
            </Link>
          </section>
        )}
        {activeLearnerId && !loading && recommendation && (
          <article className="overflow-hidden rounded-2xl border border-indigo-100 bg-white shadow-sm">
            <div className="bg-gradient-to-r from-indigo-700 to-violet-700 p-6 text-white sm:p-8">
              <p className="text-sm font-semibold uppercase tracking-wide text-indigo-100">
                Recommended next
              </p>
              <h2 className="mt-2 text-2xl font-bold sm:text-3xl">{recommendation.title}</h2>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="rounded-full bg-white/15 px-3 py-1 text-sm font-semibold">
                  {recommendation.pattern}
                </span>
                <span className="rounded-full bg-white/15 px-3 py-1 text-sm font-semibold">
                  {recommendation.difficulty}
                </span>
              </div>
            </div>
            <div className="p-6 sm:p-8">
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-4">
                <h3 className="text-sm font-semibold text-indigo-950">Why this problem?</h3>
                <p className="mt-2 text-sm leading-6 text-indigo-950">{recommendation.reason}</p>
              </div>
              <Link
                href={`/practice?problem_id=${recommendation.problem_id}`}
                className="mt-6 inline-flex rounded-lg bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700"
              >
                Practice this problem
              </Link>
            </div>
          </article>
        )}
      </div>
    </main>
  );
}
