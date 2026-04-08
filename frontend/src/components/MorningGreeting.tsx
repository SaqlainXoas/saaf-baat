"use client";

import FocusControl from "@/components/FocusControl";
import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";
import { formatEditionDate, formatEssentialStoryCount } from "@/utils/edition";

export default function MorningGreeting({
  storyCount,
  availableSources = [],
}: {
  storyCount: number;
  availableSources?: string[];
}) {
  const greeting = "Subah Bakhair";
  const city = process.env.NEXT_PUBLIC_CITY_NAME || "Islamabad";
  const dateStr = formatEditionDate();

  return (
    <header className="sb-hero-shell px-4 pt-5 pb-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div
            className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.18em]"
            style={{
              background: "color-mix(in srgb, var(--surface) 80%, var(--surface-base))",
              border: "1px solid color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
              color: "var(--ink-muted)",
            }}
          >
            <span>{city}</span>
            <span>•</span>
            <span>{dateStr}</span>
          </div>
          <p className="text-[26px] font-semibold tracking-tight mt-2" style={{ color: "var(--teal)" }}>
            Saaf Baat
          </p>
          <h1 className="sb-display-mobile mt-3">
            {greeting},<br />
            {city}.
          </h1>
          <p className="text-sm mt-4 max-w-xs leading-relaxed" style={{ color: "var(--ink-muted)" }}>
            Start with the lead story, then skim the rest in ranked order. The brief stays finite by design.
          </p>
        </div>
        <Logo size={24} decorative className="mt-1" />
      </div>

      <div className="flex items-center justify-between gap-3 mt-4 pt-4 sb-hero-divider">
        <div className="flex items-center gap-2 flex-wrap text-xs" style={{ color: "var(--ink-muted)" }}>
          <span>Pakistan morning brief</span>
          <span className="w-1 h-1 rounded-full" style={{ background: "var(--ink-muted)" }} />
          <span>{formatEssentialStoryCount(storyCount)}</span>
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          {availableSources.length ? <FocusControl availableSources={availableSources} size="sm" /> : null}
        </div>
      </div>
    </header>
  );
}
