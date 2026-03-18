import axios from "axios";
import { useAuthStore } from "../stores/authStore";

const api = axios.create({
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

export interface SearchHit {
  id: number;
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
}

export interface SearchResponse {
  total: number;
  page: number;
  size: number;
  results: SearchHit[];
}

export interface TextDetail {
  id: number;
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
  created_at: string;
}

export interface JuanInfo {
  juan_num: number;
  char_count: number;
}

export interface JuanListResponse {
  text_id: number;
  title_zh: string;
  total_juans: number;
  juans: JuanInfo[];
}

export interface JuanContentResponse {
  text_id: number;
  cbeta_id: string;
  title_zh: string;
  juan_num: number;
  total_juans: number;
  content: string;
  char_count: number;
  prev_juan: number | null;
  next_juan: number | null;
}

export interface MatchedJuan {
  juan_num: number;
  highlight: string[];
  score: number;
}

export interface ContentSearchHit {
  text_id: number;
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
  id: number;
  text_id: number;
  title_zh: string;
  cbeta_id: string;
  note: string | null;
  created_at: string;
}

export interface HistoryItem {
  id: number;
  text_id: number;
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
}

export interface TextIdentifierInfo {
  id: number;
  source_id: number;
  source_code: string;
  source_name: string;
  source_uid: string;
  source_url: string | null;
}

// --- Phase 2 Types ---

export interface SourceDistribution {
  id: number;
  source_id?: number;
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
  id: number;
  code: string;
  name_zh: string;
  name_en: string | null;
  base_url: string | null;
  description: string | null;
  access_type: "local" | "external" | "api";
  region: string | null;
  languages: string | null;
  supports_search: boolean;
  supports_fulltext: boolean;
  has_local_fulltext: boolean;
  has_remote_fulltext: boolean;
  supports_iiif: boolean;
  supports_api: boolean;
  is_active: boolean;
  distributions: SourceDistribution[];
}

export interface RelatedTextInfo {
  text_id: number;
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
  text_id: number;
  title_zh: string;
  relations: RelatedTextInfo[];
}

export interface ParallelTextContent {
  text_id: number;
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
  id: number;
  entity_type: string;
  name_zh: string;
  name_sa: string | null;
  name_pi: string | null;
  name_bo: string | null;
  name_en: string | null;
  description: string | null;
  properties: Record<string, any> | null;
  text_id: number | null;
  external_ids: Record<string, string> | null;
}

export interface EntityRelationItem {
  predicate: string;
  direction: string;
  target_id: number;
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
  id: number;
  name: string;
  entity_type: string;
  description: string | null;
}

export interface KGGraphLink {
  source: number;
  target: number;
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
  id: number;
  text_id: number;
  source_id: number;
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

// Reader APIs
export async function getJuanList(textId: number): Promise<JuanListResponse> {
  const { data } = await api.get<JuanListResponse>(`/texts/${textId}/juans`);
  return data;
}

export async function getJuanContent(textId: number, juanNum: number): Promise<JuanContentResponse> {
  const { data } = await api.get<JuanContentResponse>(`/texts/${textId}/juans/${juanNum}`);
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

// Dictionary
export interface DictEntry {
  id: number;
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

export async function searchDictionary(params: {
  q: string;
  page?: number;
  size?: number;
  lang?: string;
}): Promise<DictSearchResponse> {
  const { data } = await api.get<DictSearchResponse>("/dictionary/search", { params });
  return data;
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
  id: number;
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

export async function getPendingSuggestionCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>("/source-suggestions/pending-count");
  return data.count;
}

// --- Chat (AI Q&A) ---

export interface ChatSource {
  text_id: number;
  juan_num: number;
  chunk_text: string;
  score: number;
  title_zh?: string;
  source_type?: string;
}

export interface ChatResponse {
  session_id: number;
  message: string;
  sources: ChatSource[];
}

export interface ChatSessionItem {
  id: number;
  title: string | null;
  created_at: string;
}

export interface ChatMessageItem {
  id: number;
  role: string;
  content: string;
  sources: ChatSource[] | null;
  created_at: string;
}

export async function sendChatMessage(
  message: string,
  sessionId?: number,
): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>("/chat", {
    message,
    session_id: sessionId,
  }, { timeout: 90000 });
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

export interface StreamCallbacks {
  onToken: (content: string) => void;
  onSources: (sources: ChatSource[]) => void;
  onSessionId: (sessionId: number) => void;
  onError: (message: string) => void;
  onDone: () => void;
}

export async function sendChatMessageStream(
  message: string,
  sessionId: number | undefined,
  callbacks: StreamCallbacks,
): Promise<void> {
  try {
    const resp = await sendChatMessage(message, sessionId);
    callbacks.onSessionId(resp.session_id);
    if (resp.sources.length > 0) {
      callbacks.onSources(resp.sources);
    }
    // Typing animation — emit characters progressively for natural feel
    const text = resp.message;
    let i = 0;
    const emit = () => {
      if (i < text.length) {
        const chunk = text.slice(i, i + 1 + Math.floor(Math.random() * 2));
        callbacks.onToken(chunk);
        i += chunk.length;
        setTimeout(emit, 30 + Math.random() * 40);
      } else {
        callbacks.onDone();
      }
    };
    emit();
  } catch (err: any) {
    const detail = err?.response?.data?.detail || "发送失败，请稍后重试";
    callbacks.onError(detail);
    callbacks.onDone();
  }
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
}): Promise<ApiKeyStatus> {
  const { data } = await api.put<ApiKeyStatus>("/auth/api-key", payload);
  return data;
}

export async function deleteApiKey(): Promise<void> {
  await api.delete("/auth/api-key");
}

export default api;
