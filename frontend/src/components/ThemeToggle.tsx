"use client";

import { useTheme } from "@/components/ThemeProvider";
import { type ThemeName } from "@/utils/theme";

const OPTIONS: { value: ThemeName; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="sb-theme-toggle" role="group" aria-label="Theme">
      {OPTIONS.map((option) => {
        const active = option.value === theme;
        return (
          <button
            key={option.value}
            type="button"
            className="sb-focusable sb-theme-option"
            data-active={active ? "true" : "false"}
            onClick={() => setTheme(option.value)}
            aria-pressed={active}
            aria-label={`${option.label} theme`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
