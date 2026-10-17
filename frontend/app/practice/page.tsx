"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  apiRequest,
  LEARNER_STORAGE_KEY,
  type Pattern,
  type Problem,
  type Submission,
  type User,
} from "./api";

interface AttemptFeedback {
  submission: Submission;
}

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
    // Storage can be unavailable in private windows; the field still works.
  }
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

  const [learnerName, setLearnerName] = useState("");
  const [learnerEmail, setLearnerEmail] = useState("");
  const [creatingLearner, setCreatingLearner] = useState(false);
  const [learnerMessage, setLearnerMessage] = useState("");
  const [learnerError, setLearnerError] = useState("");

  // Guards against a second click or Enter press landing before React
  // re-renders the disabled button.
  const submitInFlight = useRef(false);

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
          const query = new URLSearchParams(window.location.search);
          const requestedPatternId = Number(query.get("pattern_id"));
          const requestedProblemId = Number(query.get("problem_id"));
          const requestedProblem = problemList.find(
            (problem) =>
              problem.id === requestedProblemId &&
              problem.test_cases_available &&
              (!Number.isInteger(requestedPatternId) ||
                requestedPatternId <= 0 ||
                problem.pattern_id === requestedPatternId),
          );
          const firstRunnable =
            requestedProblem ??
            problemList.find(
              (problem) =>
                problem.test_cases_available &&
                Number.isInteger(requestedPatternId) &&
                requestedPatternId > 0 &&
                problem.pattern_id === requestedPatternId,
            ) ??
            problemList.find((problem) => problem.test_cases_available) ??
            problemList[0];
          setProblemId(firstRunnable ? String(firstRunnable.id) : "");
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
        if (!cancelled) {
          setLoadingProblems(false);
          // Restore the remembered learner ID after the first await so this
          // never runs synchronously inside the effect body.
          setUserId((current) => current || readStoredLearnerId());
        }
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
  const runnableCount = useMemo(
    () => problems.filter((problem) => problem.test_cases_available).length,
    [problems],
  );

  function updateLearnerId(value: string) {
    setUserId(value);
    storeLearnerId(value);
  }

  async function submitAttempt(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitInFlight.current) return;
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
    if (!selectedProblem.test_cases_available) {
      setSubmitError("This problem cannot be evaluated until test cases are configured.");
      return;
    }
    if (!code.trim()) {
      setSubmitError("Add your solution before submitting.");
      return;
    }

    submitInFlight.current = true;
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
          : "Your submission could not be evaluated. Please try again.",
      );
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  }

  async function createLearner(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (creatingLearner) return;
    setLearnerError("");
    setLearnerMessage("");
    if (!learnerName.trim() || !learnerEmail.trim()) {
      setLearnerError("Enter a name and an email address.");
      return;
    }
    setCreatingLearner(true);
    try {
      const user = await apiRequest<User>("/users/", {
        method: "POST",
        body: JSON.stringify({ name: learnerName.trim(), email: learnerEmail.trim() }),
      });
      updateLearnerId(String(user.id));
      setLearnerMessage(`Created learner #${user.id} for ${user.name}.`);
      setLearnerName("");
      setLearnerEmail("");
    } catch (error) {
      setLearnerError(
        error instanceof Error ? error.message : "Could not create the learner.",
      );
    } finally {
      setCreatingLearner(false);
    }
  }

  function openRecommendedProblem() {
    if (!feedback?.submission.recommendation) return;
    setProblemId(String(feedback.submission.recommendation.problem_id));
    setFeedback(null);
    setCode("");
    setSubmitError("");
  }

  const verdict = feedback?.submission;
  const details = verdict?.evaluation_details;

  return (
    <main className="min-h-screen bg-[#f5f6f8] px-4 py-8 text-slate-900 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.16em] text-indigo-600">
              CodeX · Practice
            </p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight">
              Learn by solving
            </h1>
            <p className="mt-2 max-w-2xl text-slate-600">
              Solve a problem, get a sandboxed verdict, and use the feedback to
              choose what to practice next.
            </p>
          </div>
          <Link
            href="/"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400"
          >
            Home
          </Link>
          <Link
            href="/dashboard"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400"
          >
            Progress dashboard
          </Link>
          <Link
            href="/recommendations"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400"
          >
            Next problem
          </Link>
          <Link
            href="/revisions"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:border-indigo-400"
          >
            Revisions
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
                <div className="flex flex-wrap gap-2">
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
                  "No console input/output contract has been added for this problem yet."}
              </p>
              {selectedProblem.url && (
                <a
                  href={selectedProblem.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-block text-sm font-medium text-indigo-700 hover:underline"
                >
                  Original problem statement ↗
                </a>
              )}
              {selectedProblem.test_cases_available ? (
                selectedProblem.sample_cases.length > 0 && (
                  <div className="mt-5 space-y-3">
                    <p className="text-sm font-semibold text-slate-800">
                      Sample cases (read from standard input, print to standard output)
                    </p>
                    {selectedProblem.sample_cases.map((sample, index) => (
                      <div key={index} className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="text-xs font-semibold uppercase text-slate-500">
                            Input {index + 1}
                          </p>
                          <pre className="mt-1 overflow-auto rounded-lg bg-slate-100 p-3 text-xs text-slate-800">
                            {sample.input}
                          </pre>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase text-slate-500">
                            Expected output {index + 1}
                          </p>
                          <pre className="mt-1 overflow-auto rounded-lg bg-slate-100 p-3 text-xs text-slate-800">
                            {sample.expected_output}
                          </pre>
                        </div>
                      </div>
                    ))}
                    <p className="text-xs text-slate-500">
                      Hidden cases are also run. Trailing whitespace is ignored when comparing output.
                    </p>
                  </div>
                )
              ) : (
                <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                  Evaluation is unavailable for this problem until its test cases are configured.
                  {runnableCount > 0 && ` ${runnableCount} other problems can be evaluated.`}
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
                        setSubmitError("");
                      }}
                      className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                    >
                      {problems.map((problem) => (
                        <option key={problem.id} value={problem.id}>
                          {problem.title}
                          {problem.test_cases_available ? "" : " (not evaluable)"}
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
                      onChange={(event) => updateLearnerId(event.target.value)}
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
                    <option value="python">Python 3</option>
                    <option value="java">Java (class Main)</option>
                  </select>
                </label>

                <label className="block text-sm font-medium text-slate-700">
                  Your solution
                  <textarea
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    rows={12}
                    required
                    spellCheck={false}
                    placeholder="Read from standard input, print the answer to standard output…"
                    className="mt-2 w-full resize-y rounded-xl border border-slate-300 bg-slate-950 p-4 font-mono text-sm leading-6 text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  />
                </label>

                <p className="text-xs text-slate-500">
                  The backend runs your code in an external sandbox judge and
                  decides the verdict. Nothing is executed in the browser.
                </p>

                {submitError && (
                  <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-800">
                    {submitError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={submitting || loadingProblems || !selectedProblem.test_cases_available}
                  aria-busy={submitting}
                  className="w-full rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-wait disabled:opacity-60 sm:w-auto"
                >
                  {submitting ? "Evaluating… (up to 45s)" : "Evaluate solution"}
                </button>
              </form>
            </section>

            <aside className="space-y-6">
              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-bold">Learning feedback</h2>
                {!verdict ? (
                  <p className="mt-3 text-sm leading-6 text-slate-600">
                    Submit an attempt to see your verdict, mastery, mistake
                    feedback, and suggested next problem.
                  </p>
                ) : (
                  <div className="mt-4 space-y-4">
                    <div
                      role="status"
                      className={`rounded-lg border px-3 py-2 text-sm font-semibold ${
                        verdict.is_correct
                          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                          : "border-red-200 bg-red-50 text-red-800"
                      }`}
                    >
                      {verdict.is_correct ? "✓ Accepted" : `✗ ${verdict.status}`}
                      {!verdict.is_correct && details?.failed_test && (
                        <span className="block text-xs font-normal">
                          Failed on test case {details.failed_test}
                        </span>
                      )}
                    </div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                      Verified execution result from Judge0
                    </p>
                    {details?.error && (
                      <div>
                        <p className="text-xs font-semibold uppercase text-slate-500">Judge output</p>
                        <pre className="mt-1 max-h-60 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
                          {details.error}
                        </pre>
                      </div>
                    )}
                    {!verdict.is_correct && details?.actual_output !== undefined && details?.actual_output !== null && (
                      <div>
                        <p className="text-xs font-semibold uppercase text-slate-500">Your output</p>
                        <pre className="mt-1 max-h-60 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">
                          {details.actual_output || "(empty)"}
                        </pre>
                      </div>
                    )}
                    {details?.feedback && (
                      <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm">
                        <p className="text-xs font-semibold uppercase tracking-wide text-amber-900">
                          {details.feedback.provider === "ai" ? "AI-generated explanation (advisory)" : "Rule-based explanation"}
                        </p>
                        <p className="font-semibold">{details.feedback.explanation}</p>
                        <p><span className="font-semibold">Hint:</span> {details.feedback.hint}</p>
                        <p><span className="font-semibold">Suggested correction:</span> {details.feedback.correction}</p>
                        <p className="text-xs text-slate-500">
                          This explanation does not determine the verdict.
                        </p>
                      </div>
                    )}
                    {verdict.mastery ? (
                      <div className="rounded-xl bg-indigo-50 p-4">
                        <p className="text-sm font-medium text-indigo-900">
                          Updated pattern mastery
                        </p>
                        <p className="mt-1 text-3xl font-bold text-indigo-950">
                          {verdict.mastery.mastery_score.toFixed(1)}
                          <span className="ml-1 text-base font-medium">
                            / 100
                          </span>
                        </p>
                        {typeof verdict.mastery.total_attempts === "number" && (
                          <p className="mt-1 text-xs text-indigo-900">
                            {verdict.mastery.correct_attempts ?? 0} of {verdict.mastery.total_attempts} attempts correct
                            {typeof verdict.mastery.consecutive_correct === "number" &&
                              ` · streak ${verdict.mastery.consecutive_correct}`}
                          </p>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-600">
                        Mastery score is not available for this pattern yet.
                      </p>
                    )}

                    {verdict.recommendation && (
                      <div className="rounded-xl border border-slate-200 p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Recommended next
                        </p>
                        <p className="mt-2 font-bold">
                          {verdict.recommendation.title}
                        </p>
                        <p className="mt-1 text-sm text-slate-600">
                          {verdict.recommendation.difficulty} ·{" "}
                          {verdict.recommendation.pattern}
                        </p>
                        <p className="mt-2 text-sm leading-5 text-slate-600">
                          {verdict.recommendation.reason}
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

              <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="text-lg font-bold">Need a learner ID?</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Create a learner once and the ID is filled in for you.
                </p>
                <form onSubmit={createLearner} className="mt-4 space-y-3">
                  <input
                    type="text"
                    value={learnerName}
                    onChange={(event) => setLearnerName(event.target.value)}
                    placeholder="Name"
                    autoComplete="name"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                  <input
                    type="email"
                    value={learnerEmail}
                    onChange={(event) => setLearnerEmail(event.target.value)}
                    placeholder="Email"
                    autoComplete="email"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                  {learnerError && (
                    <p role="alert" className="text-sm text-red-700">{learnerError}</p>
                  )}
                  {learnerMessage && (
                    <p role="status" className="text-sm text-emerald-700">{learnerMessage}</p>
                  )}
                  <button
                    type="submit"
                    disabled={creatingLearner}
                    className="w-full rounded-lg border border-indigo-200 px-3 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-60"
                  >
                    {creatingLearner ? "Creating…" : "Create learner"}
                  </button>
                </form>
              </section>

              <p className="px-1 text-xs leading-5 text-slate-500">
                Code runs only through the configured external sandbox judge.
                {runnableCount > 0 && ` ${runnableCount} of ${problems.length} problems have runnable test cases.`}
              </p>
            </aside>
          </div>
        ) : null}
      </div>
    </main>
  );
}
