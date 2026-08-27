"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  normaliseTheme,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemeName,
} from "@/utils/theme";

type ThemeContextValue = {
  theme: ThemeName;
  resolvedTheme: ResolvedTheme;
  setTheme: (nextTheme: ThemeName) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: "system",
  resolvedTheme: "light",
  setTheme: () => undefined,
});

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

// This provider wraps the whole app, so anything it throws takes the page down.
// localStorage is not always available - Safari private browsing throws on
// write, and a locked-down profile can throw on read - and losing a theme
// preference must never cost the reader their brief.
function readStoredTheme(): string | null {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredTheme(theme: ThemeName): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The theme still applies for this session; it just will not be remembered.
  }
}

export default function ThemeProvider({
  children,
  defaultTheme = "system",
}: {
  children: React.ReactNode;
  defaultTheme?: ThemeName;
}) {
  const [theme, setTheme] = useState<ThemeName>(defaultTheme);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  useEffect(() => {
    setTheme(normaliseTheme(readStoredTheme(), defaultTheme));
  }, [defaultTheme]);

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");

    const applyTheme = () => {
      const nextResolved = resolveTheme(theme, Boolean(media?.matches));
      setResolvedTheme(nextResolved);
      document.documentElement.setAttribute("data-theme", theme);
      document.documentElement.style.colorScheme = nextResolved;
    };

    applyTheme();
    media?.addEventListener?.("change", applyTheme);
    return () => media?.removeEventListener?.("change", applyTheme);
  }, [theme]);

  useEffect(() => {
    writeStoredTheme(theme);
  }, [theme]);

  const value = useMemo(
    () => ({
      theme,
      resolvedTheme,
      setTheme,
    }),
    [theme, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
