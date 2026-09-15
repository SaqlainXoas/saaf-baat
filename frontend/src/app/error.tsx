"use client";

// Pages throw when the backend fetch fails so the error is never cached. A
// `reset()` only re-renders on the client and would show this screen again;
// a full reload asks the server, which by then may have a good render.
export default function Error() {
  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center p-8"
      style={{ background: "var(--paper)" }}
    >
      <p className="text-lg font-bold" style={{ color: "var(--ink)" }}>
        Something went wrong
      </p>
      <p className="text-sm mt-2 text-center" style={{ color: "var(--ink-muted)" }}>
        We couldn&apos;t load the brief. Please try again.
      </p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="mt-4 px-5 py-2 rounded-xl text-sm font-bold text-white sb-focusable"
        style={{ background: "var(--teal)" }}
      >
        Try again
      </button>
    </div>
  );
}
