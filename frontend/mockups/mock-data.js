const FEED = [
  {
    story_id: "b6b6df46-4a5f-4b51-8d88-5b6d0f5f2c01",
    created_at: "2026-02-04T06:05:00Z",
    headline: "IMF review: Pakistan pushes for relief as rupee stays under pressure",
    snippet:
      "Pakistan met IMF officials in Washington as inflation and currency volatility remained central concerns. Markets reacted cautiously, with traders watching for signals on the next tranche.",
    category: "economy",
    impact_labels: ["💳 WALLET", "🏛️ GOVERNANCE"],
    confirmed_facts: [
      { text: "Pakistan", type: "GPE", sources: 3 },
      { text: "IMF", type: "ORG", sources: 3 },
    ],
    debated_claims: [
      { text: "Next tranche", type: "MISC", sources: 2 },
      { text: "Fuel price cut", type: "MISC", sources: 1 },
    ],
    sources: [
      { source: "dawn", count: 1 },
      { source: "geo", count: 1 },
      { source: "tribune", count: 1 },
    ],
  },
  {
    story_id: "0ac8a03e-ea08-48e7-8f8e-bc33b2cbb4ac",
    created_at: "2026-02-04T06:20:00Z",
    headline: "Karachi commuters face delays as roadworks trigger morning bottlenecks",
    snippet:
      "Traffic congestion built up across key arteries after overnight construction reduced lanes. Authorities issued a diversion advisory and asked commuters to stagger departure times.",
    category: "city",
    impact_labels: ["🚦 COMMUTE", "🏢 WORK"],
    confirmed_facts: [
      { text: "Karachi", type: "GPE", sources: 2 },
      { text: "diversion", type: "MISC", sources: 2 },
    ],
    debated_claims: [{ text: "completion by weekend", type: "DATE", sources: 1 }],
    sources: [
      { source: "tribune", count: 1 },
      { source: "geo", count: 1 },
    ],
  },
  {
    story_id: "741d5c39-420b-4bb4-b1d5-2798d60f10c2",
    created_at: "2026-02-04T06:45:00Z",
    headline: "Security operation reported in Balochistan; officials confirm arrests",
    snippet:
      "Officials said a targeted operation led to multiple arrests and the recovery of arms. Details remain limited, with independent verification still emerging from the area.",
    category: "security",
    impact_labels: ["🛡️ SAFETY"],
    confirmed_facts: [{ text: "Balochistan", type: "GPE", sources: 2 }],
    debated_claims: [
      { text: "militant network", type: "MISC", sources: 1 },
      { text: "casualties", type: "MISC", sources: 1 },
    ],
    sources: [
      { source: "dawn", count: 1 },
      { source: "geo", count: 1 },
    ],
  },
];

const STORY_DETAIL = {
  ...FEED[0],
  articles: [
    {
      id: "bd6dbf0b-3cf6-4f7f-8f67-25708bce1a11",
      source: "dawn",
      headline: "Pakistan, IMF hold talks in Washington as rupee steadies",
      url: "https://www.dawn.com/news/example",
      publish_date: "2026-02-04T04:30:00Z",
    },
    {
      id: "6dbfe2f2-2b78-4f7f-86e6-15e2b9a6c4a6",
      source: "geo",
      headline: "IMF review underway; markets watch next steps",
      url: "https://www.geo.tv/latest/example",
      publish_date: "2026-02-04T05:10:00Z",
    },
    {
      id: "46c7a535-0b5c-4b0e-b9b0-7cdd97c2c2a9",
      source: "tribune",
      headline: "Relief hopes hinge on IMF signals, analysts say",
      url: "https://tribune.com.pk/story/example",
      publish_date: "2026-02-04T05:25:00Z",
    },
  ],
};
