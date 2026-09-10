import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ThemeProvider from "@/components/ThemeProvider";
import ThemeToggle from "@/components/ThemeToggle";
import { THEME_STORAGE_KEY } from "@/utils/theme";

function mockMatchMedia(prefersDark = false) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: jest.fn().mockImplementation(() => ({
      matches: prefersDark,
      media: "(prefers-color-scheme: dark)",
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      addListener: jest.fn(),
      removeListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

describe("ThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    mockMatchMedia(false);
  });

  it("loads stored theme from localStorage", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");

    render(
      <ThemeProvider defaultTheme="system">
        <ThemeToggle />
      </ThemeProvider>,
    );

    await waitFor(() => {
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    });
  });

  it("updates html theme attribute when selecting a new theme", () => {
    render(
      <ThemeProvider defaultTheme="system">
        <ThemeToggle />
      </ThemeProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });
});

 it("toggles from the resolved system appearance with one icon-only button", () => {
   window.localStorage.clear();
   mockMatchMedia(true);
   render(<ThemeProvider defaultTheme="system"><ThemeToggle /></ThemeProvider>);
   const button = screen.getByRole("button", { name: "Switch to light mode" });
   expect(screen.getAllByRole("button")).toHaveLength(1);
   expect(button.textContent).toBe("");
   fireEvent.click(button);
   expect(document.documentElement.getAttribute("data-theme")).toBe("light");
 });
