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
    const stored = normaliseTheme(window.localStorage.getItem(THEME_STORAGE_KEY), defaultTheme);
    setTheme(stored);
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
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
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
