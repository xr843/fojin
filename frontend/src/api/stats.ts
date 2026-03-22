import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  try {
    const raw = localStorage.getItem("fojin-auth");
    if (raw) {
      const { state } = JSON.parse(raw);
      if (state?.token) {
        config.headers.Authorization = `Bearer ${state.token}`;
      }
    }
  } catch {
    // ignore
  }
  return config;
});

export interface StatsSummary {
  total_texts: number;
  total_sources: number;
  total_languages: number;
  total_kg_entities: number;
  total_kg_relations: number;
  total_dict_entries: number;
}

export interface DynastyDistribution {
  dynasty: string;
  count: number;
  year_start: number | null;
  year_end: number | null;
}

export interface LanguageDistribution {
  language: string;
  count: number;
}

export interface CategoryDistribution {
  category: string;
  count: number;
}

export interface SourceCoverage {
  source_name: string;
  full_content: number;
  metadata_only: number;
}

export interface TopTranslator {
  name: string;
  dynasty: string | null;
  count: number;
}

export interface StatsOverview {
  summary: StatsSummary;
  dynasty_distribution: DynastyDistribution[];
  language_distribution: LanguageDistribution[];
  category_distribution: CategoryDistribution[];
  source_coverage: SourceCoverage[];
  top_translators: TopTranslator[];
}

export interface TimelineItem {
  id: number;
  name_zh: string;
  name_en: string | null;
  dynasty: string | null;
  year_start: number | null;
  year_end: number | null;
  category?: string | null;
  translator?: string | null;
  entity_type?: string | null;
}

export interface TimelineResponse {
  items: TimelineItem[];
  total: number;
}

export type TimelineDimension = "texts" | "figures" | "schools";

export async function getStatsOverview(): Promise<StatsOverview> {
  const { data } = await api.get<StatsOverview>("/stats/overview");
  return data;
}

export async function getStatsTimeline(params: {
  dimension: TimelineDimension;
  category?: string;
  language?: string;
  source_id?: string;
  page?: number;
  page_size?: number;
}): Promise<TimelineResponse> {
  const { data } = await api.get<TimelineResponse>("/stats/timeline", { params });
  return data;
}
