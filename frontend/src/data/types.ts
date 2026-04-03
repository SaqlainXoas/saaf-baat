export interface EntityDTO {
  text: string;
  type: string;
  sources: number;
}

export interface SourceCountDTO {
  source: string;
  count: number;
}

export interface AnalyzedFeedRow {
  cluster_id: string;
  created_at: string;
  headline: string;
  summary: string | null;
  category: string;
  impact_labels: string[] | null;
  confirmed_facts: unknown[] | null;
  debated_claims: unknown[] | null;
  source_attribution: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
}

export interface StoryCardData {
  story_id: string;
  created_at: string;
  headline: string;
  snippet: string; // mapped from analyzed_feed.summary
  category: string;
  impact_labels: string[];
  confirmed_facts: EntityDTO[];
  debated_claims: EntityDTO[];
  sources: SourceCountDTO[];
  metadata?: Record<string, unknown>;
}

export interface StoryArticleData {
  id: string;
  source: string;
  headline: string;
  url: string;
  publish_date?: string | null;
}

export interface StoryDetailData extends StoryCardData {
  articles: StoryArticleData[];
}
