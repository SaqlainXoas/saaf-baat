"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Button from "@/components/primitives/Button";
import Sheet from "@/components/primitives/Sheet";
import { IMPACT_LABELS, type ImpactLabel } from "@/utils/impact";
import { parseFilters, serialiseFilters, type FocusFilters } from "@/utils/focusFilters";

const FOCUS_STORAGE_KEY = "saaf-baat-focus";

function capitalise(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function cloneFilters(filters: FocusFilters): FocusFilters {
  return {
    impacts: new Set(filters.impacts),
    sources: new Set(filters.sources),
  };
}

function countFilters(filters: FocusFilters) {
  return filters.impacts.size + filters.sources.size;
}

function saveFiltersToStorage(filters: FocusFilters) {
  if (typeof window === "undefined") return;
  const serialised = serialiseFilters(filters);
  if (!serialised.impact && !serialised.sources) {
    window.localStorage.removeItem(FOCUS_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(FOCUS_STORAGE_KEY, JSON.stringify(serialised));
}

function readFiltersFromStorage(): { impact?: string; sources?: string } | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(FOCUS_STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as { impact?: string; sources?: string };
    if (typeof parsed !== "object" || !parsed) return null;
    return {
      impact: typeof parsed.impact === "string" ? parsed.impact : undefined,
      sources: typeof parsed.sources === "string" ? parsed.sources : undefined,
    };
  } catch {
    return null;
  }
}

export default function FocusControl({
  availableSources,
  size = "sm",
}: {
  availableSources: string[];
  size?: "sm" | "md";
}) {
  const router = useRouter();
  const sp = useSearchParams();

  const spString = sp.toString();
  const current = useMemo(() => parseFilters(new URLSearchParams(spString)), [spString]);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<FocusFilters>(() => cloneFilters(current));

  useEffect(() => {
    const hasUrlFilters = current.impacts.size > 0 || current.sources.size > 0;
    if (!hasUrlFilters) return;
    saveFiltersToStorage(current);
  }, [current]);

  useEffect(() => {
    const hasUrlFilters = current.impacts.size > 0 || current.sources.size > 0;
    if (hasUrlFilters) return;

    const stored = readFiltersFromStorage();
    if (!stored?.impact && !stored?.sources) return;

    const nextParams = new URLSearchParams(spString);
    if (stored.impact) nextParams.set("impact", stored.impact);
    if (stored.sources) nextParams.set("sources", stored.sources);

    const next = nextParams.toString();
    if (next.length && next !== spString) router.replace(`/?${next}`);
  }, [current.impacts.size, current.sources.size, router, spString]);

  useEffect(() => {
    if (!open) return;
    setDraft(cloneFilters(current));
  }, [open, current]);

  const activeCount = countFilters(current);

  function toggleImpact(label: ImpactLabel) {
    setDraft((prev) => {
      const next = cloneFilters(prev);
      if (next.impacts.has(label)) next.impacts.delete(label);
      else next.impacts.add(label);
      return next;
    });
  }

  function toggleSource(source: string) {
    setDraft((prev) => {
      const next = cloneFilters(prev);
      if (next.sources.has(source)) next.sources.delete(source);
      else next.sources.add(source);
      return next;
    });
  }

  function clearAll() {
    setDraft({ impacts: new Set(), sources: new Set() });
  }

  function apply() {
    const nextParams = new URLSearchParams(spString);
    const serialised = serialiseFilters(draft);

    if (serialised.impact) nextParams.set("impact", serialised.impact);
    else nextParams.delete("impact");

    if (serialised.sources) nextParams.set("sources", serialised.sources);
    else nextParams.delete("sources");

    const qs = nextParams.toString();
    saveFiltersToStorage(draft);
    router.push(qs.length ? `/?${qs}` : "/");
    setOpen(false);
  }

  function clearQuickFocus() {
    saveFiltersToStorage({ impacts: new Set(), sources: new Set() });
    router.push("/");
  }

  return (
    <>
      <div className="flex items-center gap-2">
        <Button
          variant="pill"
          size={size}
          onClick={() => setOpen(true)}
          aria-label={activeCount ? `Focus filters active: ${activeCount}` : "Focus"}
        >
          <span>Focus</span>
          {activeCount ? (
            <span
              className="text-xs font-bold px-2 py-0.5 rounded-full"
              style={{ background: "var(--surface-inset)", color: "var(--ink)" }}
            >
              {activeCount}
            </span>
          ) : null}
        </Button>

        {activeCount ? (
          <button
            type="button"
            onClick={clearQuickFocus}
            className="sb-focusable text-xs font-medium px-2.5 py-1.5 rounded-full"
            style={{
              color: "var(--ink-muted)",
              background: "var(--surface)",
              border: "1px solid var(--hairline)",
            }}
          >
            Clear focus
          </button>
        ) : null}
      </div>

      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Focus"
        footer={
          <div className="flex items-center justify-between gap-3">
            <button
              className="sb-focusable text-sm font-medium px-2 py-1 rounded-lg"
              style={{ color: "var(--ink-muted)" }}
              onClick={clearAll}
            >
              Clear all
            </button>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" size="sm" onClick={apply}>
                Apply
              </Button>
            </div>
          </div>
        }
      >
        <div className="space-y-5">
          <section>
            <h3 className="text-xs font-bold tracking-wide" style={{ color: "var(--ink)" }}>
              Impact
            </h3>
            <p className="text-xs mt-1" style={{ color: "var(--ink-muted)" }}>
              Pick what you care about today.
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              {IMPACT_LABELS.map((label) => {
                const active = draft.impacts.has(label);
                return (
                  <button
                    key={label}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleImpact(label)}
                    className="sb-focusable px-3 py-1.5 rounded-full text-xs font-bold tracking-wide transition-colors"
                    style={{
                      background: active ? "var(--mint-bg)" : "var(--surface)",
                      border: `1px solid ${
                        active ? "rgba(82, 183, 163, 0.32)" : "var(--hairline)"
                      }`,
                      color: "var(--ink)",
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-bold tracking-wide" style={{ color: "var(--ink)" }}>
              Sources
            </h3>
            <p className="text-xs mt-1" style={{ color: "var(--ink-muted)" }}>
              Reduce noise by narrowing publishers.
            </p>
            <div className="flex flex-wrap gap-2 mt-3">
              {availableSources.map((source) => {
                const active = draft.sources.has(source);
                return (
                  <button
                    key={source}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleSource(source)}
                    className="sb-focusable px-3 py-1.5 rounded-full text-xs font-bold transition-colors"
                    style={{
                      background: active ? "var(--surface-inset)" : "var(--surface)",
                      border: `1px solid ${active ? "var(--hairline-strong)" : "var(--hairline)"}`,
                      color: "var(--ink)",
                    }}
                  >
                    {capitalise(source)}
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </Sheet>
    </>
  );
}
