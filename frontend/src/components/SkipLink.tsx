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
      className="sb-focusable absolute left-3 top-3 z-40 rounded-lg px-3 py-2 text-xs font-bold"
      style={{ background: "var(--surface)", color: "var(--ink)", border: "1px solid var(--hairline)" }}
    >
      {label}
    </a>
  );
}
