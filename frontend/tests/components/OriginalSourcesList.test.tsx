import { fireEvent, render, screen } from "@testing-library/react";
import OriginalSourcesList from "@/components/OriginalSourcesList";

const articles = [
  {
    id: "1",
    source: "dawn",
    headline: "Pakistan IMF talks underway",
    url: "https://www.dawn.com/news/test",
    publish_date: "2026-02-04T04:30:00Z",
  },
  {
    id: "2",
    source: "geo",
    headline: "Markets react positively",
    url: "https://www.geo.tv/latest/test",
  },
  {
    id: "3",
    source: "tribune",
    headline: "Analysts watch for signals",
    url: "https://tribune.com.pk/story/test",
  },
];

describe("OriginalSourcesList", () => {
  it("renders section heading", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.getByText("Original sources")).toBeDefined();
  });

  it("renders each article headline with capitalised source", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.getByText(/Dawn: Pakistan IMF talks/)).toBeDefined();
    expect(screen.getByText(/Geo: Markets react/)).toBeDefined();
    expect(screen.getByText(/Tribune: Analysts watch/)).toBeDefined();
  });

  it("renders a Read link for each article", () => {
    render(<OriginalSourcesList articles={articles} />);
    const reads = screen.getAllByText("Read");
    expect(reads).toHaveLength(3);
  });

  it("Read links have correct hrefs", () => {
    render(<OriginalSourcesList articles={articles} />);
    const reads = screen.getAllByText("Read");
    expect(reads[0].getAttribute("href")).toBe("https://www.dawn.com/news/test");
    expect(reads[1].getAttribute("href")).toBe("https://www.geo.tv/latest/test");
    expect(reads[2].getAttribute("href")).toBe("https://tribune.com.pk/story/test");
  });

  it("Read links open in new tab", () => {
    render(<OriginalSourcesList articles={articles} />);
    const reads = screen.getAllByText("Read");
    reads.forEach((link) => {
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    });
  });

  it("does not render View full coverage when there are 4 or fewer sources", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.queryByText("View full coverage →")).toBeNull();
  });

  it("renders source badge initials", () => {
    render(<OriginalSourcesList articles={articles} />);
    // Each badge span contains the first letter of the source
    const badges = screen.getAllByText("D"); // dawn
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it("handles empty articles list gracefully", () => {
    render(<OriginalSourcesList articles={[]} />);
    expect(screen.getByText("Original sources")).toBeDefined();
    expect(screen.queryByText("Read")).toBeNull();
  });

  it("shows View full coverage when there are more than 4 sources", () => {
    const many = [
      ...articles,
      { id: "4", source: "dawn", headline: "Fourth", url: "https://www.dawn.com/news/4" },
      { id: "5", source: "geo", headline: "Fifth", url: "https://www.geo.tv/latest/5" },
    ];
    render(<OriginalSourcesList articles={many as any} />);
    expect(screen.getByText("View full coverage →")).toBeDefined();
  });

  it("expands and collapses full coverage list", () => {
    const many = [
      ...articles,
      { id: "4", source: "dawn", headline: "Fourth", url: "https://www.dawn.com/news/4" },
      { id: "5", source: "geo", headline: "Fifth", url: "https://www.geo.tv/latest/5" },
    ];
    render(<OriginalSourcesList articles={many as any} />);

    expect(screen.queryByText(/Geo: Fifth/)).toBeNull();
    fireEvent.click(screen.getByText("View full coverage →"));
    expect(screen.getByText(/Geo: Fifth/)).toBeDefined();
    fireEvent.click(screen.getByText("Show less"));
    expect(screen.queryByText(/Geo: Fifth/)).toBeNull();
  });
});
