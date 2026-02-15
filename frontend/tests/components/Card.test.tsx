import { render, screen } from "@testing-library/react";
import Card from "@/components/primitives/Card";

describe("Card", () => {
  it("renders children", () => {
    render(
      <Card>
        <span>Hello</span>
      </Card>,
    );
    expect(screen.getByText("Hello")).toBeDefined();
  });

  it("applies extra className", () => {
    const { container } = render(
      <Card className="extra-cls">
        <span>Content</span>
      </Card>,
    );
    expect((container.firstChild as HTMLElement).classList.contains("extra-cls")).toBe(true);
  });

  it("uses the elevated card styles by default", () => {
    const { container } = render(
      <Card>
        <span>Styled</span>
      </Card>,
    );
    const card = container.firstChild as HTMLElement;
    expect(card.classList.contains("sb-card")).toBe(true);
  });
});
