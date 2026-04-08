"use client";

import { useMemo, useState } from "react";
import type { StoryArticleData } from "@/data/types";
import { capitalise, formatSourceTimestamp } from "@/utils/storyMeta";

const SOURCE_BADGE_BG: Record<string, string> = {
  dawn: "#52B7A3",
  geo: "#22c55e",
  tribune: "#6B7280",
  ary: "#ef4444",
  thenews: "#0ea5e9",
  samaa: "#f59e0b",
};

const FALLBACK_BADGE_BG = ["#64748b", "#0f766e", "#1d4ed8", "#b45309", "#7c3aed", "#be123c"];

function sourceBadgeColor(source: string) {
  const key = source.trim().toLowerCase();
  const known = SOURCE_BADGE_BG[key];
  if (known) return known;

  let hash = 0;
  for (let index = 0; index < key.length; index += 1) {
    hash = ((hash << 5) - hash + key.charCodeAt(index)) | 0;
  }
  return FALLBACK_BADGE_BG[Math.abs(hash) % FALLBACK_BADGE_BG.length];
}

export default function OriginalSourcesList({
  articles,
}: {
  articles: StoryArticleData[];
}) {
  const [expanded, setExpanded] = useState(false);
  const listId = "original-sources-list";
  const canExpand = articles.length > 4;
  const intro =
    articles.length === 0
      ? "Original publisher links are still being attached to this brief."
      : articles.length === 1
        ? "This brief currently links to one original publisher report."
        : "The original publisher reports supporting this brief.";

  const visible = useMemo(() => {
    if (!canExpand) return articles;
    return expanded ? articles : articles.slice(0, 4);
  }, [articles, canExpand, expanded]);

  return (
    <section className="mt-10">
      <div className="flex items-end justify-between gap-4 mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight" style={{ color: "var(--ink)" }}>
            Original sources
          </h3>
          <p className="text-sm mt-1" style={{ color: "var(--ink-muted)" }}>
            {intro}
          </p>
        </div>
      </div>
      {canExpand ? (
        <p className="text-xs mb-3" style={{ color: "var(--ink-muted)" }}>
          Showing {visible.length} of {articles.length} reports.
        </p>
      ) : null}

      <div id={listId} className="space-y-2">
        {!visible.length ? (
          <div className="sb-source-row-empty rounded-[22px] px-4 py-4 text-sm">
            <span style={{ color: "var(--ink-muted)" }}>
              Original-source links are not available for this story yet.
            </span>
          </div>
        ) : null}
        {visible.map((a) => (
          (() => {
            const publishedAt = formatSourceTimestamp(a.publish_date || undefined);

            return (
              <div
                key={a.id}
                className="sb-source-row flex items-center justify-between gap-3 p-4 rounded-[22px]"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <span
                    className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
                    style={{ background: sourceBadgeColor(a.source) }}
                  >
                    {a.source[0]?.toUpperCase()}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold mb-1" style={{ color: "var(--ink-muted)" }}>
                      {capitalise(a.source)}
                    </p>
                    <p className="text-sm font-semibold truncate" style={{ color: "var(--ink)" }}>
                      {a.headline}
                    </p>
                    {publishedAt ? (
                      <p className="text-[11px] mt-1" style={{ color: "var(--ink-muted)" }}>
                        Published {publishedAt}
                      </p>
                    ) : null}
                  </div>
                </div>

                <a
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="sb-focusable text-xs font-semibold flex-shrink-0 px-2 py-1 rounded-lg"
                  aria-label={`Read ${capitalise(a.source)} report: ${a.headline}`}
                  style={{ color: "var(--ink-muted)" }}
                >
                  Read
                </a>
              </div>
            );
          })()
        ))}
      </div>

      {canExpand ? (
        <button
          type="button"
          className="w-full mt-3 py-2.5 rounded-xl text-sm font-bold sb-focusable"
          style={{
            background: "color-mix(in srgb, var(--surface) 92%, var(--surface-base))",
            border: "1px solid color-mix(in srgb, var(--outline-ghost) 76%, transparent)",
            color: "var(--ink)",
          }}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-controls={listId}
        >
          {expanded ? "Show fewer reports" : `View all ${articles.length} reports →`}
        </button>
      ) : null}
    </section>
  );
}
