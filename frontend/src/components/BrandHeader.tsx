import FocusControl from "@/components/FocusControl";
import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";
import { formatEditionStamp, formatEssentialStoryCount } from "@/utils/edition";

export default function BrandHeader({
  availableSources = [],
  storyCount,
}: {
  availableSources?: string[];
  storyCount?: number;
}) {
  const city = process.env.NEXT_PUBLIC_CITY_NAME || "Islamabad";
  const dateLabel = formatEditionStamp();
  const storyCountLabel = typeof storyCount === "number" ? formatEssentialStoryCount(storyCount) : undefined;

  return (
    <header className="sb-home-header">
      <div className="flex flex-col gap-8 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 flex-wrap text-[11px] font-bold uppercase tracking-[0.2em]" style={{ color: "var(--ink-muted)" }}>
            <Logo size={18} decorative className="opacity-90" />
            <span>{city}</span>
            <span>—</span>
            <span>{dateLabel}</span>
            {storyCountLabel ? (
              <>
                <span>•</span>
                <span>{storyCountLabel}</span>
              </>
            ) : null}
          </div>

          <div className="mt-8">
            <div
              className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{
                background: "color-mix(in srgb, var(--surface) 80%, var(--surface-base))",
                border: "1px solid color-mix(in srgb, var(--outline-ghost) 72%, transparent)",
                color: "var(--ink-muted)",
              }}
            >
              <span>Pakistan morning brief</span>
              <span style={{ color: "var(--teal)" }}>Edition</span>
            </div>
            <p className="text-[30px] font-semibold tracking-tight mt-5" style={{ color: "var(--teal)" }}>
              Saaf Baat
            </p>
            <h1 className="sb-display-home mt-4">
              Subah Bakhair,<br />
              <span className="not-italic">{city}</span>
            </h1>
            <p className="text-[17px] mt-5 max-w-2xl leading-relaxed" style={{ color: "var(--ink-muted)" }}>
              A finite, edited read on what matters this morning, why it matters to ordinary life or public affairs, and what deserves your attention next.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-4 xl:items-end xl:max-w-[300px]">
          <div className="flex items-center gap-2 xl:justify-end">
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
              <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--ink-muted)" }}>
                Ranked for public impact first, then the next things worth knowing.
              </p>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
