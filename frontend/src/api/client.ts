import axios from "axios";
import { useAuthStore } from "../stores/authStore";
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
  is_active: boolean;
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
  properties: Record<string, any> | null;
  text_id: TextId | null;
  external_ids: Record<string, string> | null;
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

export async function getSearchSuggestions(q: string): Promise<string[]> {
  const { data } = await api.get<{ suggestions: string[] }>("/search/suggest", { params: { q } });
  return data.suggestions;
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

export async function getPendingSuggestionCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>("/source-suggestions/pending-count");
  return data.count;
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

export async function getPendingFeedbackCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>("/feedbacks/pending-count");
  return data.count;
}

// --- Admin Dashboard ---

export interface AdminOverview {
  total_users: number;
  new_users_today: number;
  total_sessions: number;
  new_sessions_today: number;
  total_messages: number;
  new_messages_today: number;
  pending_suggestions: number;
  pending_annotations: number;
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

export interface SimilarPassagesResponse {
  text_id: TextId;
  juan_num: number;
  passages: SimilarPassageItem[];
}

export async function getSimilarPassages(
  textId: number,
  juanNum: number,
  limit: number = 5,
  minScore: number = 0.7,
): Promise<SimilarPassagesResponse> {
  const { data } = await api.get<SimilarPassagesResponse>(
    `/texts/${textId}/juans/${juanNum}/similar`,
    { params: { limit, min_score: minScore } },
  );
  return data;
}

// --- Chat (AI Q&A) ---

export interface ChatSource {
  text_id: TextId;
  juan_num: number;
  chunk_text: string;
  score: number;
  title_zh?: string;
}

export interface ChatResponse {
  session_id: ChatSessionId;
  message: string;
  sources: ChatSource[];
}

export interface ChatSessionItem {
  id: ChatSessionId;
  title: string | null;
  created_at: string;
}

export interface ChatMessageItem {
  id: number;
  role: string;
  content: string;
  sources: ChatSource[] | null;
  feedback?: string | null;
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

export interface StreamCallbacks {
  onToken: (content: string) => void;
  onSources: (sources: ChatSource[]) => void;
  onSessionId: (sessionId: number) => void;
  onError: (message: string) => void;
  onDone: () => void;
}

export function sendChatMessageStream(
  message: string,
  sessionId: number | undefined,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
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
            case "session_id":
              callbacks.onSessionId(event.session_id);
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
          let detail = "发送失败，请稍后重试";
          try { detail = JSON.parse(xhr.responseText).detail || detail; } catch { /* ignore */ }
          callbacks.onError(detail);
        }
        callbacks.onDone();
        resolve();
      }
    };

    xhr.onerror = function () {
      if (!done) {
        callbacks.onError("网络错误，请稍后重试");
        callbacks.onDone();
        resolve();
      }
    };

    xhr.ontimeout = function () {
      if (!done) {
        callbacks.onError("请求超时，请稍后重试");
        callbacks.onDone();
        resolve();
      }
    };

    xhr.timeout = 90000;

    // AbortSignal support
    if (signal) {
      signal.addEventListener("abort", () => {
        xhr.abort();
        if (!done) {
          callbacks.onError("请求已取消");
          callbacks.onDone();
          resolve();
        }
      });
    }

    xhr.send(JSON.stringify({ message, session_id: sessionId ?? null }));
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
}): Promise<ApiKeyStatus> {
  const { data } = await api.put<ApiKeyStatus>("/auth/api-key", payload);
  return data;
}

export async function deleteApiKey(): Promise<void> {
  await api.delete("/auth/api-key");
}

export default api;
