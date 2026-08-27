import { act, render } from "@testing-library/react";
import ThemeProvider from "@/components/ThemeProvider";
import { THEME_STORAGE_KEY } from "@/utils/theme";

function setPrefersDark(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    setPrefersDark(false);
  });

  it("stamps the chosen theme on the document element", () => {
    render(
      <ThemeProvider defaultTheme="dark">
        <p>brief</p>
      </ThemeProvider>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("prefers a stored choice over the default", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    render(
      <ThemeProvider defaultTheme="dark">
        <p>brief</p>
      </ThemeProvider>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("ignores a stored value that is not a theme", () => {
    // localStorage is user-writable; an unknown value must not reach the DOM.
    window.localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    render(
      <ThemeProvider defaultTheme="light">
        <p>brief</p>
      </ThemeProvider>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("renders its children", () => {
    const { getByText } = render(
      <ThemeProvider defaultTheme="system">
        <p>brief</p>
      </ThemeProvider>,
    );
    expect(getByText("brief")).toBeDefined();
  });

  it("survives localStorage throwing, as it does in private mode", () => {
    const getItem = jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(() =>
      act(() => {
        render(
          <ThemeProvider defaultTheme="light">
            <p>brief</p>
          </ThemeProvider>,
        );
      }),
    ).not.toThrow();
    getItem.mockRestore();
  });
});
