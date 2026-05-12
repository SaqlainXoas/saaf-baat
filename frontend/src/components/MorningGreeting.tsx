"use client";

import FocusControl from "@/components/FocusControl";
import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";
import { formatBriefEditionTitle, formatEditionDate, formatEssentialStoryCount } from "@/utils/edition";

export default function MorningGreeting({
  storyCount,
  availableSources = [],
  generatedAt,
}: {
  storyCount: number;
  availableSources?: string[];
  generatedAt?: string;
}) {
  const city = process.env.NEXT_PUBLIC_CITY_NAME || "Islamabad";
  const dateStr = formatEditionDate();
  const editionTitle = formatBriefEditionTitle(generatedAt);

  return (
    <header className="sb-hero-shell px-4 pt-4 pb-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <Logo size={26} decorative className="flex-shrink-0" />
            <div>
              <p className="text-[22px] font-semibold tracking-tight" style={{ color: "var(--teal)" }}>
                Saaf Baat
              </p>
              <p className="text-[11px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--ink-muted)" }}>
                Pakistan morning brief
              </p>
            </div>
          </div>

          <div
            className="mt-3 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.18em]"
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

          <h1 className="sb-display-mobile mt-3">
            {editionTitle}
          </h1>
          <p className="text-sm mt-3 max-w-sm leading-relaxed" style={{ color: "var(--ink-muted)" }}>
            Saaf Baat for {city}, ranked fast.
          </p>
        </div>

        <span
          className="text-xs font-medium rounded-full px-2.5 py-1 flex-shrink-0"
          style={{
            background: "color-mix(in srgb, var(--surface) 88%, var(--surface-base))",
            border: "1px solid color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
            color: "var(--ink-muted)",
          }}
        >
          {formatEssentialStoryCount(storyCount)}
        </span>
      </div>

      <div className="flex items-center justify-between gap-3 mt-4 pt-4 sb-hero-divider">
        <div className="flex items-center gap-2 flex-wrap text-xs" style={{ color: "var(--ink-muted)" }}>
          <span>Ranked for public impact first</span>
          <span className="w-1 h-1 rounded-full" style={{ background: "var(--ink-muted)" }} />
          <span>Finite by design</span>
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          {availableSources.length ? <FocusControl availableSources={availableSources} size="sm" /> : null}
        </div>
      </div>
    </header>
  );
}
