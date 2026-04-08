import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import Sheet from "@/components/primitives/Sheet";

function SheetHarness() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open sheet
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Focus">
        <button type="button">First action</button>
      </Sheet>
    </>
  );
}

describe("Sheet", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("returns focus to the trigger after closing", () => {
    jest.useFakeTimers();
    render(<SheetHarness />);

    const trigger = screen.getByRole("button", { name: "Open sheet" });
    trigger.focus();
    fireEvent.click(trigger);

    const close = screen.getByRole("button", { name: "Close" });
    fireEvent.click(close);

    act(() => {
      jest.advanceTimersByTime(200);
    });

    expect(document.activeElement).toBe(trigger);
  });
});
