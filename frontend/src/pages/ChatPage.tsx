import { useState, useRef, useCallback, useMemo, useEffect, lazy, Suspense, type ReactNode } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Input, Button, Space, message, Alert, Tooltip, Modal, Select } from "antd";
import Markdown, { defaultUrlTransform } from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import * as OpenCC from "opencc-js";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  DeleteOutlined,
  PlusOutlined,
  SettingOutlined,
  MenuOutlined,
  DownloadOutlined,
  StopOutlined,
  CopyOutlined,
  ReloadOutlined,
  LikeOutlined,
  LikeFilled,
  DislikeOutlined,
  DislikeFilled,
  ShareAltOutlined,
} from "@ant-design/icons";
const ShareCard = lazy(() => import("../components/ShareCard"));
const CitationDrawer = lazy(() => import("../components/CitationDrawer"));
import type { CitationTarget } from "../components/CitationDrawer";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  sendChatMessageStream,
  getChatSessions,
  getChatSessionMessages,
  deleteChatSession,
  getApiKeyStatus,
  getChatQuota,
  getChunkContext,
  getHotQuestions,
  getRandomHotQuestions,
  updateChatMessageFeedback,
  type ChatMessageItem,
  type ChatSource,
  type ChatSessionItem,
  type HotQuestionCard,
  type HotQuestionCategory,
} from "../api/client";
import { useAuthStore } from "../stores/authStore";

/** Collapse loose markdown lists into tight lists by removing blank lines between list items. */
function tightenLists(md: string): string {
  // "1.\n\n内容" → "1. 内容" (编号独占一行后跟空行)
  return md.replace(/^(\d+\.)\s*\n\n+/gm, "$1 ")
    // "内容\n\n2." → "内容\n2." (列表项之间的空行)
    .replace(/\n\n+(?=\d+\.\s)/g, "\n");
}

const HOT_QUESTION_CATEGORY_SLUGS: Record<HotQuestionCategory, string> = {
  "白话翻译": "plain_translation",
  "经文解读": "scripture_exegesis",
  "对比辨析": "comparison",
  "佛教史话": "buddhist_history",
};

/** Extract [追问] follow-up suggestions from assistant message text. */
function parseFollowUps(content: string): { cleanContent: string; suggestions: string[] } {
  const lines = content.split("\n");
  const suggestions: string[] = [];
  const cleanLines: string[] = [];
  for (const line of lines) {
    const match = line.trim().match(/^\[追问]\s*(.+)/);
    if (match) {
      suggestions.push(match[1].trim());
    } else {
      cleanLines.push(line);
    }
  }
  // Remove trailing empty lines left after stripping suggestions
  const cleaned = cleanLines.join("\n").replace(/\n+$/, "");
  return { cleanContent: cleaned, suggestions };
}

const CITATION_URL_SCHEME = "fojin-citation";

// CBETA stores sutra titles in traditional Chinese; LLM answers come back in
// simplified Chinese whenever the user's question was simplified. Normalizing
// both sides to simplified via opencc-js lets injectCitationLinks actually
// find matches in the RAG source map.
const _t2s = OpenCC.Converter({ from: "tw", to: "cn" });
const toSimplified = (s: string): string => {
  try { return _t2s(s); } catch { return s; }
};

// rehype-sanitize's defaultSchema strips any <a href> whose protocol is not
// in its allowlist (http, https, mailto, tel, …). We add our custom citation
// scheme so the citation-drawer machinery below can intercept it instead of
// seeing href=undefined on every click.
const CHAT_SANITIZE_SCHEMA = {
  ...defaultSchema,
  protocols: {
    ...(defaultSchema.protocols ?? {}),
    href: [...(defaultSchema.protocols?.href ?? []), CITATION_URL_SCHEME],
  },
};

// react-markdown runs its own urlTransform before rehype plugins run; the
// built-in one rewrites any non-(http|https|mailto|…) URL to an empty string,
// which would nuke our fojin-citation:// scheme even before rehype-sanitize
// gets a chance to allow it. Pass through our scheme explicitly and delegate
// to the default for everything else.
const chatUrlTransform = (url: string): string => {
  if (url.startsWith(`${CITATION_URL_SCHEME}:`)) return url;
  return defaultUrlTransform(url);
};

/**
 * Turn sutra references inside an AI answer into citation-drawer buttons.
 *
 * The LLM is wildly inconsistent about citation style — sometimes it emits the
 * explicit 【《心经》第1卷】 marker, sometimes it just drops 《佛说无量寿经》
 * inline as prose. We handle both:
 *
 *  1. First pass rewrites 【《title》第N卷】 into a markdown link pointing at
 *     our custom `fojin-citation://{text_id}/{juan_num}/{chunk_index}` URL.
 *  2. Second pass scans the remaining plaintext for bare 《title》 occurrences
 *     and wraps them when `title` is in the RAG source map. Existing markdown
 *     links from pass 1 are skipped so we never double-wrap.
 *
 * When a matched source lacks chunk_index (legacy chat history from before
 * the chunk_index field was wired through) we emit chunk_index=-1; the click
 * handler in the renderer falls back to reader-page navigation in that case.
 */
function injectCitationLinks(content: string, sources: ChatSource[] | null): string {
  if (!sources || sources.length === 0) return content;

  // Key on the simplified form so titles coming back from CBETA in
  // traditional characters can be matched against simplified-Chinese
  // answer text. Multiple traditional sources that collapse to the same
  // simplified key keep the highest-scoring one.
  const titleMap = new Map<string, ChatSource>();
  for (const s of sources) {
    if (!s.title_zh || s.text_id <= 0) continue;
    const key = toSimplified(s.title_zh);
    const existing = titleMap.get(key);
    if (!existing || s.score > existing.score) {
      titleMap.set(key, s);
    }
  }
  if (titleMap.size === 0) return content;

  const buildUrl = (source: ChatSource, title: string, juan: number): string => {
    const chunkIdx = source.chunk_index ?? -1;
    return `${CITATION_URL_SCHEME}://${source.text_id}/${juan}/${chunkIdx}/${encodeURIComponent(title)}`;
  };

  // Pass 1 — explicit 【《title》…】 markers. Previously the tail was locked to
  // "第(\d+)卷", which dropped perfectly-valid variants like "卷上" or
  // "第十八愿" on the floor. Now we accept any qualifier up to the close
  // bracket and only parse a juan number out of it when we can.
  let withExplicit = content.replace(
    /【《([^》]+)》([^】]*)】/g,
    (_match, rawTitle: string, tail: string) => {
      const title = rawTitle.trim();
      const simplifiedTitle = toSimplified(title);
      const source = titleMap.get(simplifiedTitle);
      if (!source) return _match;
      const juanMatch = tail.match(/第(\d+)卷/);
      const juan = juanMatch ? parseInt(juanMatch[1], 10) : source.juan_num;
      const url = buildUrl(source, simplifiedTitle, juan);
      const labelTail = tail ? tail : "";
      return `[【《${title}》${labelTail}】](${url})`;
    },
  );

  // Pass 2 — bare 《title》 in prose. Split on any markdown links already in
  // the content (the ones pass 1 just produced, plus any pre-existing links)
  // so we only process plaintext segments. Split with a capture group: JS
  // interleaves the matches into the output array, so odd indices are the
  // preserved link strings and even indices are plaintext we can rewrite.
  const parts = withExplicit.split(/(\[[^\]]*\]\([^)]*\))/g);
  withExplicit = parts
    .map((part, i) => {
      if (i % 2 === 1) return part; // preserved markdown link
      return part.replace(/《([^》]+)》/g, (bareMatch, rawTitle: string) => {
        const title = rawTitle.trim();
        const simplifiedTitle = toSimplified(title);
        const source = titleMap.get(simplifiedTitle);
        if (!source) return bareMatch;
        const url = buildUrl(source, simplifiedTitle, source.juan_num);
        return `[《${title}》](${url})`;
      });
    })
    .join("");

  return withExplicit;
}

interface ParsedCitation {
  textId: number;
  juanNum: number;
  chunkIndex: number;
  titleZh: string;
}

function parseCitationHref(href: string): ParsedCitation | null {
  if (!href.startsWith(`${CITATION_URL_SCHEME}://`)) return null;
  const rest = href.slice(`${CITATION_URL_SCHEME}://`.length);
  const parts = rest.split("/");
  if (parts.length < 3) return null;
  const textId = parseInt(parts[0], 10);
  const juanNum = parseInt(parts[1], 10);
  const chunkIndex = parseInt(parts[2], 10);
  const titleZh = parts[3] ? decodeURIComponent(parts[3]) : "";
  if (!Number.isFinite(textId) || !Number.isFinite(juanNum) || !Number.isFinite(chunkIndex)) {
    return null;
  }
  return { textId, juanNum, chunkIndex, titleZh };
}

function groupSessionsByDate(sessions: ChatSessionItem[]): { label: string; items: ChatSessionItem[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: Record<string, ChatSessionItem[]> = { today: [], yesterday: [], week: [], older: [] };
  for (const s of sessions) {
    const d = new Date(s.created_at);
    if (d >= today) groups.today.push(s);
    else if (d >= yesterday) groups.yesterday.push(s);
    else if (d >= weekAgo) groups.week.push(s);
    else groups.older.push(s);
  }

  const result: { label: string; items: ChatSessionItem[] }[] = [];
  if (groups.today.length) result.push({ label: "今天", items: groups.today });
  if (groups.yesterday.length) result.push({ label: "昨天", items: groups.yesterday });
  if (groups.week.length) result.push({ label: "本周", items: groups.week });
  if (groups.older.length) result.push({ label: "更早", items: groups.older });
  return result;
}

export default function ChatPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { user } = useAuthStore();
  const [input, setInput] = useState("");
  const [masterId, setMasterId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sessionFilter, setSessionFilter] = useState("");
  const tabIndexRef = useRef(-1);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [shareTarget, setShareTarget] = useState<{
    question: string;
    answer: string;
    sources: ChatSource[] | null;
  } | null>(null);
  const [citationTarget, setCitationTarget] = useState<CitationTarget | null>(null);
  const [citationPanelWidth, setCitationPanelWidth] = useState<number>(() => {
    try {
      const saved = localStorage.getItem("fojin-citation-panel-width");
      const n = saved ? parseInt(saved, 10) : NaN;
      return Number.isFinite(n) && n >= 360 && n <= 900 ? n : 560;
    } catch {
      return 560;
    }
  });
  const citationDragRef = useRef(false);
  const handleCitationDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    citationDragRef.current = true;
    const startX = e.clientX;
    const startWidth = citationPanelWidth;
    const onMove = (ev: MouseEvent) => {
      if (!citationDragRef.current) return;
      const delta = startX - ev.clientX;
      const next = Math.max(360, Math.min(startWidth + delta, 900));
      setCitationPanelWidth(next);
    };
    const onUp = () => {
      citationDragRef.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      try {
        localStorage.setItem("fojin-citation-panel-width", String(citationPanelWidth));
      } catch { /* ignore */ }
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [citationPanelWidth]);
  // Persist width after state settles (separate effect so latest value is saved)
  useEffect(() => {
    try { localStorage.setItem("fojin-citation-panel-width", String(citationPanelWidth)); } catch { /* ignore */ }
  }, [citationPanelWidth]);
  const queryClient = useQueryClient();
  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesTopRef = useRef<HTMLDivElement>(null);

  const { data: sessions, refetch: refetchSessions } = useQuery({
    queryKey: ["chatSessions"],
    queryFn: getChatSessions,
    enabled: !!user,
  });

  const { data: hotQuestionsData } = useQuery({
    queryKey: ["hotQuestions"],
    queryFn: getHotQuestions,
    staleTime: 3600_000,
  });

  // Welcome-screen categorized cards: fetched fresh each mount, with
  // localStorage-backed FIFO exclusion so users don't see the same four
  // questions when they refresh the page or hit "换一批".
  const SEEN_STORAGE_KEY = "fojin-hot-questions-seen";
  const SEEN_CAP = 40;
  const readSeenIds = useCallback((): number[] => {
    try {
      const raw = localStorage.getItem(SEEN_STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter((n) => typeof n === "number") : [];
    } catch { return []; }
  }, []);
  const pushSeenIds = useCallback((ids: number[]) => {
    if (!ids.length) return;
    try {
      const current = readSeenIds();
      const next = [...current, ...ids].slice(-SEEN_CAP);
      localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify(next));
    } catch { /* ignore storage errors */ }
  }, [readSeenIds]);

  const { data: welcomeCardsData, refetch: refetchWelcomeCards, isFetching: welcomeCardsLoading } = useQuery({
    queryKey: ["hotQuestionCards"],
    queryFn: () => getRandomHotQuestions(readSeenIds()),
    staleTime: 0,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (welcomeCardsData?.questions?.length) {
      pushSeenIds(welcomeCardsData.questions.map((q) => q.id));
    }
  }, [welcomeCardsData, pushSeenIds]);

  const { data: keyStatus } = useQuery({
    queryKey: ["apiKeyStatus"],
    queryFn: getApiKeyStatus,
    enabled: !!user,
  });

  const { data: quota, refetch: refetchQuota } = useQuery({
    queryKey: ["chatQuota"],
    queryFn: getChatQuota,
  });

  const filteredSessions = useMemo(
    () => sessions?.filter((s) => !sessionFilter || (s.title || "").includes(sessionFilter)),
    [sessions, sessionFilter],
  );
  const groupedSessions = useMemo(
    () => groupSessionsByDate(filteredSessions ?? []),
    [filteredSessions],
  );

  // Custom markdown components: intercept `fojin-citation://` scheme to
  // open the citation drawer, render `/texts/...` links via react-router,
  // and treat everything else as an external link.
  const markdownComponents = useMemo(() => ({
    a: ({ href, children }: { href?: string; children?: ReactNode }) => {
      if (href) {
        const parsed = parseCitationHref(href);
        if (parsed) {
          return (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                if (parsed.chunkIndex < 0) {
                  // Legacy history message without chunk_index — fall back
                  // to navigating to the reader page as before.
                  navigate(`/texts/${parsed.textId}/read?juan=${parsed.juanNum}`);
                  return;
                }
                setCitationTarget(parsed);
              }}
              style={{
                background: "none",
                border: 0,
                padding: 0,
                font: "inherit",
                color: "var(--fj-accent)",
                borderBottom: "1px dashed var(--fj-accent)",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              {children}
            </button>
          );
        }
      }
      if (href && href.startsWith("/texts/")) {
        return (
          <Link
            to={href}
            style={{
              color: "var(--fj-accent)",
              textDecoration: "none",
              borderBottom: "1px dashed var(--fj-accent)",
              fontWeight: 500,
            }}
          >
            {children}
          </Link>
        );
      }
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
  }), [navigate]);

  const scrollToBottom = () => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
  };

  const loadSession = async (sid: number) => {
    try {
      const data = await getChatSessionMessages(sid, 1, 50);
      setSessionId(sid);
      setMessages(data.messages);
      setCurrentPage(1);
      setHasOlderMessages(data.total > data.messages.length);
      // 加载历史会话时滚到顶部，让用户先看到问题
      setTimeout(() => messagesTopRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch {
      message.error("加载会话失败");
    }
  };

  const loadOlderMessages = async () => {
    if (!sessionId || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const nextPage = currentPage + 1;
      const data = await getChatSessionMessages(sessionId, nextPage, 50);
      setMessages((prev) => [...data.messages, ...prev]);
      setCurrentPage(nextPage);
      setHasOlderMessages(nextPage * 50 < data.total);
    } catch {
      message.error("加载历史消息失败");
    } finally {
      setLoadingOlder(false);
    }
  };

  const handleNewChat = () => {
    setSessionId(undefined);
    setMessages([]);
    setHasOlderMessages(false);
    setCurrentPage(1);
  };

  const handleDeleteSession = (sid: number) => {
    Modal.confirm({
      title: "删除会话",
      content: "删除后无法恢复，确定要删除这个会话吗？",
      okText: "删除",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteChatSession(sid);
          if (sessionId === sid) handleNewChat();
          refetchSessions();
        } catch {
          message.error("删除失败");
        }
      },
    });
  };

  const streamingIdRef = useRef<number>(0);
  const abortRef = useRef<AbortController | null>(null);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const handleSendMessage = useCallback(async (
    text: string,
    options?: { hotQuestionId?: number | null },
  ) => {
    const msg = text.trim();
    if (!msg || sending) return;
    const hotQuestionId = options?.hotQuestionId ?? null;

    // Umami: track chat question (truncated to 30 chars for privacy)
    if (typeof umami !== "undefined") {
      umami.track("chat", { question: msg.slice(0, 30) });
    }

    const userMsg: ChatMessageItem = {
      id: Date.now(),
      role: "user",
      content: msg,
      sources: null,
      created_at: new Date().toISOString(),
    };

    const assistantId = Date.now() + 1;
    streamingIdRef.current = assistantId;
    const assistantMsg: ChatMessageItem = {
      id: assistantId,
      role: "assistant",
      content: "正在检索经文并生成回答...",
      sources: null,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setSending(true);
    scrollToBottom();

    const abortController = new AbortController();
    abortRef.current = abortController;

    // Auto-timeout after 90 seconds
    const timeoutId = setTimeout(() => abortController.abort(), 90_000);

    await sendChatMessageStream(msg, sessionId, masterId, {
      onToken: (content: string) => {
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId) return m;
            const current = m.content === "正在检索经文并生成回答..." ? "" : m.content;
            return { ...m, content: current + content };
          }),
        );
        scrollToBottom();
      },
      onSources: (sources: ChatSource[]) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, sources } : m,
          ),
        );
        // Prefetch each citation's chunk context so the drawer opens instantly.
        for (const s of sources) {
          if (s.text_id == null || s.juan_num == null || s.chunk_index == null) continue;
          if (s.chunk_index < 0) continue;
          queryClient.prefetchQuery({
            queryKey: ["citation-context", s.text_id, s.juan_num, s.chunk_index],
            queryFn: () => getChunkContext(s.text_id, s.juan_num, s.chunk_index ?? 0, 2),
            staleTime: 15 * 60 * 1000,
          });
        }
      },
      onSearching: (_searchMsg: string) => {
        // 搜索状态由初始占位符 "正在检索经文并生成回答..." 显示，不覆盖 content
      },
      onSessionId: (newSessionId: number) => {
        if (!sessionId) {
          setSessionId(newSessionId);
          if (user) refetchSessions();
        }
      },
      onError: (errMsg: string) => {
        message.error(errMsg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.content === "正在检索经文并生成回答..."
              ? { ...m, content: "请求失败，请重试" }
              : m,
          ),
        );
      },
      onDone: () => {
        clearTimeout(timeoutId);
        abortRef.current = null;
        streamingIdRef.current = 0;
        setSending(false);
        refetchQuota();
      },
    }, abortController.signal, undefined, hotQuestionId);
  }, [sending, sessionId, masterId, user, refetchSessions, refetchQuota, queryClient]);

  const handleSend = useCallback(async () => {
    await handleSendMessage(input);
  }, [input, handleSendMessage]);

  // Tab key: cycle through suggested questions when input is empty
  const tabSuggestions = useMemo(() => {
    // Prefer follow-up suggestions from the last assistant message
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") {
        const { suggestions } = parseFollowUps(messages[i].content);
        if (suggestions.length > 0) return suggestions;
        break;
      }
    }
    // Fallback to hot questions (same defaults as the welcome card)
    return hotQuestionsData?.questions ?? (t("chat.hot_questions", { returnObjects: true }) as string[]);
  }, [messages, hotQuestionsData, t]);

  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // Attach native keydown listener to capture Tab before Ant Design / browser handles it
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || tabSuggestions.length === 0) return;
      const val = (e.target as HTMLTextAreaElement).value || "";
      if (val && !tabSuggestions.includes(val)) return;
      e.preventDefault();
      e.stopPropagation();
      const nextIndex = (tabIndexRef.current + 1) % tabSuggestions.length;
      tabIndexRef.current = nextIndex;
      setInput(tabSuggestions[nextIndex]);
    };
    el.addEventListener("keydown", handler);
    return () => el.removeEventListener("keydown", handler);
  }, [tabSuggestions]);

  // Handle pre-filled message from URL params (e.g. from "Ask XiaoJin" button on reader page)
  const [searchParams, setSearchParams] = useSearchParams();
  const autoSentRef = useRef(false);
  useEffect(() => {
    const q = searchParams.get("q");
    const context = searchParams.get("context");
    const source = searchParams.get("source");
    if (!q || !context || autoSentRef.current) return;

    autoSentRef.current = true;
    setSearchParams({}, { replace: true });

    const msg = source
      ? `关于《${source}》中的这段经文：\n\n> ${context}\n\n${q}`
      : `关于这段经文：\n\n> ${context}\n\n${q}`;
    handleSendMessage(msg);
  }, [searchParams, setSearchParams, handleSendMessage]);

  const handleExport = useCallback(() => {
    if (messages.length === 0) {
      message.warning("暂无对话内容可导出");
      return;
    }
    const sessionTitle = sessions?.find((s) => s.id === sessionId)?.title || t("chat.new_chat");
    const now = new Date().toLocaleString("zh-CN");
    let md = `# ${sessionTitle}\n导出时间: ${now}\n\n`;
    for (const m of messages) {
      if (m.role === "user") {
        md += `## 用户\n${m.content}\n\n`;
      } else {
        const { cleanContent } = parseFollowUps(m.content);
        md += `## AI 助手\n${cleanContent}\n\n`;
        if (m.sources && m.sources.length > 0) {
          md += "**引用来源:**\n";
          for (const s of m.sources) {
            const title = s.title_zh ? `《${s.title_zh}》第${s.juan_num}卷` : `文本#${s.text_id} 第${s.juan_num}卷`;
            md += `- 📖 ${title} (${Math.round(s.score * 100)}%)\n`;
          }
          md += "\n";
        }
      }
    }
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sessionTitle}-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [messages, sessions, sessionId, t]);

  return (
    <>
      <Helmet><title>{t("chat.page_title")}</title></Helmet>
      <div style={{
        display: "flex",
        height: "calc(100vh - 120px)",
        maxWidth: citationTarget ? undefined : 1100,
        margin: citationTarget ? "0 16px" : "0 auto",
        gap: 16,
      }}>

        {/* Mobile sidebar drawer (logged in only) */}
        {user && sidebarOpen && (
          <>
            <div className="chat-sidebar-overlay" onClick={() => setSidebarOpen(false)} />
            <div className="chat-sidebar-drawer">
              <Button icon={<PlusOutlined />} block onClick={() => { handleNewChat(); setSidebarOpen(false); }}>{t("chat.new_chat")}</Button>
              <Button icon={<SettingOutlined />} block type="text" size="small"
                style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                onClick={() => { navigate("/profile?tab=apikey"); setSidebarOpen(false); }}>
                {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
              </Button>
              <div style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
                {groupedSessions.map((group) => (
                  <div key={group.label}>
                    <div style={{ fontSize: 11, color: "var(--fj-ink-muted)", opacity: 0.6, padding: "6px 12px 2px", fontWeight: 500 }}>
                      {group.label}
                    </div>
                    {group.items.map((s) => (
                      <div key={s.id}
                        style={{
                          padding: "8px 12px", borderRadius: 6, cursor: "pointer", fontSize: 13,
                          color: sessionId === s.id ? "var(--fj-accent)" : "var(--fj-ink-muted)",
                          background: sessionId === s.id ? "rgba(217,208,193,0.3)" : "transparent",
                          display: "flex", justifyContent: "space-between", alignItems: "center",
                        }}
                        onClick={() => { loadSession(s.id); setSidebarOpen(false); }}
                      >
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                          {s.title || t("chat.new_chat")}
                        </span>
                        <DeleteOutlined
                          style={{ fontSize: 11, color: "var(--fj-ink-muted)", marginLeft: 4 }}
                          onClick={(e) => { e.stopPropagation(); handleDeleteSession(s.id); }}
                        />
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {/* Sidebar (desktop, logged in only) */}
        {user && <div style={{ width: 220, flexShrink: 0, display: "flex", flexDirection: "column", gap: 8 }}
             className="chat-sidebar">
          <Button icon={<PlusOutlined />} block onClick={handleNewChat}>{t("chat.new_chat")}</Button>
          <Button icon={<SettingOutlined />} block type="text" size="small"
            style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
            onClick={() => navigate("/profile?tab=apikey")}>
            {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
          </Button>
          {sessions && sessions.length > 5 && (
            <Input
              placeholder="搜索会话..."
              size="small"
              allowClear
              value={sessionFilter}
              onChange={(e) => setSessionFilter(e.target.value)}
              style={{ marginTop: 4, fontSize: 12 }}
            />
          )}
          <div style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
            {groupedSessions.map((group) => (
              <div key={group.label}>
                <div style={{ fontSize: 11, color: "var(--fj-ink-muted)", opacity: 0.6, padding: "6px 12px 2px", fontWeight: 500 }}>
                  {group.label}
                </div>
                {group.items.map((s) => (
                  <div key={s.id}
                    style={{
                      padding: "8px 12px",
                      borderRadius: 6,
                      cursor: "pointer",
                      fontSize: 13,
                      color: sessionId === s.id ? "var(--fj-accent)" : "var(--fj-ink-muted)",
                      background: sessionId === s.id ? "rgba(217,208,193,0.3)" : "transparent",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                    onClick={() => loadSession(s.id)}
                  >
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                      {s.title || t("chat.new_chat")}
                    </span>
                    <DeleteOutlined
                      style={{ fontSize: 11, color: "var(--fj-ink-muted)", marginLeft: 4 }}
                      onClick={(e) => { e.stopPropagation(); handleDeleteSession(s.id); }}
                    />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>}

        {/* Chat area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* Chat header: mobile toggle + export */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            {user ? (
              <Button
                className="chat-mobile-toggle"
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setSidebarOpen(true)}
              >
                会话列表
              </Button>
            ) : <div />}
            {messages.length > 0 && (
              <Tooltip title="导出对话为 Markdown">
                <Button
                  type="text"
                  icon={<DownloadOutlined />}
                  onClick={handleExport}
                  style={{ color: "var(--fj-ink-muted)" }}
                />
              </Tooltip>
            )}
          </div>
          {/* Messages */}
          <div style={{ flex: 1, overflow: "auto", padding: "16px 0" }}>
            <div ref={messagesTopRef} />
            {hasOlderMessages && (
              <div style={{ textAlign: "center", marginBottom: 12 }}>
                <Button size="small" type="text" loading={loadingOlder} onClick={loadOlderMessages}
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}>
                  {t("chat.load_older")}
                </Button>
              </div>
            )}
            {messages.length === 0 && (
              <div style={{ textAlign: "center", padding: "60px 24px", color: "var(--fj-ink-muted)" }}>
                <RobotOutlined style={{ fontSize: 48, marginBottom: 16, color: "var(--fj-accent)" }} />
                <div style={{ fontSize: 18, fontFamily: '"Noto Serif SC", serif', marginBottom: 8 }}>
                  {t("chat.title")}
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                  {t("chat.subtitle")}
                  <br />{t("chat.subtitle2")}
                </div>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 10,
                  marginTop: 24,
                  maxWidth: 480,
                  marginLeft: "auto",
                  marginRight: "auto",
                }}>
                  {(welcomeCardsData?.questions ?? []).map((card: HotQuestionCard) => (
                    <div
                      key={card.id}
                      onClick={() => handleSendMessage(card.display_text, { hotQuestionId: card.id })}
                      style={{
                        padding: "12px 14px 10px",
                        borderRadius: 8,
                        border: "1px solid rgba(217,208,193,0.6)",
                        fontSize: 13,
                        cursor: "pointer",
                        lineHeight: 1.6,
                        transition: "all 0.2s",
                        color: "var(--fj-ink-muted)",
                        textAlign: "left",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-start",
                        gap: 6,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = "var(--fj-accent)";
                        e.currentTarget.style.color = "var(--fj-accent)";
                        e.currentTarget.style.background = "rgba(176,141,87,0.06)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = "rgba(217,208,193,0.6)";
                        e.currentTarget.style.color = "var(--fj-ink-muted)";
                        e.currentTarget.style.background = "transparent";
                      }}
                    >
                      <span style={{
                        fontSize: 11,
                        padding: "2px 8px",
                        borderRadius: 10,
                        background: "rgba(176,141,87,0.1)",
                        color: "var(--fj-accent)",
                        fontFamily: '"Noto Serif SC", serif',
                        letterSpacing: "0.02em",
                      }}>
                        {t(`chat.hot_question_category_${HOT_QUESTION_CATEGORY_SLUGS[card.category]}`, card.category)}
                      </span>
                      <span>{card.display_text}</span>
                    </div>
                  ))}
                </div>
                {(welcomeCardsData?.questions?.length ?? 0) > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <Button
                      size="small"
                      type="text"
                      icon={<ReloadOutlined />}
                      loading={welcomeCardsLoading}
                      onClick={() => refetchWelcomeCards()}
                      style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                    >
                      {t("chat.refresh_hot_questions", "换一批")}
                    </Button>
                  </div>
                )}
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} style={{
                display: "flex",
                gap: 12,
                marginBottom: 16,
                padding: "0 16px",
                flexDirection: m.role === "user" ? "row-reverse" : "row",
              }}>
                <div style={{
                  width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: m.role === "user" ? "var(--fj-accent)" : "rgba(217,208,193,0.5)",
                  color: m.role === "user" ? "#fff" : "var(--fj-ink)",
                  fontSize: 14,
                }}>
                  {m.role === "user" ? <UserOutlined /> : <RobotOutlined />}
                </div>
                <div style={{ maxWidth: "75%", display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{
                  padding: "10px 16px",
                  borderRadius: 12,
                  background: m.role === "user" ? "var(--fj-accent)" : "rgba(217,208,193,0.2)",
                  color: m.role === "user" ? "#fff" : "var(--fj-ink)",
                  fontSize: 14,
                  lineHeight: 1.8,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}>
                  {m.role === "assistant" ? (
                    m.content === "正在检索经文并生成回答..." ? (
                      <div className="chat-thinking">
                        正在检索经文并生成回答
                        <span className="chat-thinking-dots"><span /><span /><span /></span>
                      </div>
                    ) : (() => {
                      const isStreaming = streamingIdRef.current === m.id;
                      const { cleanContent, suggestions } = isStreaming
                        ? { cleanContent: m.content, suggestions: [] }
                        : parseFollowUps(m.content);
                      return (
                        <>
                          <div className="chat-markdown">
                            <Markdown rehypePlugins={[[rehypeSanitize, CHAT_SANITIZE_SCHEMA]]} urlTransform={chatUrlTransform} components={markdownComponents}>{tightenLists(injectCitationLinks(cleanContent, m.sources)) + (isStreaming ? " ▌" : "")}</Markdown>
                          </div>
                          {suggestions.length > 0 && !sending && (
                            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
                              {suggestions.map((q, i) => (
                                <span
                                  key={i}
                                  onClick={() => handleSendMessage(q)}
                                  style={{
                                    display: "inline-block",
                                    padding: "4px 12px",
                                    borderRadius: 14,
                                    border: "1px solid var(--fj-gold, #b08d57)",
                                    color: "var(--fj-gold, #b08d57)",
                                    fontSize: 12,
                                    cursor: "pointer",
                                    background: "transparent",
                                    transition: "all 0.2s",
                                    lineHeight: 1.6,
                                  }}
                                  onMouseEnter={(e) => {
                                    e.currentTarget.style.background = "rgba(176,141,87,0.1)";
                                    e.currentTarget.style.color = "var(--fj-accent)";
                                    e.currentTarget.style.borderColor = "var(--fj-accent)";
                                  }}
                                  onMouseLeave={(e) => {
                                    e.currentTarget.style.background = "transparent";
                                    e.currentTarget.style.color = "var(--fj-gold, #b08d57)";
                                    e.currentTarget.style.borderColor = "var(--fj-gold, #b08d57)";
                                  }}
                                >
                                  {q}
                                </span>
                              ))}
                            </div>
                          )}
                        </>
                      );
                    })()
                  ) : (
                    m.content
                  )}
                </div>
                {/* Action buttons outside bubble */}
                {m.content !== "正在检索经文并生成回答..." && streamingIdRef.current !== m.id && (
                  <div style={{ marginTop: 4, display: "flex", gap: 4 }}>
                    <Tooltip title="复制">
                      <Button
                        type="text" size="small" icon={<CopyOutlined />}
                        style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                        onClick={() => {
                          const textToCopy = m.role === "assistant"
                            ? parseFollowUps(m.content).cleanContent
                            : m.content;
                          navigator.clipboard.writeText(textToCopy);
                          message.success("已复制");
                        }}
                      />
                    </Tooltip>
                      {m.role === "assistant" && m.content !== "请求失败，请重试" && (
                        <Tooltip title="生成分享卡片">
                          <Button
                            type="text" size="small" icon={<ShareAltOutlined />}
                            style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                            onClick={() => {
                              const idx = messages.findIndex((x) => x.id === m.id);
                              let question = "";
                              for (let i = idx - 1; i >= 0; i--) {
                                if (messages[i].role === "user") {
                                  question = messages[i].content;
                                  break;
                                }
                              }
                              setShareTarget({
                                question: question || "佛典问答",
                                answer: parseFollowUps(m.content).cleanContent,
                                sources: m.sources,
                              });
                            }}
                          />
                        </Tooltip>
                      )}
                      {m.role === "assistant" && user && (
                        <>
                          <Tooltip title="有帮助">
                            <Button
                              type="text" size="small"
                              icon={m.feedback === "up" ? <LikeFilled /> : <LikeOutlined />}
                              style={{ color: m.feedback === "up" ? "var(--fj-accent)" : "var(--fj-ink-muted)", fontSize: 12 }}
                              onClick={() => {
                                const newFeedback = m.feedback === "up" ? null : "up";
                                setMessages((prev) => prev.map((x) => x.id === m.id ? { ...x, feedback: newFeedback } : x));
                                updateChatMessageFeedback(m.id, newFeedback as "up" | "down" | null).catch(() => {
                                  setMessages((prev) => prev.map((x) => x.id === m.id ? { ...x, feedback: m.feedback } : x));
                                });
                              }}
                            />
                          </Tooltip>
                          <Tooltip title="没帮助">
                            <Button
                              type="text" size="small"
                              icon={m.feedback === "down" ? <DislikeFilled /> : <DislikeOutlined />}
                              style={{ color: m.feedback === "down" ? "#e74c3c" : "var(--fj-ink-muted)", fontSize: 12 }}
                              onClick={() => {
                                const newFeedback = m.feedback === "down" ? null : "down";
                                setMessages((prev) => prev.map((x) => x.id === m.id ? { ...x, feedback: newFeedback } : x));
                                updateChatMessageFeedback(m.id, newFeedback as "up" | "down" | null).catch(() => {
                                  setMessages((prev) => prev.map((x) => x.id === m.id ? { ...x, feedback: m.feedback } : x));
                                });
                              }}
                            />
                          </Tooltip>
                        </>
                      )}
                      {m.role === "assistant" && m.content === "请求失败，请重试" && (
                        <Tooltip title="重试">
                          <Button
                            type="text" size="small" icon={<ReloadOutlined />}
                            style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                            onClick={() => {
                              const idx = messages.findIndex((x) => x.id === m.id);
                              const userMsg = idx > 0 ? messages[idx - 1] : null;
                              if (userMsg && userMsg.role === "user") {
                                setMessages((prev) => prev.filter((x) => x.id !== m.id && x.id !== userMsg.id));
                                handleSendMessage(userMsg.content);
                              }
                            }}
                          />
                        </Tooltip>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {/* Streaming cursor is shown inline via ▌ in the message bubble */}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{ padding: "12px 0", borderTop: "1px solid rgba(217,208,193,0.5)" }}>
            <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, color: "#8b7355", whiteSpace: "nowrap" }}>{t("chat.master_mode")}</span>
              <Select
                allowClear
                placeholder={t("chat.general_assistant")}
                value={masterId}
                onChange={(v) => setMasterId(v || null)}
                style={{ width: 200, fontSize: 13 }}
                size="small"
                options={[
                  { value: "", label: `🟢 ${t("chat.general_assistant")}` },
                  { value: "zhiyi", label: "🪷 智顗（天台宗）" },
                  { value: "huineng", label: "🪷 慧能（禅宗）" },
                  { value: "xuanzang", label: "🪷 玄奘（唯识宗）" },
                  { value: "fazang", label: "🪷 法藏（华严宗）" },
                  { value: "kumarajiva", label: "🪷 鸠摩罗什（中观）" },
                  { value: "yinguang", label: "🪷 印光（净土宗）" },
                  { value: "ouyi", label: "🪷 蕅益（跨宗派）" },
                  { value: "xuyun", label: "🪷 虚云（禅宗）" },
                ]}
              />
              {masterId && <span style={{ fontSize: 11, color: "#a09070" }}>{t("chat.rag_scope_hint")}</span>}
            </div>
            {!user && !keyStatus?.has_api_key && quota && quota.remaining >= 0 && (
              <Alert
                message={<span>{t("chat.quota_info", { limit: quota.limit, remaining: quota.remaining })}<a onClick={() => navigate("/login")}>{t("chat.login")}</a>{t("chat.login_quota_hint")}</span>}
                type={quota.remaining <= 2 ? "warning" : "info"} showIcon closable
                style={{ marginBottom: 8, fontSize: 12 }}
              />
            )}
            <Space.Compact style={{ width: "100%", alignItems: "stretch" }}>
              <Input.TextArea
                ref={(instance) => { inputRef.current = instance?.resizableTextArea?.textArea ?? null; }}
                value={input}
                onChange={(e) => { setInput(e.target.value); tabIndexRef.current = -1; }}
                onPressEnter={(e) => {
                  if (e.shiftKey) return;
                  e.preventDefault();
                  handleSend();
                }}
                placeholder={tabSuggestions.length > 0 ? `${tabSuggestions[(tabIndexRef.current + 1) % tabSuggestions.length]}    ⇥ Tab    ⇧⏎ 换行` : t("chat.input_placeholder")}
                disabled={sending}
                autoSize={{ minRows: 1, maxRows: 6 }}
                style={{ fontFamily: '"Noto Serif SC", serif', fontSize: 16, resize: "none" }}
              />
              {sending ? (
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={handleCancel}
                  size="large"
                >
                  {t("chat.stop")}
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={handleSend}
                  size="large"
                  style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}
                />
              )}
            </Space.Compact>
          </div>
        </div>

        {/* Citation drawer — inline side panel, drag to resize */}
        {citationTarget !== null && (
          <>
            <div className="chat-citation-divider" onMouseDown={handleCitationDragStart} />
            <div className="chat-citation-panel" style={{ width: citationPanelWidth }}>
              <Suspense fallback={<div style={{ padding: 40, textAlign: "center" }}>…</div>}>
                <CitationDrawer
                  target={citationTarget}
                  onClose={() => setCitationTarget(null)}
                />
              </Suspense>
            </div>
          </>
        )}
      </div>
      {shareTarget !== null && (
        <Suspense fallback={null}>
          <ShareCard
            open={shareTarget !== null}
            onClose={() => setShareTarget(null)}
            question={shareTarget.question}
            answer={shareTarget.answer}
            sources={shareTarget.sources}
          />
        </Suspense>
      )}
    </>
  );
}
