"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  apiRequest,
  type Pattern,
  type Problem,
  type Submission,
} from "./api";

interface AttemptFeedback {
  submission: Submission;
}

export default function PracticePage() {
  const [problems, setProblems] = useState<Problem[]>([]);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [problemId, setProblemId] = useState("");
  const [userId, setUserId] = useState("");
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState("");
  const [feedback, setFeedback] = useState<AttemptFeedback | null>(null);
  const [loadingProblems, setLoadingProblems] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadPracticeData() {
      try {
        const [problemList, patternList] = await Promise.all([
          apiRequest<Problem[]>("/problems/"),
          apiRequest<Pattern[]>("/patterns/"),
        ]);
        if (!cancelled) {
          setProblems(problemList);
          setPatterns(patternList);
          setProblemId(problemList[0] ? String(problemList[0].id) : "");
          if (problemList.length === 0) {
            setLoadError("There are no problems available to practice yet.");
          }
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(
            error instanceof Error
              ? error.message
              : "Could not load practice problems.",
          );
        }
      } finally {
        if (!cancelled) setLoadingProblems(false);
      }
    }

    void loadPracticeData();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedProblem = problems.find(
    (problem) => String(problem.id) === problemId,
  );
  const selectedPattern = useMemo(
    () => patterns.find((pattern) => pattern.id === selectedProblem?.pattern_id),
    [patterns, selectedProblem],
  );

  async function submitAttempt(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError("");
    setFeedback(null);

    const parsedUserId = Number(userId);
    if (!Number.isInteger(parsedUserId) || parsedUserId <= 0) {
      setSubmitError("Enter a valid learner ID before submitting.");
      return;
    }
    if (!selectedProblem) {
      setSubmitError("Choose a problem before submitting.");
      return;
    }
    if (!code.trim()) {
      setSubmitError("Add your solution or notes before submitting.");
      return;
    }

    setSubmitting(true);
    try {
      const submission = await apiRequest<Submission>("/submissions/", {
        method: "POST",
        body: JSON.stringify({
          user_id: parsedUserId,
          problem_id: selectedProblem.id,
          code,
          language,
        }),
      });
      setFeedback({ submission });
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Your submission could not be saved. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function openRecommendedProblem() {
    if (!feedback?.submission.recommendation) return;
    setProblemId(String(feedback.submission.recommendation.problem_id));
    setFeedback(null);
    setCode("");
    setSubmitError("");
  }

  return (
    <main className="min-h-screen bg-[#f5f6f8] px-4 py-8 text-slate-900 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-indigo-600">
              PatternIQ · Practice
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight">
              Learn by solving
            </h1>
            <p className="mt-2 max-w-2xl text-slate-600">
              Work through a problem, record how it went, and use the feedback
              to choose what to practice next.
            </p>
          </div>
          <Link
            href="/"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400"
          >
            Home
          </Link>
        </header>

        {loadError && (
          <div
            role="alert"
            className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          >
            {loadError} Check that the backend is running and
            BACKEND_API_URL is configured correctly.
          </div>
        )}

        {loadingProblems ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-slate-600">
            Loading problems…
          </div>
        ) : selectedProblem ? (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-500">
                    Problem {selectedProblem.id}
                  </p>
                  <h2 className="mt-1 text-2xl font-bold">
                    {selectedProblem.title}
                  </h2>
                </div>
                <div className="flex gap-2">
                  <span className="rounded-full bg-amber-50 px-3 py-1 text-sm font-semibold text-amber-800">
                    {selectedProblem.difficulty}
                  </span>
                  <span className="rounded-full bg-indigo-50 px-3 py-1 text-sm font-semibold text-indigo-800">
                    {selectedPattern?.name ?? "Pattern"}
                  </span>
                </div>
              </div>
              <p className="mt-6 whitespace-pre-wrap leading-7 text-slate-700">
                {selectedProblem.description ||
                  "No problem description has been added yet. Use this practice to record an attempt and receive learning feedback."}
              </p>
              {!selectedProblem.test_cases_available && (
                <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                  Evaluation is unavailable for this problem until its test cases are configured.
                </p>
              )}

              <form onSubmit={submitAttempt} className="mt-8 space-y-5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block text-sm font-medium text-slate-700">
                    Problem
                    <select
                      value={problemId}
                      onChange={(event) => {
                        setProblemId(event.target.value);
                        setFeedback(null);
                      }}
                      className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                    >
                      {problems.map((problem) => (
                        <option key={problem.id} value={problem.id}>
                          {problem.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm font-medium text-slate-700">
                    Learner ID
                    <input
                      type="number"
                      min="1"
                      value={userId}
                      onChange={(event) => setUserId(event.target.value)}
                      placeholder="Enter your user ID"
                      required
                      className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5"
                    />
                  </label>
                </div>

                <label className="block text-sm font-medium text-slate-700">
                  Language
                  <select
                    value={language}
                    onChange={(event) => setLanguage(event.target.value)}
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 sm:max-w-xs"
                  >
                    {["python", "java"].map(
                      (item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ),
                    )}
                  </select>
                </label>

                <label className="block text-sm font-medium text-slate-700">
                  Your solution or notes
                  <textarea
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    rows={12}
                    required
                    placeholder="Write or paste your solution here…"
                    className="mt-2 w-full resize-y rounded-xl border border-slate-300 bg-slate-950 p-4 font-mono text-sm leading-6 text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  />
                </label>

                <fieldset className="rounded-xl border border-slate-200 p-4">
                  <legend className="px-1 text-sm font-semibold text-slate-800">
                    Evaluation
                  </legend>
                  <p className="mb-3 text-xs text-slate-500">
                    The backend evaluates source code in an external sandbox.
                  </p>
                </fieldset>


                {submitError && (
                  <p role="alert" className="text-sm font-medium text-red-700">
                    {submitError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={submitting || loadingProblems || !selectedProblem.test_cases_available}
                  className="w-full rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-60 sm:w-auto"
                >
                  {submitting ? "Evaluating…" : "Evaluate solution"}
                </button>
              </form>
            </section>

            <aside className="space-y-6">
              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-bold">Learning feedback</h2>
                {!feedback ? (
                  <p className="mt-3 text-sm leading-6 text-slate-600">
                    Submit an attempt to see your result, mastery, mistake
                    feedback, and suggested next problem.
                  </p>
                ) : (
                  <div className="mt-4 space-y-4">
                    <p
                      className={`rounded-lg px-3 py-2 text-sm font-semibold ${
                        feedback.submission.is_correct
                          ? "bg-emerald-50 text-emerald-800"
                          : "bg-amber-50 text-amber-900"
                      }`}
                    >
                      {feedback.submission.status}
                    </p>
                    {feedback.submission.evaluation_details?.failed_test && (
                      <p className="text-sm text-slate-600">
                        Failed test {feedback.submission.evaluation_details.failed_test}
                      </p>
                    )}
                    {feedback.submission.evaluation_details?.error && (
                      <pre className="overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
                        {feedback.submission.evaluation_details.error}
                      </pre>
                    )}
                    {feedback.submission.evaluation_details?.actual_output && (
                      <div>
                        <p className="text-xs font-semibold uppercase text-slate-500">Your output</p>
                        <pre className="mt-1 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
                          {feedback.submission.evaluation_details.actual_output}
                        </pre>
                      </div>
                    )}
                    {feedback.submission.evaluation_details?.feedback && (
                      <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
                        <p className="font-semibold">{feedback.submission.evaluation_details.feedback.explanation}</p>
                        <p><span className="font-semibold">Hint:</span> {feedback.submission.evaluation_details.feedback.hint}</p>
                        <p><span className="font-semibold">Suggested correction:</span> {feedback.submission.evaluation_details.feedback.correction}</p>
                        <p className="text-xs text-slate-500">Feedback: {feedback.submission.evaluation_details.feedback.provider}</p>
                      </div>
                    )}
                    {feedback.submission.mastery ? (
                      <div className="rounded-xl bg-indigo-50 p-4">
                        <p className="text-sm font-medium text-indigo-900">
                          Updated pattern mastery
                        </p>
                        <p className="mt-1 text-3xl font-bold text-indigo-950">
                          {feedback.submission.mastery.mastery_score.toFixed(1)}
                          <span className="ml-1 text-base font-medium">
                            / 100
                          </span>
                        </p>
                      </div>
                    ) : (
                      <p className="text-sm text-slate-600">
                        Mastery score is not available for this pattern yet.
                      </p>
                    )}

                    {feedback.submission.recommendation && (
                      <div className="rounded-xl border border-slate-200 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Recommended next
                        </p>
                        <p className="mt-2 font-bold">
                          {feedback.submission.recommendation.title}
                        </p>
                        <p className="mt-1 text-sm text-slate-600">
                          {feedback.submission.recommendation.difficulty} ·{" "}
                          {feedback.submission.recommendation.pattern}
                        </p>
                        <p className="mt-2 text-sm leading-5 text-slate-600">
                          {feedback.submission.recommendation.reason}
                        </p>
                        <button
                          type="button"
                          onClick={openRecommendedProblem}
                          className="mt-4 w-full rounded-lg border border-indigo-200 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50"
                        >
                          Practice this problem
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </section>
              <p className="px-1 text-xs leading-5 text-slate-500">
                Code runs only through the configured external sandbox judge.
              </p>
            </aside>
          </div>
        ) : null}
      </div>
    </main>
  );
}
