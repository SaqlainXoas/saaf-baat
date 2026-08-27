import type { ReactNode } from "react";

type CardVariant = "elevated" | "flat" | "inset";

export default function Card({
  children,
  className = "",
  variant = "elevated",
  interactive = false,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  variant?: CardVariant;
  interactive?: boolean;
  /** Set false when the caller's own class owns the padding (story cards do,
   *  because lead and supporting are padded differently). */
  padded?: boolean;
}) {
  const base =
    variant === "flat"
      ? "sb-surface"
      : variant === "inset"
        ? "sb-surface sb-surface-inset"
        : "sb-card";

  return (
    <div
      className={`w-full ${padded ? "p-4" : ""} ${base} ${interactive ? "sb-card-interactive" : ""} ${className}`}
    >
      {children}
    </div>
  );
}
