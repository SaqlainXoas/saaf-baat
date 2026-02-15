const STYLES = {
  agreed: {
    background: "var(--mint-bg)",
    border: "1px solid rgba(82, 183, 163, 0.25)",
  },
  debated: {
    background: "var(--amber-bg)",
    border: "1px solid rgba(240, 195, 122, 0.4)",
  },
};

export default function Chip({
  label,
  variant = "agreed",
  size = "sm",
}: {
  label: string;
  variant?: "agreed" | "debated";
  size?: "sm" | "md";
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${
        size === "md" ? "px-3 py-1 text-xs" : "px-2.5 py-1 text-xs"
      }`}
      style={STYLES[variant]}
    >
      {label}
    </span>
  );
}
