"use client";

export default function Error({ reset }: { error: Error; reset: () => void }) {
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
        onClick={reset}
        className="mt-4 px-5 py-2 rounded-xl text-sm font-bold text-white"
        style={{ background: "var(--teal)" }}
      >
        Try again
      </button>
    </div>
  );
}
