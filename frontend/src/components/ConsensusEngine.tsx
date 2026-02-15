import type { EntityDTO } from "@/data/types";

export default function ConsensusEngine({
  confirmedFacts,
  debatedClaims,
  sourceCount,
}: {
  confirmedFacts: EntityDTO[];
  debatedClaims: EntityDTO[];
  sourceCount: number;
}) {
  const agreed = confirmedFacts.slice(0, 2);
  const debated = debatedClaims.slice(0, 1);

  return (
    <section className="mt-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold tracking-tight" style={{ color: "var(--ink)" }}>
          Consensus Engine
        </h3>
        <span className="text-xs" style={{ color: "var(--ink-muted)" }}>
          Sources assessed: {sourceCount}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div
          className="rounded-xl p-3"
          style={{
            background: "var(--mint-bg)",
            border: "1px solid rgba(82, 183, 163, 0.18)",
            borderRadius: "var(--radius-xl)",
          }}
        >
          <h4 className="text-xs font-bold tracking-wide mb-2" style={{ color: "var(--ink)" }}>
            What&apos;s agreed
          </h4>
          {agreed.length ? (
            <ul className="space-y-2">
              {agreed.map((e, i) => (
                <li key={i} className="flex items-start gap-2 text-xs" style={{ color: "var(--ink)" }}>
                  <span
                    className="w-4 h-4 flex-shrink-0 rounded-md flex items-center justify-center text-xs font-bold"
                    style={{
                      background: "var(--surface)",
                      border: "1px solid var(--hairline)",
                      color: "var(--teal)",
                    }}
                  >
                    ✓
                  </span>
                  <span>{e.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
              No clear consensus yet.
            </p>
          )}
        </div>

        <div
          className="rounded-xl p-3"
          style={{
            background: "var(--amber-bg)",
            border: "1px solid rgba(240, 195, 122, 0.28)",
            borderRadius: "var(--radius-xl)",
          }}
        >
          <h4 className="text-xs font-bold tracking-wide mb-2" style={{ color: "var(--ink)" }}>
            What&apos;s debated
          </h4>
          {debated.length ? (
            <ul className="space-y-2">
              {debated.map((e, i) => (
                <li key={i} className="flex items-start gap-2 text-xs" style={{ color: "var(--ink)" }}>
                  <span
                    className="w-4 h-4 flex-shrink-0 rounded-md flex items-center justify-center text-xs font-bold"
                    style={{ background: "var(--surface)", border: "1px solid var(--hairline)" }}
                  >
                    ?
                  </span>
                  <span>{e.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs" style={{ color: "var(--ink-muted)" }}>
              No major debated claims.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
