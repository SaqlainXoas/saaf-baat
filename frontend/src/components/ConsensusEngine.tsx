import type { StoryDetailData } from "@/data/types";
import { buildConsensusSummary } from "@/utils/storyPresentation";

export default function ConsensusEngine({ story }: { story: StoryDetailData }) {
  const summary = buildConsensusSummary(story);
  const isSingleSource = story.sources.length <= 1;
  const sectionLabel = isSingleSource ? "Reporting Summary" : "Consensus Summary";
  const agreedHeading = isSingleSource ? "What’s clear in current reporting" : "Where reporting lines up";
  const debatedHeading = "What to Watch";

  return (
    <section className="mt-10">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-lg" style={{ color: "var(--teal)" }}>
          ✦
        </span>
        <div>
          <h3 className="sb-kicker !text-[12px]" style={{ color: "var(--teal)" }}>
            {sectionLabel}
          </h3>
        </div>
      </div>

      <div className="sb-summary-stack grid grid-cols-1 md:grid-cols-2">
        <div className="sb-summary-shell sb-summary-panel-agreed">
          <h4 className="sb-summary-heading">{agreedHeading}</h4>
          <ul className="mt-4 space-y-3">
            {summary.agreed.map((item) => (
              <li key={item} className="sb-summary-detail-item">
                <span>•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="sb-summary-shell sb-summary-panel-debated">
          <h4 className="sb-summary-heading">{debatedHeading}</h4>
          <ul className="mt-4 space-y-3">
            {summary.debated.map((item) => (
              <li key={item} className="sb-summary-detail-item">
                <span>•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
