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

    let observer: IntersectionObserver;
    const visible = new Set<number>();
    const observe = () => {
      observer?.disconnect();
      visible.clear();
      // IntersectionObserver percentage margins resolve against width, which
      // can erase the entire band on a wide screen. Use viewport-height pixels.
      const inset = Math.round(window.innerHeight * 0.35);
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            const index = Number((entry.target as HTMLElement).dataset.briefIndex);
            if (Number.isNaN(index)) continue;
            if (entry.isIntersecting) visible.add(index);
            else visible.delete(index);
          }
          if (visible.size) setPosition(Math.min(...visible) + 1);
        },
        { rootMargin: `-${inset}px 0px -${inset}px 0px` },
      );
      nodes.forEach((node) => observer.observe(node));
    };
    observe();
    window.addEventListener("resize", observe);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", observe);
    };
  }, [count]);

  const register = (index: number) => (node: HTMLElement | null) => {
    refs.current[index] = node;
  };

  return { position, register };
}
