import type { ReactNode } from "react";

type CardVariant = "elevated" | "flat" | "inset";

export default function Card({
  children,
  className = "",
  variant = "elevated",
  interactive = false,
}: {
  children: ReactNode;
  className?: string;
  variant?: CardVariant;
  interactive?: boolean;
}) {
  const base =
    variant === "flat"
      ? "sb-surface"
      : variant === "inset"
        ? "sb-surface"
        : "sb-card";

  return (
    <div
      className={`w-full p-4 ${base} ${interactive ? "sb-card-interactive" : ""} ${className}`}
      style={
        variant === "inset"
          ? {
              background: "var(--surface-2)",
              border: "1px solid var(--hairline)",
              boxShadow: "none",
            }
          : undefined
      }
    >
      {children}
    </div>
  );
}
