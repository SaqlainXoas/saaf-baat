"use client";

import type { MouseEvent } from "react";

type SkipLinkProps = {
  label: string;
  selector: string;
};

export default function SkipLink({ label, selector }: SkipLinkProps) {
  function onClick(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    const candidates = Array.from(document.querySelectorAll<HTMLElement>(selector));
    const target = candidates.find((element) => element.getClientRects().length > 0) || candidates[0];
    if (!target) return;

    if (!target.hasAttribute("tabindex")) {
      target.setAttribute("tabindex", "-1");
    }

    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  return (
    <a
      href="#"
      onClick={onClick}
      className="sb-focusable fixed left-3 top-3 z-50 -translate-y-[calc(100%+0.75rem)] rounded-lg px-3 py-2 text-xs font-bold opacity-0 transition-all duration-150 focus:translate-y-0 focus:opacity-100"
      style={{ background: "var(--surface)", color: "var(--ink)", border: "1px solid var(--hairline)" }}
    >
      {label}
    </a>
  );
}
