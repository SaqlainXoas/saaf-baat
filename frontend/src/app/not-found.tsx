import Link from "next/link";

export default function NotFound() {
  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center p-8 text-center"
      style={{ background: "var(--paper)" }}
    >
      <p className="sb-kicker">404</p>
      <h1 className="sb-display-mobile mt-2">This page isn&apos;t part of the brief</h1>
      <p className="text-sm mt-3 max-w-sm leading-relaxed" style={{ color: "var(--ink-muted)" }}>
        The brief is finite and it changes every morning. Whatever was here has either
        moved on or never existed.
      </p>
      <Link
        href="/"
        className="mt-5 inline-block px-5 py-2 rounded-xl text-sm font-bold sb-focusable"
        style={{ background: "var(--surface)", border: "1px solid var(--hairline)", color: "var(--ink)" }}
      >
        Read today&apos;s brief
      </Link>
    </div>
  );
}
