import Chip from "./primitives/Chip";
import type { EntityDTO } from "@/data/types";

export default function TrustPreview({
  confirmedFacts,
  debatedClaims,
  layout = "default",
}: {
  confirmedFacts: EntityDTO[];
  debatedClaims: EntityDTO[];
  layout?: "default" | "compact";
}) {
  const agreed = confirmedFacts.slice(0, 2);
  const debated = debatedClaims.slice(0, 1);

  if (layout === "compact") {
    return (
      <div className="flex gap-1.5 mt-2 flex-wrap items-center">
        {agreed.map((e, i) => (
          <Chip key={`a-${i}`} label={e.text} variant="agreed" />
        ))}
        {debated.map((e, i) => (
          <Chip key={`d-${i}`} label={e.text} variant="debated" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
      <div>
        <span className="text-xs font-medium" style={{ color: "var(--ink-muted)" }}>
          Agreed across sources
        </span>
        <div className="flex gap-1.5 mt-1 flex-wrap">
          {agreed.map((e, i) => (
            <Chip key={i} label={e.text} variant="agreed" />
          ))}
          {agreed.length === 0 ? (
            <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
              —
            </span>
          ) : null}
        </div>
      </div>
      <div>
        <span className="text-xs font-medium" style={{ color: "var(--ink-muted)" }}>
          Debated / emerging
        </span>
        <div className="flex gap-1.5 mt-1 flex-wrap">
          {debated.map((e, i) => (
            <Chip key={i} label={e.text} variant="debated" />
          ))}
          {debated.length === 0 ? (
            <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
              —
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
