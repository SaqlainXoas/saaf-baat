import "@testing-library/jest-dom";

// jsdom implements neither of these, and both are things the brief genuinely
// does: the skip link scrolls its target into view, and ThemeToggle reads the
// colour-scheme media query. Without the stubs a component crashes in the test
// environment for reasons that have nothing to do with the component.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
