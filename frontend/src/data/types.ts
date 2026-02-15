export interface EntityDTO {
  text: string;
  type: string;
  sources: number;
}

export interface SourceCountDTO {
  source: string;
  count: number;
}

export interface StoryCardData {
  story_id: string;
  created_at: string;
  headline: string;
  snippet: string;
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
