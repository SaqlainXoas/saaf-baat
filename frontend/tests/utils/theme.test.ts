import { isThemeName, normaliseTheme, resolveTheme, THEME_OPTIONS } from "@/utils/theme";

describe("theme", () => {
  it("recognises exactly the three options", () => {
    THEME_OPTIONS.forEach((option) => expect(isThemeName(option)).toBe(true));
    expect(isThemeName("sepia")).toBe(false);
    expect(isThemeName(null)).toBe(false);
    expect(isThemeName(undefined)).toBe(false);
    expect(isThemeName("")).toBe(false);
  });

  it("falls back rather than passing an unknown theme through to the DOM", () => {
    expect(normaliseTheme("dark")).toBe("dark");
    expect(normaliseTheme("sepia")).toBe("system");
    expect(normaliseTheme(undefined, "light")).toBe("light");
  });

  it("resolves system against the media query and ignores it otherwise", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });
});
