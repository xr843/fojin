import { api } from "./client";

export interface SourceUpdateItem {
  id: number;
  source_id: number;
  source_code: string;
  source_name_zh: string;
  update_type: string;
  count: number;
  summary: string;
  detected_at: string;
}

export interface AcademicFeedItem {
  id: number;
  feed_source: string;
  title: string;
  url: string;
  summary: string | null;
  author: string | null;
  category: string | null;
  language: string | null;
  published_at: string | null;
}

export interface FeedSummary {
  recent_source_updates: SourceUpdateItem[];
  recent_academic: AcademicFeedItem[];
  stats: {
    source_updates_30d: number;
    academic_feeds_30d: number;
    active_sources: number;
  };
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface PlatformActivity {
  period_days: number;
  reading: {
    total_reads: number;
    unique_texts_read: number;
    top_texts: {
      text_id: number;
      title_zh: string;
      read_count: number;
    }[];
  };
  chat: {
    total_messages: number;
    total_sessions: number;
    positive_feedback: number;
  };
  users: {
    new_users: number;
    active_users: number;
  };
  content: {
    new_texts: number;
    total_texts: number;
    total_sources: number;
  };
}

export async function getFeedSummary(): Promise<FeedSummary> {
  const { data } = await api.get<FeedSummary>("/feed/summary");
  return data;
}

export async function getSourceUpdates(params: {
  source_id?: number;
  update_type?: string;
  days?: number;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<SourceUpdateItem>> {
  const { data } = await api.get<PaginatedResponse<SourceUpdateItem>>(
    "/feed/source-updates",
    { params },
  );
  return data;
}

export async function getAcademicFeeds(params: {
  feed_source?: string;
  category?: string;
  days?: number;
  page?: number;
  page_size?: number;
}): Promise<PaginatedResponse<AcademicFeedItem>> {
  const { data } = await api.get<PaginatedResponse<AcademicFeedItem>>(
    "/feed/academic",
    { params },
  );
  return data;
}

export async function getPlatformActivity(params: {
  days?: number;
}): Promise<PlatformActivity> {
  const { data } = await api.get<PlatformActivity>(
    "/stats/platform-activity",
    { params },
  );
  return data;
}
