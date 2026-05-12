import FocusControl from "@/components/FocusControl";
import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";
import { formatBriefEditionTitle, formatEditionStamp, formatEssentialStoryCount } from "@/utils/edition";

export default function BrandHeader({
  availableSources = [],
  storyCount,
  generatedAt,
}: {
  availableSources?: string[];
  storyCount?: number;
  generatedAt?: string;
}) {
  const city = process.env.NEXT_PUBLIC_CITY_NAME || "Islamabad";
  const dateLabel = formatEditionStamp();
  const storyCountLabel = typeof storyCount === "number" ? formatEssentialStoryCount(storyCount) : undefined;
  const editionTitle = formatBriefEditionTitle(generatedAt);

  return (
    <header className="sb-home-header">
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_260px] xl:items-start xl:gap-6">
        <div className="max-w-[760px]">
          <div className="flex items-center gap-3">
            <Logo size={28} decorative className="opacity-95 flex-shrink-0" />
            <div>
              <p className="text-[26px] font-semibold tracking-tight" style={{ color: "var(--teal)" }}>
                Saaf Baat
              </p>
              <div className="mt-1 flex items-center gap-2 flex-wrap text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: "var(--ink-muted)" }}>
                <span>{city}</span>
                <span>•</span>
                <span>{dateLabel}</span>
                {storyCountLabel ? (
                  <>
                    <span>•</span>
                    <span>{storyCountLabel}</span>
                  </>
                ) : null}
              </div>
            </div>
          </div>

          <div className="mt-2">
            <div
              className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.2em]"
              style={{
                background: "color-mix(in srgb, var(--surface) 80%, var(--surface-base))",
                border: "1px solid color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
                color: "var(--ink-muted)",
              }}
            >
              <span>Pakistan morning brief</span>
              <span style={{ color: "var(--teal)" }}>Edition</span>
            </div>
            <h1 className="sb-display-home mt-2">
              {editionTitle}
            </h1>
            <p className="text-sm mt-1 max-w-lg leading-relaxed" style={{ color: "var(--ink-muted)" }}>
              Saaf Baat for {city}.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2.5 xl:items-start xl:max-w-[260px] xl:pt-1">
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <FocusControl availableSources={availableSources} size="sm" />
          </div>

          <div className="sb-status-pill">
            <div className="sb-status-icon">
              <Logo size={16} decorative />
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color: "var(--ink-muted)" }}>
                Today&apos;s edition
              </p>
              <p className="text-sm font-semibold" style={{ color: "var(--teal)" }}>
                {formatEssentialStoryCount(storyCount || 0)}
              </p>
              <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--ink-muted)" }}>
                Ranked for public impact first.
              </p>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
