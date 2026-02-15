import FocusControl from "@/components/FocusControl";
import Logo from "@/components/Logo";
import ThemeToggle from "@/components/ThemeToggle";

export default function BrandHeader({
  availableSources = [],
  storyCount,
}: {
  availableSources?: string[];
  storyCount?: number;
}) {
  return (
    <header className="px-2 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Logo size={26} />
          <div className="leading-none">
            <p className="text-lg font-semibold tracking-tight" style={{ color: "var(--ink)" }}>
              Saaf Baat
            </p>
            <p className="text-xs sb-meta mt-1">Morning brief</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <FocusControl availableSources={availableSources} size="sm" />
        </div>
      </div>
      {typeof storyCount === "number" ? (
        <p className="text-xs sb-meta mt-2 pl-0.5">{storyCount} essential stories</p>
      ) : null}
    </header>
  );
}
