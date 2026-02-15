export const THEME_STORAGE_KEY = "saaf-baat-theme";

export const THEME_OPTIONS = ["system", "light", "dark"] as const;

export type ThemeName = (typeof THEME_OPTIONS)[number];
export type ResolvedTheme = "light" | "dark";

export function isThemeName(value: string | null | undefined): value is ThemeName {
  if (!value) return false;
  return (THEME_OPTIONS as readonly string[]).includes(value);
}

export function normaliseTheme(
  value: string | null | undefined,
  fallback: ThemeName = "system",
): ThemeName {
  return isThemeName(value) ? value : fallback;
}

export function resolveTheme(theme: ThemeName, prefersDark: boolean): ResolvedTheme {
  if (theme === "dark") return "dark";
  if (theme === "light") return "light";
  return prefersDark ? "dark" : "light";
}
