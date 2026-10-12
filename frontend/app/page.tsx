import Link from "next/link";

const steps = [
  {
    title: "Pick a problem",
    body: "Each runnable problem has a console input/output contract and visible sample cases.",
  },
  {
    title: "Submit Python or Java",
    body: "Your code is sent to the backend, which runs it in an external sandbox judge. The browser never decides the verdict.",
  },
  {
    title: "Learn from the result",
    body: "Verdicts update pattern mastery, record mistakes with feedback, and recommend what to practice next.",
  },
];

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col bg-[#f5f6f8] px-4 py-12 text-slate-900 sm:px-8">
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col justify-center">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-indigo-600">
          CodeX
        </p>
        <h1 className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl">
          Master coding patterns, one evaluated attempt at a time.
        </h1>
        <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
          A practice workspace that grades real code in a sandbox, tracks
          mastery per pattern, and turns every mistake into a next step.
        </p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/practice"
            className="rounded-xl bg-indigo-600 px-6 py-3 text-center font-semibold text-white transition hover:bg-indigo-700"
          >
            Start practicing
          </Link>
          <Link
            href="/dashboard"
            className="rounded-xl border border-indigo-200 bg-white px-6 py-3 text-center font-semibold text-indigo-700 transition hover:border-indigo-400"
          >
            View progress
          </Link>
          <Link
            href="/recommendations"
            className="rounded-xl border border-slate-300 bg-white px-6 py-3 text-center font-semibold text-slate-800 transition hover:border-indigo-400"
          >
            Next problem
          </Link>
          <Link
            href="/revisions"
            className="rounded-xl border border-slate-300 bg-white px-6 py-3 text-center font-semibold text-slate-800 transition hover:border-indigo-400"
          >
            Due revisions
          </Link>
          <a
            href="/api/backend/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-xl border border-slate-300 bg-white px-6 py-3 text-center font-semibold text-slate-800 transition hover:border-indigo-400"
          >
            API docs
          </a>
        </div>

        <ol className="mt-12 grid gap-4 sm:grid-cols-3">
          {steps.map((step, index) => (
            <li
              key={step.title}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
                Step {index + 1}
              </p>
              <h2 className="mt-2 text-lg font-bold">{step.title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </main>
  );
}
