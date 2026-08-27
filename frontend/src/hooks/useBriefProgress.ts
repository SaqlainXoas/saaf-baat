"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Track which card of a finite brief the reader is currently on.
 *
 * Shared by the mobile deck and the desktop brief. Both surfaces need to show
 * "4 / 12" and both were going to grow their own copy of this observer, which
 * is how the two views drift apart: mobile got rank numerals and a counter in
 * Phase 5 and desktop did not.
 *
 * Attach `register(index)` as a card's ref. Returns a 1-based position that
 * stays at 1 before hydration, so the server-rendered markup is stable.
 */
export function useBriefProgress(count: number) {
  const refs = useRef<(HTMLElement | null)[]>([]);
  const [position, setPosition] = useState(1);

  useEffect(() => {
    const nodes = refs.current.filter(Boolean) as HTMLElement[];
    if (!nodes.length || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .map((entry) => Number((entry.target as HTMLElement).dataset.briefIndex))
          .filter((index) => !Number.isNaN(index));
        // The topmost visible card is the one being read; taking the minimum
        // stops the counter jumping ahead when two cards share the viewport.
        if (visible.length) setPosition(Math.min(...visible) + 1);
      },
      // A band across the middle of the viewport: a card counts as "current"
      // only once it is genuinely the thing in front of the reader.
      { rootMargin: "-45% 0px -45% 0px" }
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [count]);

  const register = (index: number) => (node: HTMLElement | null) => {
    refs.current[index] = node;
  };

  return { position, register };
}
