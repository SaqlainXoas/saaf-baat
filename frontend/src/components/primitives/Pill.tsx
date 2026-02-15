import { normaliseImpact } from "@/utils/impact";

/** Back-compat export for tests and call sites. */
export function getPillText(raw: string): string {
  return normaliseImpact(raw);
}

export default function Pill({ label }: { label: string }) {
  const text = getPillText(label);

  return (
    <span
      className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-xs font-bold tracking-wide"
      style={{
        background: "color-mix(in srgb, var(--mint-bg) 70%, var(--surface))",
        border: "1px solid rgba(82, 183, 163, 0.2)",
      }}
    >
      {/* Brand micro-icon */}
      <span
        className="relative inline-block w-3.5 h-3.5 rounded-md flex-shrink-0"
        style={{
          background: "linear-gradient(135deg, var(--teal), var(--teal-light))",
        }}
      >
        <span
          className="absolute rounded-full bg-white"
          style={{ top: 2.5, right: 2.5, width: 4.5, height: 4.5, opacity: 0.92 }}
        />
      </span>
      {text}
    </span>
  );
}
