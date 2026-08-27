import { fireEvent, render, screen } from "@testing-library/react";
import Button from "@/components/primitives/Button";

describe("Button", () => {
  it("defaults to type=button so it cannot submit a surrounding form", () => {
    render(<Button>Apply</Button>);
    expect(screen.getByRole("button", { name: "Apply" }).getAttribute("type")).toBe("button");
  });

  it("lets a caller opt into submit", () => {
    render(<Button type="submit">Send</Button>);
    expect(screen.getByRole("button", { name: "Send" }).getAttribute("type")).toBe("submit");
  });

  it("fires onClick", () => {
    const onClick = jest.fn();
    render(<Button onClick={onClick}>Apply</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("forwards disabled and stays inert", () => {
    const onClick = jest.fn();
    render(
      <Button disabled onClick={onClick}>
        Apply
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Apply" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("keeps the focus ring on every variant", () => {
    for (const variant of ["primary", "ghost", "pill"] as const) {
      const { unmount } = render(<Button variant={variant}>Apply</Button>);
      expect(screen.getByRole("button", { name: "Apply" }).className).toContain("sb-focusable");
      unmount();
    }
  });

  it("keeps caller classes alongside its own", () => {
    render(<Button className="w-full">Apply</Button>);
    expect(screen.getByRole("button", { name: "Apply" }).className).toContain("w-full");
  });
});
