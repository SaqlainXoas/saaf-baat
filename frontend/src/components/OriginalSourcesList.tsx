"use client";

import { useMemo, useState } from "react";
import type { StoryArticleData } from "@/data/types";

const SOURCE_BADGE_BG: Record<string, string> = {
  dawn: "#52B7A3",
  geo: "#22c55e",
  tribune: "#6B7280",
  ary: "#ef4444",
  thenews: "#0ea5e9",
  samaa: "#f59e0b",
};

const FALLBACK_BADGE_BG = ["#64748b", "#0f766e", "#1d4ed8", "#b45309", "#7c3aed", "#be123c"];

function capitalise(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

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
  const canExpand = articles.length > 4;

  const visible = useMemo(() => {
    if (!canExpand) return articles;
    return expanded ? articles : articles.slice(0, 4);
  }, [articles, canExpand, expanded]);

  return (
    <section className="mt-6">
      <h3 className="text-sm font-bold tracking-tight mb-3" style={{ color: "var(--ink)" }}>
        Original sources
      </h3>

      <div className="space-y-2">
        {visible.map((a) => (
          <div
            key={a.id}
            className="flex items-center justify-between gap-3 p-3 rounded-xl"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--hairline)",
              borderRadius: "var(--radius-xl)",
            }}
          >
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <span
                className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
                style={{ background: sourceBadgeColor(a.source) }}
              >
                {a.source[0]?.toUpperCase()}
              </span>
              <p
                className="text-xs font-bold truncate"
                style={{ color: "var(--ink)" }}
              >
                {capitalise(a.source)}: {a.headline}
              </p>
            </div>

            <a
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              className="sb-focusable text-xs font-semibold flex-shrink-0 px-2 py-1 rounded-lg"
              style={{ color: "var(--ink-muted)" }}
            >
              Read
            </a>
          </div>
        ))}
      </div>

      {canExpand ? (
        <button
          className="w-full mt-3 py-2.5 rounded-xl text-sm font-bold sb-focusable"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--hairline)",
            color: "var(--ink)",
          }}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          {expanded ? "Show less" : "View full coverage →"}
        </button>
      ) : null}
    </section>
  );
}
