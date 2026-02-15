"use client";

import { useEffect, useMemo, useRef } from "react";

function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
  if (!container) return [];
  const selectors = [
    "a[href]",
    "button:not([disabled])",
    "textarea:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
  ];
  return Array.from(container.querySelectorAll<HTMLElement>(selectors.join(","))).filter(
    (el) => !el.hasAttribute("disabled"),
  );
}

export default function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
  widthClassName = "sm:max-w-md",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  widthClassName?: string;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const lastActive = useMemo(() => (typeof document !== "undefined" ? document.activeElement : null), []);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const focusables = getFocusableElements(panel);
    (focusables[0] || panel)?.focus?.();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab") return;
      const f = getFocusableElements(panel);
      if (f.length === 0) return;
      const first = f[0];
      const last = f[f.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open) return;
    const el = lastActive as HTMLElement | null;
    el?.focus?.();
  }, [open, lastActive]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0"
        style={{ background: "rgba(11, 18, 32, 0.38)" }}
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="absolute inset-x-0 bottom-0 sm:inset-0 sm:flex sm:items-center sm:justify-center p-3 sm:p-6">
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-label={title}
          tabIndex={-1}
          className={`w-full ${widthClassName} sb-focusable`}
          style={{
            background: "var(--surface)",
            border: "1px solid var(--hairline)",
            borderRadius: "var(--radius-2xl)",
            boxShadow: "var(--elev-2)",
          }}
        >
          <div className="px-4 py-3 flex items-center justify-between">
            <h2 className="text-sm font-bold tracking-tight" style={{ color: "var(--ink)" }}>
              {title}
            </h2>
            <button
              onClick={onClose}
              className="sb-focusable text-sm font-medium px-2 py-1 rounded-lg"
              style={{ color: "var(--ink-muted)" }}
            >
              Close
            </button>
          </div>

          <div className="sb-divider" />

          <div className="px-4 py-4">{children}</div>

          {footer ? (
            <>
              <div className="sb-divider" />
              <div className="px-4 py-3">{footer}</div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

