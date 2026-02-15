"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import StoryCard from "./StoryCard";
import type { StoryCardData } from "@/data/types";

const DEPTH_STYLE: { transform: string; opacity: number; zIndex: number }[] = [
  { transform: "scale(1)", opacity: 1, zIndex: 10 },
  { transform: "translate(7px, 11px) scale(0.978)", opacity: 0.76, zIndex: 9 },
  { transform: "translate(14px, 20px) scale(0.962)", opacity: 0.54, zIndex: 8 },
  { transform: "translate(20px, 29px) scale(0.948)", opacity: 0.38, zIndex: 7 },
];

export default function Deck({ stories }: { stories: StoryCardData[] }) {
  const [idx, setIdx] = useState(0);
  const total = stories.length;
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const update = () => setReduceMotion(mq.matches);
    update();
    mq.addEventListener?.("change", update);
    return () => mq.removeEventListener?.("change", update);
  }, []);

  // Indices of cards currently visible (current + up-to-3 behind)
  const visible: number[] = [];
  for (let i = 0; i < 4 && idx + i < total; i++) visible.push(idx + i);

  return (
    <div aria-label="Morning brief deck">
      <div className="relative" style={{ height: 430 }}>
        {[...visible].reverse().map((si) => {
          const depth = si - idx;
          const story = stories[si];
          const ds = DEPTH_STYLE[depth];

          return (
            <div
              key={story.story_id}
              className="absolute inset-x-0 top-0"
              style={{
                ...ds,
                transition: reduceMotion
                  ? "none"
                  : "transform 0.24s ease-out, opacity 0.24s ease-out",
                transformOrigin: "50% 50%",
                filter: depth === 0 ? "none" : "saturate(0.92)",
              }}
            >
              {depth === 0 ? (
                <Link href={`/stories/${story.story_id}`} className="block">
                  <StoryCard story={story} />
                </Link>
              ) : (
                <button
                  className="block w-full text-left"
                  onClick={() => setIdx(si)}
                  aria-label={`Switch to story: ${story.headline}`}
                >
                  <StoryCard story={story} isBackground />
                </button>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex flex-col items-center gap-1.5 mt-4">
        <div className="flex gap-1.5">
          {stories.map((_, i) => (
            <button
              key={i}
              className="w-2 h-2 rounded-full transition-colors"
              style={{
                background: i === idx ? "var(--teal)" : "var(--hairline)",
              }}
              onClick={() => setIdx(i)}
              aria-label={`Go to story ${i + 1}`}
            />
          ))}
        </div>

        <span className="text-xs font-medium" style={{ color: "var(--ink-muted)" }}>
          {idx + 1} / {total}
        </span>
      </div>

      {idx >= total - 1 && (
        <p
          className="text-center text-sm mt-4 leading-relaxed"
          style={{ color: "var(--ink-muted)" }}
        >
          You&apos;re all caught up.<br />Enjoy your day.
        </p>
      )}
    </div>
  );
}
