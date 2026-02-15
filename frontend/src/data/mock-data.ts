import type { StoryCardData, StoryDetailData, StoryArticleData } from "./types";

export const FEED: StoryCardData[] = [
  {
    story_id: "b6b6df46-4a5f-4b51-8d88-5b6d0f5f2c01",
    created_at: "2026-02-04T06:05:00Z",
    headline: "IMF Tranche Released: Rupee Strengthens",
    snippet:
      "State Bank confirms $1.2bn receipt. Market reacts positively, rupee gains as traders welcome the signal on the next tranche disbursement.",
    category: "economy",
    impact_labels: ["💳 WALLET", "🏛️ GOVERNANCE"],
    confirmed_facts: [
      { text: "IMF", type: "ORG", sources: 3 },
      { text: "Pakistan", type: "GPE", sources: 3 },
    ],
    debated_claims: [{ text: "fuel cut", type: "MISC", sources: 2 }],
    sources: [
      { source: "dawn", count: 1 },
      { source: "geo", count: 1 },
      { source: "tribune", count: 1 },
    ],
  },
  {
    story_id: "0ac8a03e-ea08-48e7-8f8e-bc33b2cbb4ac",
    created_at: "2026-02-04T06:20:00Z",
    headline: "Karachi Commuters Face Delays as Roadworks Trigger Bottlenecks",
    snippet:
      "Traffic congestion built up across key arteries after overnight construction reduced lanes on the Lyari Expressway.",
    category: "city",
    impact_labels: ["🚦 COMMUTE", "🏢 WORK"],
    confirmed_facts: [
      { text: "Karachi", type: "GPE", sources: 2 },
      { text: "diversion advisory", type: "MISC", sources: 2 },
    ],
    debated_claims: [
      { text: "completion by weekend", type: "DATE", sources: 1 },
    ],
    sources: [
      { source: "tribune", count: 1 },
      { source: "geo", count: 1 },
    ],
  },
  {
    story_id: "741d5c39-420b-4bb4-b1d5-2798d60f10c2",
    created_at: "2026-02-04T06:45:00Z",
    headline: "Security Operation in Balochistan; Officials Confirm Arrests",
    snippet:
      "A targeted operation led to multiple arrests and the recovery of arms caches. Independent verification is still emerging from the area.",
    category: "security",
    impact_labels: ["🛡️ SAFETY"],
    confirmed_facts: [{ text: "Balochistan", type: "GPE", sources: 2 }],
    debated_claims: [
      { text: "militant network", type: "MISC", sources: 1 },
    ],
    sources: [
      { source: "dawn", count: 1 },
      { source: "geo", count: 1 },
    ],
  },
  {
    story_id: "a1c2d3e4-5678-9012-abcd-ef1234567890",
    created_at: "2026-02-04T07:00:00Z",
    headline: "Punjab Schools Reopen After Week-Long Closure Order Lifted",
    snippet:
      "Thousands of students returned to classrooms as provincial authorities formally ended the emergency shutdown across the province.",
    category: "education",
    impact_labels: ["🏢 WORK"],
    confirmed_facts: [
      { text: "Punjab", type: "GPE", sources: 2 },
      { text: "schools", type: "MISC", sources: 2 },
    ],
    debated_claims: [
      { text: "exam schedule change", type: "MISC", sources: 1 },
    ],
    sources: [
      { source: "dawn", count: 1 },
      { source: "tribune", count: 1 },
    ],
  },
  {
    story_id: "f5e4d3c2-1098-7654-fedc-ba9876543210",
    created_at: "2026-02-04T07:30:00Z",
    headline: "Gas Prices Stay Flat This Week, Utility Companies Confirm",
    snippet:
      "Despite seasonal demand increases, gas providers confirmed no price revision for the current billing cycle across all provinces.",
    category: "economy",
    impact_labels: ["⚡ UTILITIES", "💳 WALLET"],
    confirmed_facts: [{ text: "gas prices", type: "MISC", sources: 3 }],
    debated_claims: [
      { text: "next month revision", type: "DATE", sources: 1 },
    ],
    sources: [
      { source: "dawn", count: 1 },
      { source: "geo", count: 1 },
      { source: "tribune", count: 1 },
    ],
  },
];

// Pre-built detail objects keyed by story_id for mock lookup
const DETAIL_ARTICLES: Record<string, StoryArticleData[]> = {
  "b6b6df46-4a5f-4b51-8d88-5b6d0f5f2c01": [
    {
      id: "bd6dbf0b-3cf6-4f7f-8f67-25708bce1a11",
      source: "dawn",
      headline: "IMF Tranche Released: Rupee Strengthens",
      url: "https://www.dawn.com/news/1234567",
      publish_date: "2026-02-04T04:30:00Z",
    },
    {
      id: "6dbfe2f2-2b78-4f7f-86e6-15e2b9a6c4a6",
      source: "geo",
      headline: "SBP reserves increase by $1.2bn after IMF receipt",
      url: "https://www.geo.tv/latest/1234567",
      publish_date: "2026-02-04T05:10:00Z",
    },
    {
      id: "46c7a535-0b5c-4b0e-b9b0-7cdd97c2c2a9",
      source: "tribune",
      headline: "Relief hopes hinge on IMF signals, analysts say",
      url: "https://tribune.com.pk/story/1234567",
      publish_date: "2026-02-04T05:25:00Z",
    },
  ],
  "0ac8a03e-ea08-48e7-8f8e-bc33b2cbb4ac": [
    {
      id: "aa111111-1111-1111-1111-111111111111",
      source: "tribune",
      headline: "Lyari Expressway roadworks cause morning chaos",
      url: "https://tribune.com.pk/story/7654321",
      publish_date: "2026-02-04T05:00:00Z",
    },
    {
      id: "bb222222-2222-2222-2222-222222222222",
      source: "geo",
      headline: "Karachi traffic advisory issued for commuters",
      url: "https://www.geo.tv/latest/7654321",
      publish_date: "2026-02-04T05:45:00Z",
    },
  ],
  "741d5c39-420b-4bb4-b1d5-2798d60f10c2": [
    {
      id: "cc333333-3333-3333-3333-333333333333",
      source: "dawn",
      headline: "Balochistan operation: arrests and arms recovery reported",
      url: "https://www.dawn.com/news/7654322",
      publish_date: "2026-02-04T04:10:00Z",
    },
    {
      id: "dd444444-4444-4444-4444-444444444444",
      source: "geo",
      headline: "Security forces conduct raids in Balochistan",
      url: "https://www.geo.tv/latest/7654322",
      publish_date: "2026-02-04T04:55:00Z",
    },
  ],
};

export function getMockDetail(storyId: string): StoryDetailData | null {
  const card = FEED.find((s) => s.story_id === storyId);
  if (!card) return null;
  return {
    ...card,
    articles: DETAIL_ARTICLES[storyId] || [],
  };
}
