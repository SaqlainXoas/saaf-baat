"use client";

import { useEffect, useRef, useState, type TouchEvent } from "react";
import Link from "next/link";
import StoryCard from "./StoryCard";
import type { StoryCardData } from "@/data/types";

const DEPTH_STYLE: { transform: string; opacity: number; zIndex: number }[] = [
  { transform: "scale(1)", opacity: 1, zIndex: 10 },
  { transform: "translate(7px, 11px) scale(0.978)", opacity: 0.76, zIndex: 9 },
  { transform: "translate(14px, 20px) scale(0.962)", opacity: 0.54, zIndex: 8 },
  { transform: "translate(20px, 29px) scale(0.948)", opacity: 0.38, zIndex: 7 },
];
const SWIPE_THRESHOLD_PX = 56;

export default function Deck({ stories }: { stories: StoryCardData[] }) {
  const [idx, setIdx] = useState(0);
  const total = stories.length;
  const [reduceMotion, setReduceMotion] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const touchStartX = useRef<number | null>(null);
  const touchStartY = useRef<number | null>(null);
  const suppressTap = useRef(false);

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

  function handleTouchStart(event: TouchEvent<HTMLDivElement>) {
    const touch = event.touches[0];
    touchStartX.current = touch.clientX;
    touchStartY.current = touch.clientY;
    setDragging(false);
    setDragOffset(0);
  }

  function handleTouchMove(event: TouchEvent<HTMLDivElement>) {
    if (touchStartX.current === null || touchStartY.current === null) return;
    const touch = event.touches[0];
    const dx = touch.clientX - touchStartX.current;
    const dy = touch.clientY - touchStartY.current;

    if (Math.abs(dx) <= Math.abs(dy)) return;
    setDragging(true);
    setDragOffset(dx);
  }

  function handleTouchEnd() {
    if (!dragging) {
      touchStartX.current = null;
      touchStartY.current = null;
      return;
    }

    if (dragOffset <= -SWIPE_THRESHOLD_PX && idx < total - 1) {
      setIdx((current) => current + 1);
    } else if (dragOffset >= SWIPE_THRESHOLD_PX && idx > 0) {
      setIdx((current) => current - 1);
    }

    suppressTap.current = true;
    window.setTimeout(() => {
      suppressTap.current = false;
    }, 140);

    touchStartX.current = null;
    touchStartY.current = null;
    setDragging(false);
    setDragOffset(0);
  }

  return (
    <div
      aria-label="Morning brief deck"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
    >
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
                  : dragging && depth === 0
                    ? "none"
                  : "transform 0.24s ease-out, opacity 0.24s ease-out",
                transformOrigin: "50% 50%",
                filter: depth === 0 ? "none" : "saturate(0.92)",
                transform:
                  depth === 0 && dragging ? `${ds.transform} translateX(${dragOffset}px)` : ds.transform,
              }}
            >
              {depth === 0 ? (
                <Link
                  href={`/stories/${story.story_id}`}
                  className="block"
                  onClick={(event) => {
                    if (!suppressTap.current) return;
                    event.preventDefault();
                  }}
                >
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
