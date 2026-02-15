type LogoVariant = "brand" | "mono";

export default function Logo({
  size = 24,
  variant = "brand",
  className = "",
  decorative = false,
}: {
  size?: number;
  variant?: LogoVariant;
  className?: string;
  decorative?: boolean;
}) {
  const fill = variant === "brand" ? "var(--teal)" : "currentColor";
  const ariaProps = decorative
    ? { "aria-hidden": true as const }
    : { role: "img" as const, "aria-label": "Saaf Baat logo" };

  return (
    <svg
      viewBox="0 0 128 128"
      width={size}
      height={size}
      className={className}
      {...ariaProps}
    >
      <g fill={fill}>
        <circle cx="48" cy="80" r="40" />
        <rect x="78" y="22" width="12" height="34" rx="6" transform="rotate(-25 84 39)" />
        <rect x="94" y="30" width="12" height="30" rx="6" transform="rotate(5 100 45)" />
        <rect x="108" y="42" width="12" height="26" rx="6" transform="rotate(25 114 55)" />
        <circle cx="112" cy="24" r="6" />
      </g>
    </svg>
  );
}
