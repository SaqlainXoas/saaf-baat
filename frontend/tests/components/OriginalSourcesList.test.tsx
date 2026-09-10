import { fireEvent, render, screen } from "@testing-library/react";
import OriginalSourcesList from "@/components/OriginalSourcesList";
import type { StoryArticleData } from "@/data/types";

const articles: StoryArticleData[] = [
  {
    id: "1",
    source: "dawn",
    headline: "Pakistan IMF talks underway",
    url: "https://www.dawn.com/news/test",
    publish_date: "2026-02-04T04:30:00Z",
    published_on: "2026-02-04",
    publish_date_status: "precise",
  },
  {
    id: "2",
    source: "geo",
    headline: "Markets react positively",
    url: "https://www.geo.tv/latest/test",
    published_on: "2026-02-04",
    publish_date_status: "date_only",
  },
  {
    id: "3",
    source: "tribune",
    headline: "Analysts watch for signals",
    url: "https://tribune.com.pk/story/test",
    publish_date_status: "missing",
  },
];

describe("OriginalSourcesList", () => {
  it("renders section heading", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.getByText("Original sources")).toBeDefined();
  });

  it("supports a separate contextual-report label and list id", () => {
    render(
      <OriginalSourcesList
        articles={articles}
        title="Related reporting used for analysis"
        description="These reports are context, not event corroboration."
        listId="analysis-sources-list"
      />,
    );
    expect(screen.getByText("Related reporting used for analysis")).toBeDefined();
    expect(screen.getByText(/not event corroboration/i)).toBeDefined();
    expect(document.getElementById("analysis-sources-list")).toBeDefined();
  });

  it("renders each article headline with capitalised source", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.getByText("Dawn")).toBeDefined();
    expect(screen.getByText(/Pakistan IMF talks/)).toBeDefined();
    expect(screen.getByText("Geo News")).toBeDefined();
    expect(screen.getByText(/Markets react/)).toBeDefined();
    expect(screen.getByText("The Express Tribune")).toBeDefined();
    expect(screen.getByText(/Analysts watch/)).toBeDefined();
  });

  it("shows source timestamps as concrete Pakistan time when the backend marks them precise", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.getByText(/Published (?:4 Feb|Feb 4), 9:30\s?(?:am|AM) PKT/i)).toBeDefined();
  });

  it("shows only the calendar day when the backend marks a source timestamp as date-only", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.getByText(/Published (?:4 Feb|Feb 4)(?!,)/i)).toBeDefined();
  });

  it("does not invent a timestamp for an article with no publisher date", () => {
    // I-6: the "suspicious" status is gone. Ingest drops undated items and
    // quarantines stale endpoints, so the publisher date is trusted when
    // present and simply absent when not.
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.queryByText("Date under review")).toBeNull();
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

  it("gives each Read link a descriptive accessible name", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.getByLabelText(/Read Dawn report: Pakistan IMF talks underway/i)).toBeDefined();
    expect(screen.getByLabelText(/Read Geo News report: Markets react positively/i)).toBeDefined();
  });

  it("does not render View all reports when there are 4 or fewer entries", () => {
    render(<OriginalSourcesList articles={articles} />);
    expect(screen.queryByText(/View all \d+ reports/)).toBeNull();
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
    expect(screen.getByText(/links are unavailable for this story/i)).toBeDefined();
    expect(screen.getByText(/not available for this story yet/i)).toBeDefined();
  });

  it("uses single-source copy when only one article link is available", () => {
    render(<OriginalSourcesList articles={[articles[0]]} />);
    expect(screen.getByText(/currently links to one original publisher report/i)).toBeDefined();
  });

  it("shows View all reports when there are more than 4 entries", () => {
    const many = [
      ...articles,
      { id: "4", source: "dawn", headline: "Fourth", url: "https://www.dawn.com/news/4" },
      { id: "5", source: "geo", headline: "Fifth", url: "https://www.geo.tv/latest/5" },
    ];
    render(<OriginalSourcesList articles={many as any} />);
    expect(screen.getByText("View all 5 reports →")).toBeDefined();
  });

  it("expands and collapses full coverage list", () => {
    const many = [
      ...articles,
      { id: "4", source: "dawn", headline: "Fourth", url: "https://www.dawn.com/news/4" },
      { id: "5", source: "geo", headline: "Fifth", url: "https://www.geo.tv/latest/5" },
    ];
    render(<OriginalSourcesList articles={many as any} />);

    expect(screen.queryByText(/Fifth/)).toBeNull();
    const toggle = screen.getByText("View all 5 reports →");
    expect(toggle.getAttribute("aria-controls")).toBe("original-sources-list");
    fireEvent.click(toggle);
    expect(screen.getByText(/Fifth/)).toBeDefined();
    fireEvent.click(screen.getByText("Show fewer reports"));
    expect(screen.queryByText(/Fifth/)).toBeNull();
  });
});

describe("analysis-aware source ordering", () => {
  const nine: StoryArticleData[] = Array.from({ length: 9 }, (_, index) => ({
    id: `pims-${index}`,
    source: index === 8 ? "brecorder" : ["dawn", "geo", "tribune", "ary", "nation", "app", "thenews", "dawn"][index],
    headline: `PIMS report ${index}`,
    url: `https://example.com/${index}`,
    publish_date_status: "missing",
  }));

  it("pulls a publisher quoted by the analysis into the un-expanded list", () => {
    // The analysis said "Brecorder reports..." while Brecorder sat behind
    // "View all 9 reports", so the reader could not reach the source it quoted.
    render(<OriginalSourcesList articles={nine} prioritiseSources={["brecorder"]} />);

    expect(screen.getByText("Showing 4 of 9 reports.")).toBeDefined();
    expect(screen.getByRole("link", { name: /Read Business Recorder report: PIMS report 8/i })).toBeDefined();
  });

  it("leaves the order alone when the analysis names nobody", () => {
    render(<OriginalSourcesList articles={nine} />);

    expect(screen.queryByRole("link", { name: /Read Business Recorder report/i })).toBeNull();
  });

  it("labels the link role so context reports are distinguishable", () => {
    render(
      <OriginalSourcesList
        articles={[nine[0]]}
        title="Related reporting used for analysis"
        linkRole="context report"
      />,
    );

    expect(screen.getByRole("link", { name: /Read Dawn context report/i })).toBeDefined();
  });
});
