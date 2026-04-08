import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

type ButtonVariant = "primary" | "ghost" | "pill";
type ButtonSize = "sm" | "md";

export default function Button({
  children,
  variant = "ghost",
  size = "md",
  className = "",
  type,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
}) {
  const sizeClass =
    size === "sm" ? "text-sm px-3 py-1.5 rounded-xl" : "text-sm px-4 py-2 rounded-xl";

  const variantStyle: CSSProperties =
    variant === "primary"
      ? { background: "var(--teal)", color: "white", border: "1px solid transparent" }
      : variant === "pill"
        ? {
            background: "var(--surface)",
            color: "var(--ink)",
            border: "1px solid var(--hairline)",
            borderRadius: "999px",
          }
        : {
            background: "var(--surface)",
            color: "var(--ink-muted)",
            border: "1px solid var(--hairline)",
          };

  return (
    <button
      {...props}
      type={type ?? "button"}
      className={`sb-focusable inline-flex items-center justify-center gap-2 font-medium transition-colors ${sizeClass} ${className}`}
      style={variantStyle}
    >
      {children}
    </button>
  );
}
