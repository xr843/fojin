import axios from "axios";
import { useAuthStore } from "../stores/authStore";
import i18n from "../i18n";
import type {
  TextId,
  SourceId,
  ChatSessionId,
  UserId,
  DictEntryId,
  KGEntityId,
  AnnotationId,
  BookmarkId,
  NotificationId,
  IIIFManifestId,
} from "../types/branded";

export const api = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

// Attach JWT token from localStorage (zustand persist)
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
    // ignore parse errors
  }
  return config;
});

// Auto-logout on 401 responses (except auth endpoints)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      !error.config?.url?.startsWith("/auth/")
    ) {
      useAuthStore.getState().logout();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

export interface RelatedTranslation {
  id: TextId;
  title: string;
  lang: string;
  relation_type: string;
}

export interface SearchHit {
  id: TextId;
  taisho_id: string | null;
  cbeta_id: string;
  title_zh: string;
  translator: string | null;
  dynasty: string | null;
  category: string | null;
  cbeta_url: string | null;
  has_content: boolean;
  source_code: string | null;
  lang: string | null;
  score: number | null;
  highlight: Record<string, string[]> | null;
  related_translations: RelatedTranslation[];
}

export interface SearchResponse {
  total: number;
  page: number;
  size: number;
  results: SearchHit[];
  suggestion?: string | null;
}

export interface CrossLanguageSearchHit {
  id: TextId;
  taisho_id: string | null;
  cbeta_id: string;
  title_zh: string;
  title_en: string | null;
  title_sa: string | null;
  title_pi: string | null;
  title_bo: string | null;
  translator: string | null;
  dynasty: string | null;
  category: string | null;
  cbeta_url: string | null;
  has_content: boolean;
  source_code: string | null;
  lang: string;
  score: number | null;
  highlight: Record<string, string[]> | null;
  related_translations: RelatedTranslation[];
}

export interface CrossLanguageSearchResponse {
  total: number;
  page: number;
  size: number;
  results: CrossLanguageSearchHit[];
  suggestion?: string | null;
}

export interface TextDetail {
  id: TextId;
  taisho_id: string | null;
  cbeta_id: string;
  title_zh: string;
  title_sa: string | null;
  title_bo: string | null;
  title_pi: string | null;
  translator: string | null;
  dynasty: string | null;
  fascicle_count: number | null;
  category: string | null;
  subcategory: string | null;
  cbeta_url: string | null;
  has_content: boolean;
  content_char_count: number;
  lang: string;
  created_at: string;
  // Goryeo (Tripitaka Koreana) cross-reference, null when no Goryeo parallel.
  goryeo_k?: string | null;
  kabc_url?: string | null;
}

export interface JuanInfo {
  juan_num: number;
  char_count: number;
}

export interface JuanListResponse {
  text_id: TextId;
  title_zh: string;
  total_juans: number;
  juans: JuanInfo[];
}

export interface JuanContentResponse {
  text_id: TextId;
  cbeta_id: string;
  title_zh: string;
  juan_num: number;
  total_juans: number;
  content: string;
  char_count: number;
  prev_juan: number | null;
  next_juan: number | null;
  // Base-edition (底本) — derived from cbeta_id prefix by the backend.
  // canon is the machine code (taisho / xuzang / pali / kangyur / gretil);
  // canon_label is the Chinese display string (大正藏 / 卍续藏 / …).
  canon?: string | null;
  canon_label?: string | null;
}

export interface MatchedJuan {
  juan_num: number;
  highlight: string[];
  score: number;
}

export interface ContentSearchHit {
  text_id: TextId;
  cbeta_id: string;
  title_zh: string;
  translator: string | null;
  dynasty: string | null;
  juan_num: number;
  lang: string;
  source_code: string | null;
  highlight: string[];
  score: number;
  matched_juan_count: number;
  matched_juans: MatchedJuan[];
}

export interface ContentSearchResponse {
  total: number;
  total_juans: number;
  page: number;
  size: number;
  results: ContentSearchHit[];
}

export interface BookmarkItem {
  id: BookmarkId;
  text_id: TextId;
  title_zh: string;
  cbeta_id: string;
  note: string | null;
  created_at: string;
}

export interface HistoryItem {
  id: number;
  text_id: TextId;
  title_zh: string;
  cbeta_id: string;
  juan_num: number;
  last_read_at: string;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  size: number;
  items: T[];
}

export interface Filters {
  dynasties: string[];
  categories: string[];
  languages: string[];
  languages_all: string[];
  sources: string[];
}

export interface Stats {
  total_texts: number;
  source_count: number;
}

export interface TextIdentifierInfo {
  id: number;
  source_id: SourceId;
  source_code: string;
  source_name: string;
  source_uid: string;
  source_url: string | null;
}

// --- Phase 2 Types ---

export interface SourceDistribution {
  id: number;
  source_id?: SourceId;
  source_code?: string;
  source_name?: string;
  code: string;
  name: string;
  channel_type: string;
  url: string;
  format: string | null;
  license_note: string | null;
  is_primary_ingest: boolean;
  priority: number;
  is_active: boolean;
  created_at: string;
}

export interface DataSource {
  id: SourceId;
  code: string;
  name_zh: string;
  name_en: string | null;
  base_url: string | null;
  description: string | null;
  access_type: "local" | "external" | "api";
  region: string | null;
  languages: string | null;
  research_fields: string | null;
  supports_search: boolean;
  supports_fulltext: boolean;
  has_local_fulltext: boolean;
  has_remote_fulltext: boolean;
  supports_iiif: boolean;
  supports_api: boolean;
  sort_order: number;
  is_active: boolean;
  /** Cron-updated reachability signal; independent of is_active. */
  health_status: "ok" | "degraded" | "cert_invalid" | "unreachable" | "moved";
  health_checked_at: string | null;
  /** Latest-probe context: redirect target for `moved`, failure reason otherwise, null when ok. */
  health_detail: string | null;
  distributions: SourceDistribution[];
}

export interface RelatedTextInfo {
  text_id: TextId;
  cbeta_id: string;
  title_zh: string;
  translator: string | null;
  dynasty: string | null;
  lang: string;
  relation_type: string;
  confidence: number;
  note: string | null;
}

export interface TextRelationsResponse {
  text_id: TextId;
  title_zh: string;
  relations: RelatedTextInfo[];
}

export interface ParallelTextContent {
  text_id: TextId;
  cbeta_id: string;
  title_zh: string;
  translator: string | null;
  lang: string;
  juan_num: number;
  content: string;
}

export interface ParallelReadResponse {
  text_a: ParallelTextContent;
  text_b: ParallelTextContent;
}

export interface KGEntity {
  id: KGEntityId;
  entity_type: string;
  name_zh: string;
  name_sa: string | null;
  name_pi: string | null;
  name_bo: string | null;
  name_en: string | null;
  description: string | null;
  properties: Record<string, unknown> | null;
  text_id: TextId | null;
  external_ids: Record<string, string> | null;
  /** KG relation count — populated by search results, used for the degree badge. */
  relation_count?: number;
}

export interface EntityRelationItem {
  predicate: string;
  direction: string;
  target_id: KGEntityId;
  target_name: string;
  target_type: string;
  confidence: number;
  source: string | null;
}

export interface KGEntityDetail extends KGEntity {
  relations: EntityRelationItem[];
}

export interface KGSearchResponse {
  total: number;
  results: KGEntity[];
}

export interface KGGraphNode {
  id: KGEntityId;
  name: string;
  entity_type: string;
  description: string | null;
}

export interface KGGraphLink {
  source: KGEntityId;
  target: KGEntityId;
  predicate: string;
  confidence: number;
  provenance: string | null;
  evidence: string | null;
}

export interface KGGraphResponse {
  nodes: KGGraphNode[];
  links: KGGraphLink[];
  truncated: boolean;
}

export interface IIIFManifestInfo {
  id: IIIFManifestId;
  text_id: TextId;
  source_id: SourceId;
  label: string;
  manifest_url: string;
  thumbnail_url: string | null;
  provider: string;
  rights: string | null;
}

export async function searchTexts(params: {
  q: string;
  page?: number;
  size?: number;
  dynasty?: string;
  category?: string;
  sources?: string;
  sort?: string;
  lang?: string;
}): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>("/search", { params });
  return data;
}

export async function searchCrossLanguage(params: {
  q: string;
  page?: number;
  size?: number;
  dynasty?: string;
  category?: string;
  sources?: string;
}): Promise<CrossLanguageSearchResponse> {
  const { data } = await api.get<CrossLanguageSearchResponse>("/search/cross-language", { params });
  return data;
}

// 语义搜索（智能搜索）
export interface SemanticSearchHit {
  text_id: TextId;
  juan_num: number;
  title_zh: string;
  translator: string | null;
  dynasty: string | null;
  category: string | null;
  source_code: string | null;
  cbeta_id: string | null;
  cbeta_url: string | null;
  has_content: boolean;
  snippet: string;
  similarity_score: number;
}

export interface SemanticSearchResponse {
  total: number;
  results: SemanticSearchHit[];
  error?: string;  // 服务异常时的错误提示
}

export async function searchSemantic(params: {
  q: string;
  size?: number;
  dynasty?: string;
  category?: string;
  lang?: string;
  sources?: string;
}): Promise<SemanticSearchResponse> {
  const { data } = await api.get<SemanticSearchResponse>("/search/semantic", { params, timeout: 30000 });
  return data;
}

// 跨语对照搜索（MITRA 平行语料）: 输入中文短语，返回对齐的梵/藏语句及其汉文对照
export interface ParallelSentenceHit {
  zh_text: string;
  foreign_text: string;
  foreign_lang: string;
  taisho_id: string;
  text_id: TextId;
  title: string;
  juan_num: number | null;
  mitra_e_score: number | null;
  source: string;
  license: string;
}

export interface ParallelSentencesResponse {
  total: number;
  results: ParallelSentenceHit[];
  error?: string;
}

export async function searchParallelSentences(
  q: string,
  opts: { lang?: string; limit?: number } = {},
): Promise<ParallelSentencesResponse> {
  const { data } = await api.get<ParallelSentencesResponse>("/search/parallel-sentences", {
    params: { q, lang: opts.lang, limit: opts.limit },
    timeout: 30000,
  });
  return data;
}

export async function getSearchSuggestions(q: string): Promise<string[]> {
  const { data } = await api.get<{ suggestions: string[] }>("/search/suggest", { params: { q } });
  return data.suggestions;
}

export interface CbetaRedirect {
  text_id: number;
  cbeta_id: string;
  redirect_to: string;
}

/**
 * Resolve a CBETA ID (e.g. "T0278") to a canonical /texts/{id} URL.
 * Returns null on 404 / non-CBETA input — callers should silently fall back
 * to the regular search results path.
 *
 * 用户在搜索栏输入 CBETA 编号时直跳经文页。
 */
export async function getCbetaRedirect(cbetaId: string): Promise<CbetaRedirect | null> {
  try {
    const { data } = await api.get<CbetaRedirect>(
      `/cbeta/${encodeURIComponent(cbetaId)}`,
    );
    return data;
  } catch {
    return null;
  }
}

export interface UnifiedSearchSection {
  dictionary?: Array<{
    id: number;
    headword: string;
    reading?: string | null;
    definition: string;
    source?: string | null;
    url: string;
  }> | null;
  catalog?: { total: number; results: SearchHit[] } | null;
  content?: { total: number; total_juans?: number; results: ContentSearchHit[] } | null;
  semantic?: { total: number; results: SemanticSearchHit[] } | null;
}

export interface UnifiedSearchResponse {
  query: string;
  sections: UnifiedSearchSection;
  errors: Record<string, string>;
}

export async function searchUnified(params: {
  q: string;
  sources?: string;
  lang?: string;
}): Promise<UnifiedSearchResponse> {
  const { data } = await api.get<UnifiedSearchResponse>("/search/unified", { params, timeout: 30000 });
  return data;
}

export async function getTextDetail(id: number): Promise<TextDetail> {
  const { data } = await api.get<TextDetail>(`/texts/${id}`);
  return data;
}

export async function getFilters(): Promise<Filters> {
  const { data } = await api.get<Filters>("/filters");
  return data;
}

export async function getStats(): Promise<Stats> {
  const { data } = await api.get<Stats>("/stats");
  return data;
}

// Homepage dynamic showcase — live subtitle content for the hero feature cards.
// Every card key is nullable: a null card means "show the static fallback".
// Each card is a POOL (cached ~15min); the frontend picks one at random per page
// load so the card varies on every refresh without extra backend load.
export interface HomeShowcase {
  sources: { sources: number; texts: number; names?: string[] } | null;
  chat: { questions: string[] } | null;
  dictionary: { terms: { term: string; definition: string | null }[] } | null;
  kg: { triples: { subject: string; predicate: string; object: string }[] } | null;
  geo: { count: number; places: string[] } | null;
}

export async function getHomeShowcase(): Promise<HomeShowcase> {
  const { data } = await api.get<HomeShowcase>("/home/showcase");
  return data;
}

// Reader APIs
export async function getJuanList(textId: number): Promise<JuanListResponse> {
  const { data } = await api.get<JuanListResponse>(`/texts/${textId}/juans`);
  return data;
}

export async function getJuanContent(textId: number, juanNum: number, lang?: string): Promise<JuanContentResponse> {
  const params = lang ? { lang } : {};
  const { data } = await api.get<JuanContentResponse>(`/texts/${textId}/juans/${juanNum}`, { params });
  return data;
}

export interface JuanLanguagesResponse {
  text_id: TextId;
  juan_num: number;
  languages: string[];
  default_lang: string;
}

export async function getJuanLanguages(textId: number, juanNum: number): Promise<JuanLanguagesResponse> {
  const { data } = await api.get<JuanLanguagesResponse>(`/texts/${textId}/juans/${juanNum}/languages`);
  return data;
}

// Critical apparatus (校勘异文)
export interface ApparatusReadingItem {
  reading: string;
  witnesses: string[];
  resp: string | null;
  is_omission: boolean;
}

export interface ApparatusEntryItem {
  char_start: number;
  char_end: number;
  lemma: string;
  lemma_siglum: string | null;
  readings: ApparatusReadingItem[];
}

export interface JuanApparatusResponse {
  text_id: TextId;
  juan_num: number;
  entries: ApparatusEntryItem[];
}

export async function getJuanApparatus(textId: number, juanNum: number): Promise<JuanApparatusResponse> {
  const { data } = await api.get<JuanApparatusResponse>(`/texts/${textId}/juans/${juanNum}/apparatus`);
  return data;
}

// CBETA <lb> page-column-line anchors (校勘行锚 / 引用定位)
export interface LineAnchorItem {
  char_offset: number;
  line_ref: string;
}

export interface JuanLineAnchorsResponse {
  text_id: TextId;
  juan_num: number;
  anchors: LineAnchorItem[];
}

export async function getJuanLineAnchors(textId: number, juanNum: number): Promise<JuanLineAnchorsResponse> {
  const { data } = await api.get<JuanLineAnchorsResponse>(`/texts/${textId}/juans/${juanNum}/line-anchors`);
  return data;
}

// Content search
export async function searchContent(params: {
  q: string;
  page?: number;
  size?: number;
  sources?: string;
  lang?: string;
}): Promise<ContentSearchResponse> {
  const { data } = await api.get<ContentSearchResponse>("/search/content", { params });
  return data;
}

// Bookmarks
export async function getBookmarks(page: number = 1, size: number = 20): Promise<PaginatedResponse<BookmarkItem>> {
  const { data } = await api.get<PaginatedResponse<BookmarkItem>>("/bookmarks", { params: { page, size } });
  return data;
}

export async function addBookmark(textId: number, note?: string): Promise<BookmarkItem> {
  const { data } = await api.post<BookmarkItem>("/bookmarks", { text_id: textId, note });
  return data;
}

export async function removeBookmark(textId: number): Promise<void> {
  await api.delete(`/bookmarks/${textId}`);
}

export async function checkBookmark(textId: number): Promise<boolean> {
  try {
    const { data } = await api.get<{ bookmarked: boolean }>(`/bookmarks/check/${textId}`);
    return data.bookmarked;
  } catch {
    return false;
  }
}

// Reading history
export async function getHistory(page: number = 1, size: number = 20): Promise<PaginatedResponse<HistoryItem>> {
  const { data } = await api.get<PaginatedResponse<HistoryItem>>("/history", { params: { page, size } });
  return data;
}

// --- Phase 2 APIs ---

// Data Sources
export async function getSources(): Promise<DataSource[]> {
  const { data } = await api.get<DataSource[]>("/sources");
  return data;
}

export async function getPrimaryIngestDistributions(): Promise<SourceDistribution[]> {
  const { data } = await api.get<SourceDistribution[]>("/sources/ingest/primary");
  return data;
}

export async function getTextIdentifiers(textId: number): Promise<TextIdentifierInfo[]> {
  const { data } = await api.get<TextIdentifierInfo[]>(`/sources/texts/${textId}/identifiers`);
  return data;
}

// Text Relations
export async function getTextRelations(textId: number): Promise<TextRelationsResponse> {
  const { data } = await api.get<TextRelationsResponse>(`/texts/${textId}/relations`);
  return data;
}

export async function getParallelRead(
  textId: number,
  compareId: number,
  juan: number = 1
): Promise<ParallelReadResponse> {
  const { data } = await api.get<ParallelReadResponse>(`/texts/${textId}/parallel-read`, {
    params: { compare: compareId, juan },
  });
  return data;
}

// Knowledge Graph
export async function searchKGEntities(
  q: string,
  entityType?: string,
  limit: number = 20,
  hasRelations?: boolean,
): Promise<KGSearchResponse> {
  const { data } = await api.get<KGSearchResponse>("/kg/entities", {
    params: { q, entity_type: entityType, limit, has_relations: hasRelations },
  });
  return data;
}

export async function getKGEntity(entityId: number): Promise<KGEntityDetail> {
  const { data } = await api.get<KGEntityDetail>(`/kg/entities/${entityId}`);
  return data;
}

export async function getKGEntityGraph(
  entityId: number,
  depth: number = 2,
  maxNodes: number = 150,
  predicates?: string[],
): Promise<KGGraphResponse> {
  const { data } = await api.get<KGGraphResponse>(`/kg/entities/${entityId}/graph`, {
    params: {
      depth,
      max_nodes: maxNodes,
      predicates: predicates?.length ? predicates.join(",") : undefined,
    },
  });
  return data;
}

export interface KGMentionItem {
  id: number;
  name_zh: string;
  entity_type: string;
  snippet?: string | null;
}

export interface KGMentionsResponse {
  mentions: KGMentionItem[];
}

export async function getKGEntityMentions(
  entityId: number,
  limit: number = 30,
): Promise<KGMentionsResponse> {
  const { data } = await api.get<KGMentionsResponse>(
    `/kg/entities/${entityId}/mentions`,
    { params: { limit } },
  );
  return data;
}

export interface KGStats {
  entities: Record<string, number>;
  relations: Record<string, number>;
  total_entities: number;
  total_relations: number;
}

export async function getKGStats(): Promise<KGStats> {
  const { data } = await api.get<KGStats>("/kg/stats");
  return data;
}

// /kg/geo is serialized with exclude_none (the payload is ~65k entities; emitting
// the mostly-null fields as explicit nulls cost ~5.5MB of raw JSON), so every
// nullable field may be ABSENT rather than null. Compare with `!= null`, never `!== null`.
export interface KGGeoEntity {
  id: number;
  entity_type: string;
  name_zh: string;
  name_en?: string | null;
  description?: string | null;
  latitude: number;
  longitude: number;
  year_start?: number | null;
  year_end?: number | null;
  province?: string | null;
  city?: string | null;
  district?: string | null;
}

export interface KGGeoResponse {
  entities: KGGeoEntity[];
  total: number;
}

export interface KGLineageArc {
  teacher_id: number;
  teacher_name: string;
  teacher_lat: number;
  teacher_lng: number;
  student_id: number;
  student_name: string;
  student_lat: number;
  student_lng: number;
  year: number | null;
  school: string | null;
}

export interface KGLineageArcsResponse {
  arcs: KGLineageArc[];
  total: number;
}

export async function getKGGeoEntities(params?: {
  entity_type?: string;
  year_start?: number;
  year_end?: number;
  south?: number;
  west?: number;
  north?: number;
  east?: number;
  limit?: number;
}): Promise<KGGeoResponse> {
  // Payload can exceed 16MB (65K+ entities); default 15s timeout trips on
  // typical networks and leaves the map stuck on "暂无地理数据".
  const { data } = await api.get<KGGeoResponse>("/kg/geo", {
    params,
    timeout: 120000,
  });
  return data;
}

export async function getKGLineageArcs(params?: {
  school?: string;
  year_start?: number;
  year_end?: number;
  limit?: number;
}): Promise<KGLineageArcsResponse> {
  const { data } = await api.get<KGLineageArcsResponse>("/kg/lineage-arcs", { params });
  return data;
}

export interface KGTimelineEntity {
  id: number;
  name_zh: string;
  entity_type: string;
  year_start: number;
  year_end: number | null;
}

export interface KGTimelineResponse {
  entities: KGTimelineEntity[];
  total: number;
}

export async function getKGTimeline(params?: {
  entity_type?: string;
  limit?: number;
}): Promise<KGTimelineResponse> {
  const { data } = await api.get<KGTimelineResponse>("/kg/timeline", { params });
  return data;
}

// Dictionary
export interface DictEntry {
  id: DictEntryId;
  headword: string;
  reading: string | null;
  definition: string;
  lang: string;
  source_code: string | null;
  source_name: string | null;
}

export interface DictSearchResponse {
  total: number;
  page: number;
  size: number;
  results: DictEntry[];
}

// --- Annotations ---

export interface AnnotationItem {
  id: AnnotationId;
  text_id: TextId;
  juan_num: number;
  start_pos: number;
  end_pos: number;
  annotation_type: string;
  content: string;
  user_id: UserId;
  status: string;
  created_at: string;
  updated_at: string;
}

export async function getAnnotations(textId: number, juanNum: number): Promise<AnnotationItem[]> {
  const { data } = await api.get<AnnotationItem[]>("/annotations", { params: { text_id: textId, juan_num: juanNum } });
  return data;
}

export async function createAnnotation(payload: {
  text_id: number;
  juan_num: number;
  start_pos: number;
  end_pos: number;
  annotation_type: string;
  content: string;
}): Promise<AnnotationItem> {
  const { data } = await api.post<AnnotationItem>("/annotations", payload);
  return data;
}

export async function deleteAnnotation(annotationId: number): Promise<void> {
  await api.delete(`/annotations/${annotationId}`);
}

export async function searchDictionary(params: {
  q: string;
  page?: number;
  size?: number;
  lang?: string;
  source?: string;
}): Promise<DictSearchResponse> {
  const { data } = await api.get<DictSearchResponse>("/dictionary/search", { params });
  return data;
}

// Dictionary Sources
export interface DictSourceInfo {
  id: number;
  code: string;
  name_zh: string;
  name_en: string | null;
  description?: string;
  entry_count: number;
  languages: string[];
  base_url: string | null;
}

export async function getDictionarySources(): Promise<DictSourceInfo[]> {
  const { data } = await api.get<DictSourceInfo[]>("/dictionary/sources");
  return data;
}

// Dictionary grouped search
export interface DictGroupedResult {
  source_code: string;
  source_name: string;
  total: number;
  entries: DictEntry[];
}

export interface DictGroupedSearchResponse {
  total: number;
  page: number | null;
  page_size: number | null;
  groups: DictGroupedResult[];
}

export async function searchDictionaryGrouped(params: {
  q: string;
  lang?: string;
  source?: string;
  page?: number;
}): Promise<DictGroupedSearchResponse> {
  const { data } = await api.get<DictGroupedSearchResponse>("/dictionary/search/grouped", { params });
  return data;
}

// Cross-lingual term concept (multilingual concept card)
export interface DictConcept {
  sanskrit: string | null;
  devanagari: string | null;
  pali: string | null;
  tibetan: string | null;
  chinese: string | null;
  english: string | null;
}

export interface DictConceptEntry {
  id: DictEntryId;
  headword: string;
  source_name: string | null;
  definition_preview: string;
}

export interface DictConceptLangGroup {
  lang: string;
  entries: DictConceptEntry[];
}

export interface DictConceptResponse {
  concept: DictConcept | null;
  entries_by_lang: DictConceptLangGroup[];
}

export async function getDictConcept(q: string): Promise<DictConceptResponse> {
  const { data } = await api.get<DictConceptResponse>("/dictionary/concept", { params: { q } });
  return data;
}

// Dictionary hot terms
export async function getDictionaryHot(): Promise<string[]> {
  const { data } = await api.get<{ terms: string[] }>("/dictionary/hot");
  return data.terms;
}

// IIIF Manifests
export async function getTextManifests(textId: number): Promise<IIIFManifestInfo[]> {
  const { data } = await api.get<IIIFManifestInfo[]>(`/iiif/texts/${textId}/manifests`);
  return data;
}

// Source Suggestions
export async function submitSourceSuggestion(payload: {
  name: string;
  url: string;
  description?: string;
}): Promise<{ id: number; name: string; url: string; status: string }> {
  const { data } = await api.post("/source-suggestions", payload);
  return data;
}

// Admin: Source Suggestions Management
export interface SourceSuggestionItem {
  id: number; // 暂不品牌化，使用频率低
  name: string;
  url: string;
  description: string | null;
  status: string;
  submitted_at: string | null;
}

export async function getSourceSuggestions(
  page: number = 1,
  size: number = 20,
  status?: string,
): Promise<PaginatedResponse<SourceSuggestionItem>> {
  const { data } = await api.get<PaginatedResponse<SourceSuggestionItem>>(
    "/source-suggestions",
    { params: { page, size, status: status || undefined } },
  );
  return data;
}

export async function updateSuggestionStatus(
  id: number,
  status: string,
): Promise<SourceSuggestionItem> {
  const { data } = await api.patch<SourceSuggestionItem>(
    `/source-suggestions/${id}`,
    { status },
  );
  return data;
}

export async function deleteSourceSuggestion(id: number): Promise<void> {
  await api.delete(`/source-suggestions/${id}`);
}

export async function reviewAnnotation(
  annotationId: number,
  payload: { action: string; comment?: string },
): Promise<void> {
  await api.post(`/annotations/${annotationId}/review`, payload);
}

// --- Notifications ---

export interface NotificationItem {
  id: NotificationId;
  type: string;
  title: string;
  content: string;
  is_read: boolean;
  created_at: string;
}

export async function getNotifications(page: number = 1, size: number = 20): Promise<{
  total: number;
  items: NotificationItem[];
}> {
  const { data } = await api.get("/notifications", { params: { page, size } });
  return data;
}

export async function getUnreadNotificationCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>("/notifications/unread-count");
  return data.count;
}

export async function markNotificationRead(id: number): Promise<void> {
  await api.patch(`/notifications/${id}/read`);
}

export async function markAllNotificationsRead(): Promise<void> {
  await api.patch("/notifications/read-all");
}

// --- Feedback ---

export async function submitFeedback(payload: {
  content: string;
  contact?: string;
}): Promise<{ id: number; content: string; status: string }> {
  const { data } = await api.post("/feedbacks", payload);
  return data;
}

export interface AdminFeedbackItem {
  id: number;
  user_id: UserId;
  username: string;
  content: string;
  contact: string | null;
  status: string;
  admin_reply: string | null;
  replied_at: string | null;
  created_at: string;
}

export async function getAdminFeedbacks(params: {
  page?: number;
  size?: number;
  status?: string;
}): Promise<PaginatedResponse<AdminFeedbackItem>> {
  const { data } = await api.get<PaginatedResponse<AdminFeedbackItem>>("/feedbacks", { params });
  return data;
}

export async function updateFeedbackStatus(
  id: number,
  status: string,
): Promise<void> {
  await api.patch(`/feedbacks/${id}`, { status });
}

export async function replyFeedback(id: number, reply: string): Promise<void> {
  await api.post(`/feedbacks/${id}/reply`, { reply });
}

// --- Admin Dashboard ---

export interface AdminOverview {
  total_users: number;
  new_users_today: number;
  new_users_yesterday: number;
  total_sessions: number;
  new_sessions_today: number;
  new_sessions_yesterday: number;
  total_messages: number;
  new_messages_today: number;
  new_messages_yesterday: number;
  pending_suggestions: number;
  pending_annotations: number;
  last_updated: string;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface AdminTrends {
  registrations: DailyCount[];
  messages: DailyCount[];
  active_users: DailyCount[];
}

export interface ActiveUserDetail {
  user_id: UserId;
  username: string | null;
  display_name: string | null;
  email: string | null;
  role: string;
  chat_messages: number;
  texts_read: number;
  last_active_at: string | null;
  api_provider: string | null;
}

export interface ActiveUserDayDetail {
  date: string;
  total: number;
  users: ActiveUserDetail[];
}

export interface AdminUserItem {
  id: UserId;
  username: string;
  display_name: string | null;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_active_at: string | null;
}

export interface AdminAnnotationItem {
  id: AnnotationId;
  text_id: TextId;
  juan_num: number;
  annotation_type: string;
  content: string;
  user_id: UserId;
  username: string;
  status: string;
  created_at: string;
}

export async function getAdminOverview(): Promise<AdminOverview> {
  const { data } = await api.get<AdminOverview>("/admin/stats/overview");
  return data;
}

export async function getAdminTrends(days: number = 30): Promise<AdminTrends> {
  const { data } = await api.get<AdminTrends>("/admin/stats/trends", { params: { days } });
  return data;
}

export async function getAdminActiveUsers(date: string): Promise<ActiveUserDayDetail> {
  const { data } = await api.get<ActiveUserDayDetail>("/admin/stats/active-users", { params: { date } });
  return data;
}

export async function getAdminUsers(params: {
  page?: number;
  size?: number;
  q?: string;
  sort_by?: string;
  sort_order?: string;
}): Promise<PaginatedResponse<AdminUserItem>> {
  const { data } = await api.get<PaginatedResponse<AdminUserItem>>("/admin/users", { params });
  return data;
}

export async function updateAdminUser(
  id: number,
  payload: { role?: string; is_active?: boolean },
): Promise<AdminUserItem> {
  const { data } = await api.patch<AdminUserItem>(`/admin/users/${id}`, payload);
  return data;
}

export async function getAdminAnnotations(params: {
  page?: number;
  size?: number;
  status?: string;
}): Promise<PaginatedResponse<AdminAnnotationItem>> {
  const { data } = await api.get<PaginatedResponse<AdminAnnotationItem>>("/admin/annotations", { params });
  return data;
}

export interface AdminAuditLogItem {
  id: number;
  actor_id: number | null;
  actor_username: string | null;
  action: string;
  target_type: string;
  target_id: number | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export async function getAdminAuditLog(params: {
  page?: number;
  size?: number;
  action?: string;
}): Promise<PaginatedResponse<AdminAuditLogItem>> {
  const { data } = await api.get<PaginatedResponse<AdminAuditLogItem>>("/admin/audit-log", { params });
  return data;
}

// --- Admin Module Usage (Umami analytics) ---

export interface ModuleEventItem {
  event_name: string;
  label: string;
  count: number;
}

export interface KeywordItem {
  keyword: string;
  count: number;
}

export interface AnswerQuality {
  chat_questions: number;
  citation_click: number;
  chat_copy: number;
  chat_retry: number;
  citation_click_rate: number | null;
  copy_rate: number | null;
  retry_rate: number | null;
}

export interface AdminModuleUsage {
  days: number;
  events: ModuleEventItem[];
  top_search_keywords: KeywordItem[];
  answer_quality: AnswerQuality;
}

export async function getAdminModuleUsage(days: number = 7): Promise<AdminModuleUsage> {
  const { data } = await api.get<AdminModuleUsage>("/admin/stats/module-usage", {
    params: { days },
  });
  return data;
}

// --- Admin: Answer-Quality Queue ---

export interface AnswerQueueSource {
  text_id: number;
  juan_num: number;
  chunk_index: number;
  chunk_text: string;
  score: number | null;
  title_zh: string;
  lang: string;
}

export interface AnswerQueueItem {
  message_id: number;
  session_id: number;
  question: string;
  answer: string;
  sources: AnswerQueueSource[];
  reason_tags: string[];
  suspicion_score: number;
  feedback: string | null;
  created_at: string;
}

export interface ScoreDistribution {
  p10: number | null;
  p25: number | null;
  p50: number | null;
  p90: number | null;
}

export interface AnswerQueueResponse {
  total_unreviewed: number;
  score_distribution: ScoreDistribution;
  tag_distribution: Record<string, number>;
  items: AnswerQueueItem[];
}

export interface AnswerReviewStats {
  reviewed_total: number;
  good: number;
  bad: number;
  by_category: Record<string, number>;
  last_reviewed_at: string | null;
}

export async function getAnswerQualityQueue(params: {
  window?: number;
  min_suspicion?: number;
  category?: string;
  limit?: number;
  offset?: number;
}): Promise<AnswerQueueResponse> {
  const { data } = await api.get<AnswerQueueResponse>(
    "/admin/answer-quality/queue",
    { params },
  );
  return data;
}

export async function submitAnswerReview(payload: {
  message_id: number;
  verdict: "good" | "bad";
  failure_category?: string;
  note?: string;
}): Promise<{ ok: boolean; remaining_unreviewed: number }> {
  const { data } = await api.post("/admin/answer-quality/reviews", payload);
  return data;
}

export async function getAnswerReviewStats(
  params?: { window?: number },
): Promise<AnswerReviewStats> {
  const { data } = await api.get<AnswerReviewStats>(
    "/admin/answer-quality/reviews/stats",
    { params },
  );
  return data;
}

export interface AdminPendingSummary {
  answer_quality: number;
  alignment_candidates: number;
  suggestions: number;
  feedbacks: number;
  annotations: number;
}

/** 侧边栏角标的唯一数据源:一次请求拿全部待办计数(后端全部走 COUNT)。 */
export async function getAdminPendingSummary(): Promise<AdminPendingSummary> {
  const { data } = await api.get<AdminPendingSummary>("/admin/pending-summary");
  return data;
}

// --- Similar Passages ---

export interface SimilarPassageItem {
  text_id: TextId;
  juan_num: number;
  chunk_text: string;
  score: number;
  title_zh: string;
  translator: string | null;
  dynasty: string | null;
}


// --- Chat (AI Q&A) ---

export interface ParallelChunk {
  text_id: number;
  juan_num: number;
  chunk_index: number;
  chunk_text: string;
  lang: string;  // "lzh" | "pi" | "sa" | "bo" | "en"
  title?: string;
  confidence?: number;
}

export interface ChatSource {
  text_id: TextId;
  juan_num: number;
  chunk_index?: number;
  chunk_text: string;
  score: number;
  title_zh?: string;
  // Trilingual RAG additions
  lang?: string;
  source_id?: number;
  parallel_chunks?: ParallelChunk[];
  // Portable cross-canon citation id (fojin:cbeta/T0001.1 …), null when the
  // source has no round-trippable cbeta_id.
  urn?: string | null;
}

export interface ChunkContextItem {
  chunk_index: number;
  chunk_text: string;
  is_center: boolean;
}

// --- Alignment API (trilingual cross-canon parallels) ---

export interface ParallelPair {
  text_id: number;
  juan_num: number;
  chunk_index: number;
  chunk_text: string;
  lang: string;
  title: string;
  confidence: number;
  original_preview?: string | null;
  original_lang?: string | null;
  /** "fojin" (alignment_pairs, deep-linkable) | "mitra-parallel" (inline Skt/Tib, CC BY-SA 4.0, no deep-link). */
  source?: string;
}

export interface ChunkAlignmentResponse {
  source_text_id: number;
  source_juan_num: number;
  source_chunk_index: number;
  parallels: ParallelPair[];
}

export interface JuanAlignmentEntry {
  chunk_index: number;
  chunk_text: string;
  parallels: ParallelPair[];
}

export interface JuanAlignmentResponse {
  text_id: number;
  juan_num: number;
  total_chunks: number;
  chunks_with_parallels: number;
  entries: JuanAlignmentEntry[];
}

export async function getChunkAlignment(
  textId: number,
  juanNum: number,
  chunkIndex: number,
  limit: number = 5,
): Promise<ChunkAlignmentResponse> {
  const { data } = await api.get<ChunkAlignmentResponse>(
    `/alignment/chunks/${textId}/${juanNum}/${chunkIndex}`,
    { params: { limit } },
  );
  return data;
}

export async function getJuanAlignment(
  textId: number,
  juanNum: number,
): Promise<JuanAlignmentResponse> {
  const { data } = await api.get<JuanAlignmentResponse>(
    `/alignment/texts/${textId}/juans/${juanNum}`,
  );
  return data;
}

export interface AlignmentCatalogEntry {
  text_id: number;
  cbeta_id: string;
  title_zh: string;
  other_lang: string;
  pair_count: number;
  partner_count: number;
  avg_confidence: number | null;        // fojin-verified only; null for mitra-only
  sources: string[];                    // "fojin" (verified) / "mitra" (parallel)
  sample_juan: number;
  sample_partner_id: number | null;     // mitra coverage has no fojin partner
  sample_partner_title: string;
}

export interface AlignmentCatalogResponse {
  entries: AlignmentCatalogEntry[];
  total_pairs: number;
}

export async function getAlignmentCatalog(): Promise<AlignmentCatalogResponse> {
  const { data } = await api.get<AlignmentCatalogResponse>("/alignment/catalog");
  return data;
}

export interface CanonicalParallel {
  related_text_id: number;
  related_cbeta_id: string;
  related_title: string;
  related_lang: string;
  relation_type: string;
  note?: string | null;
  pali_preview?: string | null;
  english_preview?: string | null;
}

export interface CanonicalParallelsResponse {
  text_id: number;
  source_cbeta_id: string;
  source_title: string;
  total: number;
  parallels: CanonicalParallel[];
}

export async function getCanonicalParallels(textId: number): Promise<CanonicalParallelsResponse> {
  const { data } = await api.get<CanonicalParallelsResponse>(
    `/alignment/canonical/${textId}`,
  );
  return data;
}

export interface FullParallelContentResponse {
  text_id: number;
  cbeta_id: string;
  title: string;
  lang: string;
  pali_full?: string | null;
  english_full?: string | null;
  pali_chars: number;
  english_chars: number;
}

export async function getFullParallelContent(textId: number): Promise<FullParallelContentResponse> {
  const { data } = await api.get<FullParallelContentResponse>(
    `/alignment/canonical/full/${textId}`,
  );
  return data;
}

// --- Sentence-level alignment (逐句对读, P4-C frozen contract) ---
// GET /api/alignment/sentences/{text_id}/{juan_num} — side_a is always the
// requested text (current juan, Chinese side), side_b the counterpart foreign
// text (carries its own text_id/juan_num for future deep-linking). Ships dark:
// an empty sentence_alignments table (or the flag off) yields total=0 / pairs=[]
// and never errors.
export interface SentenceSideA {
  char_start: number;
  char_end: number;
  lang: string;
  text: string;
}

export interface SentenceSideB {
  text_id: number;
  juan_num: number;
  char_start: number;
  char_end: number;
  lang: string;
  title: string;
  text: string;
}

export interface SentencePair {
  side_a: SentenceSideA;
  side_b: SentenceSideB;
  similarity: number;
  align_type: "1-1" | "1-2" | "2-1";
  method: string;
  is_verified: boolean;
}

export interface SentenceAlignmentResponse {
  text_id: number;
  juan_num: number;
  total: number;
  pairs: SentencePair[];
}

export async function getSentenceParallels(
  textId: number,
  juanNum: number,
): Promise<SentenceAlignmentResponse> {
  const { data } = await api.get<SentenceAlignmentResponse>(
    `/alignment/sentences/${textId}/${juanNum}`,
  );
  return data;
}

export interface ChunkContextResponse {
  text_id: TextId;
  juan_num: number;
  title_zh: string;
  center_chunk_index: number;
  radius: number;
  chunks: ChunkContextItem[];
  has_more_before: boolean;
  has_more_after: boolean;
}

export async function getChunkContext(
  textId: TextId | number,
  juanNum: number,
  chunkIndex: number,
  radius: number = 2,
): Promise<ChunkContextResponse> {
  const { data } = await api.get<ChunkContextResponse>(
    `/texts/${textId}/juans/${juanNum}/chunks/${chunkIndex}/context`,
    { params: { radius } },
  );
  return data;
}

export interface ChatResponse {
  session_id: ChatSessionId;
  message: string;
  sources: ChatSource[];
  trust_status?: ChatTrustStatus | null;
}

export interface ChatSessionItem {
  id: ChatSessionId;
  title: string | null;
  created_at: string;
}

export type ChatTrustState =
  | "verified"
  | "citation_corrected"
  | "quote_relaxed"
  | "quote_unverified"
  | "sources_available"
  | "no_sources";

export interface ChatTrustStatus {
  state: ChatTrustState;
  citation_count: number;
  source_count: number;
  citation_mutation_count: number;
  quote_mutation_count: number;
  /** How many 「…」 quotes were verbatim-checked against a source. null for
   *  historical answers reconstructed from a diagnostic (not stored there). */
  quote_checked_count?: number | null;
  max_source_score?: number | null;
  min_source_score?: number | null;
}

// --- Research assistant (POST /api/research/query) ---

export interface ResearchStep {
  tool: string; // "corpus" | "dictionary" | "entity"
  query: string;
  aspect: string;
  num_sources: number;
}

export interface ResearchReference {
  kind: string; // "dictionary" | "entity"
  term: string;
  detail: string;
  source?: string | null;
}

export interface ResearchReport {
  question: string;
  plan: ResearchStep[];
  answer: string;
  sources: ChatSource[];
  references: ResearchReference[];
  trust_status?: ChatTrustStatus | null;
}

export async function runResearch(question: string, maxSteps = 3): Promise<ResearchReport> {
  // The agent fans out into a plan + several retrievals + a synthesis, all on a
  // (often reasoning-class) LLM, so a single call routinely runs 60-90s — far
  // past the 15s axios default. Give it a 3-minute ceiling so the client waits
  // instead of aborting with a spurious "research failed".
  const { data } = await api.post<ResearchReport>(
    "/research/query",
    { question, max_steps: maxSteps },
    { timeout: 180000 },
  );
  return data;
}

/** 检索完成、生成尚未开始时的轻量进度信息。只用于等待期提示，与答案下方的
 *  完整 `sources` 列表是两回事（后者仍在答案之后才发）。 */
export interface ChatRetrieval {
  count: number;
  titles: string[];
}

/** 推理模型思考阶段的活性信号（后端按约 1 次/秒节流）。`chars` 是累计的
 *  reasoning_content 字符数 —— 只用来证明「仍在推进」，不含推理原文：那里面
 *  全是会被模型自己推翻的中间结论，摆在答案位置上是拿答案真实性冒险。 */
export interface ChatReasoning {
  chars: number;
}

export interface ChatMessageItem {
  id: number;
  role: string;
  content: string;
  sources: ChatSource[] | null;
  trust_status?: ChatTrustStatus | null;
  feedback?: string | null;
  created_at: string;
  /** 仅存在于流式生成过程中；不持久化，历史消息读回来时为空。 */
  retrieval?: ChatRetrieval | null;
  /** 首个推理信号到达的时刻（epoch ms），用于渲染「已思考 N 秒」。同样不持久化。 */
  reasoningSince?: number | null;
}

export interface SharedQA {
  id: string;
  question: string;
  answer: string;
  sources: ChatSource[] | null;
  view_count: number;
  created_at: string;
}

export interface SharedQACreated {
  id: string;
  url: string;
}

export async function createSharedQA(payload: {
  question: string;
  answer: string;
  sources: ChatSource[] | null;
}): Promise<SharedQACreated> {
  const { data } = await api.post<SharedQACreated>("/share/qa", payload);
  return data;
}

export async function getSharedQA(id: string): Promise<SharedQA> {
  const { data } = await api.get<SharedQA>(`/share/qa/${id}`);
  return data;
}

export async function sendChatMessage(
  message: string,
  sessionId?: number,
): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>("/chat", {
    message,
    session_id: sessionId,
  }, { timeout: 300000 });
  return data;
}

export interface ChatQuota {
  limit: number;
  used: number;
  remaining: number;
  has_byok: boolean;
}

export async function getChatQuota(): Promise<ChatQuota> {
  const { data } = await api.get<ChatQuota>("/chat/quota");
  return data;
}

export async function getChatSessions(): Promise<ChatSessionItem[]> {
  const { data } = await api.get<ChatSessionItem[]>("/chat/sessions");
  return data;
}

export async function getChatSession(sessionId: number): Promise<{
  id: number;
  title: string | null;
  messages: ChatMessageItem[];
  created_at: string;
}> {
  const { data } = await api.get(`/chat/sessions/${sessionId}`);
  return data;
}

export async function getChatSessionMessages(
  sessionId: number,
  page: number = 1,
  size: number = 50,
): Promise<{ total: number; page: number; size: number; messages: ChatMessageItem[] }> {
  const { data } = await api.get(`/chat/sessions/${sessionId}/messages`, { params: { page, size } });
  return data;
}

export async function deleteChatSession(sessionId: number): Promise<void> {
  await api.delete(`/chat/sessions/${sessionId}`);
}

export async function updateChatMessageFeedback(
  messageId: number,
  feedback: "up" | "down" | null,
): Promise<void> {
  await api.put(`/chat/messages/${messageId}/feedback`, { feedback });
}

export interface HotQuestionsResponse {
  questions: string[];
}

export async function getHotQuestions(): Promise<HotQuestionsResponse> {
  const { data } = await api.get<HotQuestionsResponse>("/chat/hot-questions");
  return data;
}

export type HotQuestionCategory =
  | "白话翻译" // i18n-exempt — backend enum contract
  | "经文解读" // i18n-exempt — backend enum contract
  | "对比辨析" // i18n-exempt — backend enum contract
  | "佛教史话"; // i18n-exempt — backend enum contract

export interface HotQuestionCard {
  id: number;
  category: HotQuestionCategory;
  display_text: string;
}

export interface HotQuestionCardsResponse {
  questions: HotQuestionCard[];
}

export async function getRandomHotQuestions(
  excludeIds: number[] = [],
): Promise<HotQuestionCardsResponse> {
  const params = excludeIds.length
    ? { exclude_ids: excludeIds.join(",") }
    : undefined;
  const { data } = await api.get<HotQuestionCardsResponse>(
    "/chat/hot-questions/random",
    { params },
  );
  return data;
}

export interface StreamCallbacks {
  onToken: (content: string) => void;
  onSources: (sources: ChatSource[]) => void;
  onTrustStatus?: (trustStatus: ChatTrustStatus) => void;
  onSessionId: (sessionId: number) => void;
  onSearching?: (message: string) => void;
  /** 检索完成、生成开始之前触发一次。用于把等待期的静态文案换成实际召回的经典。 */
  onRetrieved?: (retrieval: ChatRetrieval) => void;
  /** 推理模型思考期间按约 1 次/秒触发。用于证明「仍在推进」而非卡死。 */
  onReasoning?: (reasoning: ChatReasoning) => void;
  /**
   * Backend has rewritten one or more 【《X》第N卷】 references in the
   * answer to anchor them to retrieved sources. The full corrected
   * answer is provided; the consumer should replace the visible
   * message body with this value so reload + the just-streamed view
   * stay consistent with what was persisted.
   */
  onCitationCorrection?: (correctedAnswer: string) => void;
  /**
   * Real chat_messages.id of the just-persisted assistant reply. Arrives
   * after the stream is otherwise complete (after sources/correction,
   * before done). Consumers must swap their in-flight Date.now()
   * placeholder id with this real id, so the feedback / share buttons
   * target the correct row.
   */
  onMessageId?: (assistantMessageId: number) => void;
  onError: (message: string) => void;
  onDone: () => void;
}

export interface ReadingContext {
  text_id: number;
  juan_num: number;
  selected_text?: string;
  page_content?: string;
}

export interface ChatStreamOptions {
  signal?: AbortSignal;
  readingContext?: ReadingContext;
  hotQuestionId?: number | null;
  modelId?: string | null;
  attachmentIds?: number[] | null;
}

export function sendChatMessageStream(
  message: string,
  sessionId: number | undefined,
  masterId: string | null,
  callbacks: StreamCallbacks,
  options: ChatStreamOptions = {},
): Promise<void> {
  const {
    signal,
    readingContext,
    hotQuestionId,
    modelId,
    attachmentIds,
  } = options;
  return new Promise<void>((resolve) => {
    // Get auth token from localStorage (same pattern as axios interceptor)
    let token = "";
    try {
      const raw = localStorage.getItem("fojin-auth");
      if (raw) {
        const { state } = JSON.parse(raw);
        if (state?.token) token = state.token;
      }
    } catch { /* ignore */ }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/chat/stream");
    xhr.setRequestHeader("Content-Type", "application/json");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

    let lastIndex = 0;
    let buffer = "";
    let done = false;

    function processChunk(newText: string) {
      buffer += newText;
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (!payload) continue;
        try {
          const event = JSON.parse(payload);
          switch (event.type) {
            case "token":
              callbacks.onToken(event.content);
              break;
            case "sources":
              callbacks.onSources(event.sources);
              break;
            case "reasoning":
              callbacks?.onReasoning?.({ chars: event.chars });
              break;
            case "retrieved":
              callbacks?.onRetrieved?.({
                count: event.count,
                titles: Array.isArray(event.titles) ? event.titles : [],
              });
              break;
            case "trust_status":
              callbacks?.onTrustStatus?.(event.trust_status);
              break;
            case "session_id":
              callbacks.onSessionId(event.session_id);
              break;
            case "searching":
              callbacks?.onSearching?.(event.message);
              break;
            case "citation_correction":
              callbacks?.onCitationCorrection?.(event.content);
              break;
            case "message_id":
              callbacks?.onMessageId?.(event.id);
              break;
            case "error":
              callbacks.onError(event.message);
              break;
            case "done":
              done = true;
              callbacks.onDone();
              resolve();
              return;
          }
        } catch { /* skip malformed JSON */ }
      }
    }

    xhr.onprogress = function () {
      const newData = xhr.responseText.substring(lastIndex);
      lastIndex = xhr.responseText.length;
      if (newData) processChunk(newData);
    };

    xhr.onload = function () {
      // Process any remaining data
      const remaining = xhr.responseText.substring(lastIndex);
      if (remaining) processChunk(remaining);
      if (!done) {
        if (xhr.status === 401) {
          useAuthStore.getState().logout();
          window.location.href = "/login";
          return;
        }
        if (xhr.status !== 200) {
          let detail = i18n.t("chat.stream.sendFailed");
          try { detail = JSON.parse(xhr.responseText).detail || detail; } catch { /* ignore */ }
          callbacks.onError(detail);
        }
        callbacks.onDone();
        resolve();
      }
    };

    xhr.onerror = function () {
      if (!done) {
        callbacks.onError(i18n.t("chat.stream.networkError"));
        callbacks.onDone();
        resolve();
      }
    };

    xhr.ontimeout = function () {
      if (!done) {
        callbacks.onError(i18n.t("chat.stream.timeout"));
        callbacks.onDone();
        resolve();
      }
    };

    // 5 min — must exceed the backend's per-LLM-call timeout (120s for
    // reader-mode page_content + retry/fallback chain) so a slow reasoning
    // model on a long passage doesn't get killed by the client mid-stream
    // and surface as the generic "请求失败，请重试". 90s was the original
    // cap and routinely tripped on DeepSeek V4 Pro + reader-mode juan.
    xhr.timeout = 300000;

    // AbortSignal support
    if (signal) {
      signal.addEventListener("abort", () => {
        xhr.abort();
        if (!done) {
          callbacks.onError(i18n.t("chat.stream.cancelled"));
          callbacks.onDone();
          resolve();
        }
      });
    }

    xhr.send(JSON.stringify({
      message,
      session_id: sessionId ?? null,
      master_id: masterId,
      ...(modelId ? { model_id: modelId } : {}),
      ...(hotQuestionId != null ? { hot_question_id: hotQuestionId } : {}),
      ...(attachmentIds && attachmentIds.length > 0
        ? { attachment_ids: attachmentIds }
        : {}),
      ...(readingContext ? {
        text_id: readingContext.text_id,
        juan_num: readingContext.juan_num,
        selected_text: readingContext.selected_text ?? null,
        page_content: readingContext.page_content ?? null,
      } : {}),
    }));
  });
}

// --- BYOK (Bring Your Own Key) ---

export interface ApiKeyStatus {
  has_api_key: boolean;
  provider: string | null;
  model: string | null;
  key_preview: string | null;
}

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  const { data } = await api.get<ApiKeyStatus>("/auth/api-key");
  return data;
}

export async function saveApiKey(payload: {
  api_key: string;
  provider: string;
  model?: string;
  custom_url?: string;
}): Promise<ApiKeyStatus> {
  const { data } = await api.put<ApiKeyStatus>("/auth/api-key", payload);
  return data;
}

export async function deleteApiKey(): Promise<void> {
  await api.delete("/auth/api-key");
}

export interface ChangePasswordResponse {
  access_token: string;
  token_type: string;
}

export async function changePassword(payload: {
  old_password: string;
  new_password: string;
}): Promise<ChangePasswordResponse> {
  const { data } = await api.post<ChangePasswordResponse>(
    "/auth/change-password",
    payload,
  );
  return data;
}

export default api;

// Text Versions (aggregated view)
export interface VersionTranslation {
  text_id: number;
  title_zh: string | null;
  title_en: string | null;
  translator: string | null;
  dynasty: string | null;
  lang: string | null;
  source_name: string | null;
  relation_type: string | null;
}

export interface VersionIIIF {
  id: number;
  label: string | null;
  manifest_url: string;
  thumbnail_url: string | null;
  provider: string | null;
}

export interface VersionSourceLink {
  source_name: string;
  source_url: string | null;
}

export interface TextVersionsResponse {
  text_id: number;
  title_zh: string | null;
  translations: VersionTranslation[];
  iiif_manifests: VersionIIIF[];
  source_links: VersionSourceLink[];
}

export async function getTextVersions(textId: number): Promise<TextVersionsResponse> {
  const { data } = await api.get<TextVersionsResponse>(`/texts/${textId}/versions`);
  return data;
}

// --- Work spine (FRBR Work witnesses) ---

/** 单个见证本（同一 FRBR Work 下的某一具体文本，可能跨语言/跨藏经）。 */
export interface WorkWitnessInfo {
  // 后端在 Work 接口返回纯数字 text_id，故不品牌化。
  text_id: number;
  cbeta_id: string;
  title: string | null;
  lang: string;
  canon: string | null;
  role: string;
  confidence: string;
  has_content: boolean;
}

/** GET /api/works/by-text/{text_id} 的响应：当前文本所属的 Work 及其全部见证本。 */
export interface WorkByText {
  slug: string;
  title_primary: string;
  title_sa: string | null;
  witness_count: number;
  witnesses: WorkWitnessInfo[];
}

/**
 * 取某文本所属 FRBR Work 及其全部见证本（跨语言/跨藏经的同一经的不同版本）。
 * 文本未挂任何 Work 时后端返回 404 —— 此处吞掉 404 返回 null，调用方据此不渲染。
 * 其他错误照常抛出。
 */
export async function getWorkByText(textId: number): Promise<WorkByText | null> {
  try {
    const { data } = await api.get<WorkByText>(`/works/by-text/${textId}`);
    return data;
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 404) {
      return null;
    }
    throw err;
  }
}

/** GET /api/works/{slug} 的响应：FRBR Work 详情（聚合元数据 + 见证本计数）。 */
export interface WorkDetail {
  id: number;
  slug: string;
  title_primary: string;
  title_sa: string | null;
  title_pi: string | null;
  sc_root_uid: string | null;
  toh_number: string | null;
  category: string | null;
  note: string | null;
  created_at: string;
  witness_count: number;
}

/** 取作品详情。404 时抛出（由调用方/路由处理）。 */
export async function getWork(slug: string): Promise<WorkDetail> {
  const { data } = await api.get<WorkDetail>(`/works/${encodeURIComponent(slug)}`);
  return data;
}

/** 取作品的全部见证本（root 优先，已富化标题/内容标志）。 */
export async function getWorkWitnesses(slug: string): Promise<WorkWitnessInfo[]> {
  const { data } = await api.get<WorkWitnessInfo[]>(
    `/works/${encodeURIComponent(slug)}/witnesses`,
  );
  return data;
}

// === V2 cross-canon AI difference analysis ===

export interface AiDiffChunkInput {
  text_id: number;
  juan_num: number;
  chunk_index: number;
  lang: string;
  text: string;
}

export interface AiDiffAnalysis {
  summary?: string;
  differences?: string[];
  doctrinal_notes?: string;
}

export interface AiDiffResponse {
  cached: boolean;
  prompt_version: string;
  model: string;
  analysis: AiDiffAnalysis;
}

export async function postAiDiff(chunks: AiDiffChunkInput[]): Promise<AiDiffResponse> {
  const { data } = await api.post<AiDiffResponse>("/alignment/ai-diff", { chunks });
  return data;
}

// --- Admin: cross-canon alignment coverage (ops view) ---

export interface AlignmentCoverageItem {
  text_id: number;
  title_zh: string;
  dynasty: string | null;
  pair_count: number;
  aligned_juans: number;
  total_juans: number;
  remaining_juans: number | null;
  coverage_pct: number | null;
  avg_confidence: number | null;
  partner_langs: string[];
}

export interface AlignmentCoverageResponse {
  items: AlignmentCoverageItem[];
  total: number;
}

export async function getAlignmentCoverage(
  limit = 200,
): Promise<AlignmentCoverageResponse> {
  const { data } = await api.get<AlignmentCoverageResponse>(
    "/admin/alignment-coverage",
    { params: { limit } },
  );
  return data;
}

// --- Admin: cross-canon alignment candidate review (flywheel) ---

export interface AlignmentCandidate {
  id: number;
  text_a_id: number;
  text_a_title: string | null;
  text_a_juan_num: number;
  text_a_lang: string;
  text_b_id: number;
  text_b_title: string | null;
  text_b_juan_num: number;
  text_b_lang: string;
  similarity: number;
  source: string;
  status: string;
}

export async function getAlignmentCandidates(
  limit = 50,
): Promise<AlignmentCandidate[]> {
  const { data } = await api.get<AlignmentCandidate[]>(
    "/admin/alignment-candidates",
    { params: { limit } },
  );
  return data;
}

export async function reviewAlignmentCandidate(
  id: number,
  accept: boolean,
): Promise<AlignmentCandidate> {
  const { data } = await api.post<AlignmentCandidate>(
    `/admin/alignment-candidates/${id}/review`,
    { accept },
  );
  return data;
}

// ── Buddhist master personas (祖师长廊) ───────────────────────────────────────

/** A representative line, quoted verbatim from a text FoJin hosts and checked
 *  against the master's OWN work. Null on the profile when our corpus holds none
 *  of the master's writing — we show that plainly rather than an unbacked line. */
export interface MasterEpigraph {
  quote: string;
  text_id: number;
  cbeta_id: string;
  title_zh: string;
  juan: number;
}

export interface MasterProfile {
  id: string;
  name_zh: string;
  name_en: string;
  tradition: string;
  dates: string;
  description: string;
  epigraph: MasterEpigraph | null;
}

export async function getMasters(): Promise<MasterProfile[]> {
  const { data } = await api.get<{ masters: MasterProfile[] }>("/chat/masters");
  return data.masters;
}
