import { render, screen } from "@testing-library/react";
import BrandHeader from "@/components/BrandHeader";
import ThemeProvider from "@/components/ThemeProvider";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(""),
}));

describe("BrandHeader", () => {
  function renderHeader() {
    return render(
      <ThemeProvider defaultTheme="system">
        <BrandHeader />
      </ThemeProvider>,
    );
  }

  it("renders brand name", () => {
    renderHeader();
    expect(screen.getByText("Saaf Baat")).toBeDefined();
  });

  it("renders inline logo", () => {
    renderHeader();
    expect(screen.getByLabelText("Saaf Baat logo")).toBeDefined();
  });

  it("renders Focus button", () => {
    renderHeader();
    expect(screen.getByText("Focus")).toBeDefined();
  });
});
