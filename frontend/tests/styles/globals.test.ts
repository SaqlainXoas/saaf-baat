import { readFileSync } from "fs";
import { join } from "path";

const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");

/**
 * jsdom applies no stylesheet, so component tests cannot see any of this.
 * These are read against the source text instead - crude, but they guard rules
 * the product has an explicit position on, where a silent change would alter
 * how the brief reads rather than break a test.
 */
describe("globals.css contracts", () => {
  it("never snaps mandatorily", () => {
    // R-7: a reader skims a brief and skips what they already know. Twelve
    // mandatory full-screen stops would make it slower than a plain list.
    expect(css).toMatch(/scroll-snap-type:\s*y\s+proximity/);
    expect(css).not.toMatch(/scroll-snap-type:\s*[xy](\s+both)?\s+mandatory/);
  });

  it("turns snapping off under reduced motion", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(reduced).toMatch(/\.sb-deck\s*\{\s*scroll-snap-type:\s*none/);
  });

  it("defines every colour token in both themes", () => {
    const tokensIn = (block: string) =>
      new Set([...block.matchAll(/(--[a-z0-9-]+):/g)].map((m) => m[1]));
    const light = css.slice(css.indexOf(":root {"), css.indexOf('html[data-theme="dark"]'));
    const darkStart = css.indexOf('html[data-theme="dark"] {');
    const dark = css.slice(darkStart, css.indexOf("}", css.indexOf("--hover", darkStart)));

    const colourish = (token: string) =>
      /paper|surface|ink|hairline|outline|teal|amber|mint|status|summary|elev|focus|hover/.test(
        token,
      );
    const missing = [...tokensIn(light)].filter((t) => colourish(t) && !tokensIn(dark).has(t));
    expect(missing).toEqual([]);
  });

  it("keeps the lead card visually distinct from supporting cards", () => {
    // They differed only by four pixels of headline size before this pass,
    // which is not a hierarchy a reader perceives.
    expect(css).toMatch(/\.sb-story-card-lead\s*\{[^}]*box-shadow:\s*var\(--elev-2\)/);
  });

  it("does not leave rules for components that were deleted", () => {
    for (const gone of [
      ".sb-home-story",
      ".sb-brief-flow",
      ".sb-headline-homepage",
      ".sb-deck-progress",
    ]) {
      expect(css).not.toContain(`${gone} {`);
    }
  });
});
