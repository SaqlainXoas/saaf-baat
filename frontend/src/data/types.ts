export interface EntityDTO {
  text: string;
  type: string;
  sources: number;
}

export interface SourceCountDTO {
  source: string;
  count: number;
}

export interface StoryMetadata {
  why_it_matters?: string;
  what_to_watch?: string;
  editorial_priority?: number;
  [key: string]: unknown;
}

export interface AnalyzedFeedRow {
  cluster_id: string;
  created_at: string;
  headline: string;
  summary: string | null;
  category: string;
  impact_labels: string[] | null;
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
  sources: SourceCountDTO[];
  metadata?: StoryMetadata;
}

export interface StoryArticleData {
  id: string;
  source: string;
  headline: string;
  url: string;
  publish_date?: string | null;
  published_on?: string | null;
  publish_date_status?: "precise" | "date_only" | "missing";
}

export interface StoryDetailData extends StoryCardData {
  analysis: string | null;
  question: string | null;
  articles: StoryArticleData[];
  analysis_sources: StoryArticleData[];
}

export interface FeedResponseData {
  generated_at?: string | null;
  is_fresh: boolean;
  stories: AnalyzedFeedRow[];
}
