import { act, render, screen } from "@testing-library/react";
import { useBriefProgress } from "@/hooks/useBriefProgress";

it("uses a height-based band and retains visible cards between observer updates", () => {
  let callback: IntersectionObserverCallback;
  let options: IntersectionObserverInit | undefined;
  const original = window.IntersectionObserver;
  window.IntersectionObserver = jest.fn((cb, config) => {
    callback = cb;
    options = config;
    return { observe: jest.fn(), disconnect: jest.fn() };
  }) as unknown as typeof IntersectionObserver;
  function Brief() {
    const { position, register } = useBriefProgress(3);
    return <><output>{position}</output>{[0, 1, 2].map(i => <article key={i} data-brief-index={i} ref={register(i)} />)}</>;
  }
  const { container, unmount } = render(<Brief />);
  expect(options?.rootMargin).toBe(`-${Math.round(window.innerHeight * .35)}px 0px -${Math.round(window.innerHeight * .35)}px 0px`);
  const nodes = container.querySelectorAll("article");
  const change = (index: number, isIntersecting: boolean) => ({ target: nodes[index], isIntersecting } as unknown as IntersectionObserverEntry);
  act(() => callback([change(1, true)], {} as IntersectionObserver));
  expect(screen.getByRole("status")).toHaveTextContent("2");
  act(() => callback([change(2, true)], {} as IntersectionObserver));
  expect(screen.getByRole("status")).toHaveTextContent("2");
  act(() => callback([change(1, false)], {} as IntersectionObserver));
  expect(screen.getByRole("status")).toHaveTextContent("3");
  unmount();
  window.IntersectionObserver = original;
});
