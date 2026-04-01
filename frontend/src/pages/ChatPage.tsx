import { useState, useRef, useCallback, useMemo, useEffect, type ReactNode } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { Input, Button, Space, message, Alert, Tooltip, Modal } from "antd";
import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
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
  ReadOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import {
  sendChatMessageStream,
  getChatSessions,
  getChatSessionMessages,
  deleteChatSession,
  getApiKeyStatus,
  getChatQuota,
  getHotQuestions,
  updateChatMessageFeedback,
  type ChatMessageItem,
  type ChatSource,
  type ChatSessionItem,
} from "../api/client";
import { useAuthStore } from "../stores/authStore";

/** Collapse loose markdown lists into tight lists by removing blank lines between list items. */
function tightenLists(md: string): string {
  // "1.\n\n内容" → "1. 内容" (编号独占一行后跟空行)
  return md.replace(/^(\d+\.)\s*\n\n+/gm, "$1 ")
    // "内容\n\n2." → "内容\n2." (列表项之间的空行)
    .replace(/\n\n+(?=\d+\.\s)/g, "\n");
}

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

/**
 * Replace citation patterns like 【《心经》第1卷】 in markdown content
 * with clickable markdown links using source data to map title -> text_id.
 */
function injectCitationLinks(content: string, sources: ChatSource[] | null): string {
  if (!sources || sources.length === 0) return content;

  const titleMap = new Map<string, ChatSource>();
  for (const s of sources) {
    if (!s.title_zh || s.text_id <= 0) continue;
    const existing = titleMap.get(s.title_zh);
    if (!existing || s.score > existing.score) {
      titleMap.set(s.title_zh, s);
    }
  }
  if (titleMap.size === 0) return content;

  return content.replace(/【《([^》]+)》(?:第(\d+)卷)?】/g, (_match, title: string, juanStr: string | undefined) => {
    const source = titleMap.get(title);
    if (!source) return _match;
    const juan = juanStr ? parseInt(juanStr, 10) : source.juan_num;
    const url = `/texts/${source.text_id}/read?juan=${juan}`;
    const label = juanStr ? `【《${title}》第${juanStr}卷】` : `【《${title}》】`;
    return `[${label}](${url})`;
  });
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
  const { user } = useAuthStore();
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sessionFilter, setSessionFilter] = useState("");
  const tabIndexRef = useRef(-1);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const bottomRef = useRef<HTMLDivElement>(null);

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

  // Custom markdown components: render internal citation links with react-router Link
  const markdownComponents = useMemo(() => ({
    a: ({ href, children }: { href?: string; children?: ReactNode }) => {
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
  }), []);

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
      scrollToBottom();
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

  const handleSendMessage = useCallback(async (text: string) => {
    const msg = text.trim();
    if (!msg || sending) return;

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

    await sendChatMessageStream(msg, sessionId, {
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
      },
      onSearching: (searchMsg: string) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: searchMsg } : m,
          ),
        );
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
    }, abortController.signal);
  }, [sending, sessionId, user, refetchSessions, refetchQuota]);

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
    return hotQuestionsData?.questions ?? [
      "《心经》中「色不异空」的含义是什么？",
      "鸠摩罗什与玄奘的翻译风格有何不同？",
      "四圣谛的核心教义是什么？",
      "禅宗的「不立文字」思想源自哪些经典？",
    ];
  }, [messages, hotQuestionsData]);

  const inputRef = useRef<HTMLInputElement | null>(null);

  // Attach native keydown listener to capture Tab before Ant Design / browser handles it
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || tabSuggestions.length === 0) return;
      const val = (e.target as HTMLInputElement).value || "";
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
    const sessionTitle = sessions?.find((s) => s.id === sessionId)?.title || "新对话";
    const now = new Date().toLocaleString("zh-CN");
    let md = `# ${sessionTitle}\n导出时间: ${now}\n\n`;
    for (const m of messages) {
      if (m.role === "user") {
        md += `## 用户\n${m.content}\n\n`;
      } else {
        md += `## AI 助手\n${m.content}\n\n`;
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
  }, [messages, sessions, sessionId]);

  return (
    <>
      <Helmet><title>小津 AI 佛典问答 — 佛津 FoJin</title></Helmet>
      <div style={{ display: "flex", height: "calc(100vh - 120px)", maxWidth: 1100, margin: "0 auto", gap: 16 }}>

        {/* Mobile sidebar drawer (logged in only) */}
        {user && sidebarOpen && (
          <>
            <div className="chat-sidebar-overlay" onClick={() => setSidebarOpen(false)} />
            <div className="chat-sidebar-drawer">
              <Button icon={<PlusOutlined />} block onClick={() => { handleNewChat(); setSidebarOpen(false); }}>新对话</Button>
              <Button icon={<SettingOutlined />} block type="text" size="small"
                style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                onClick={() => { navigate("/profile?tab=apikey"); setSidebarOpen(false); }}>
                {keyStatus?.has_api_key ? `已配置 Key (${keyStatus.provider})` : "配置 API Key"}
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
                          {s.title || "新对话"}
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
          <Button icon={<PlusOutlined />} block onClick={handleNewChat}>新对话</Button>
          <Button icon={<SettingOutlined />} block type="text" size="small"
            style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
            onClick={() => navigate("/profile?tab=apikey")}>
            {keyStatus?.has_api_key ? `已配置 Key (${keyStatus.provider})` : "配置 API Key"}
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
                      {s.title || "新对话"}
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
            {hasOlderMessages && (
              <div style={{ textAlign: "center", marginBottom: 12 }}>
                <Button size="small" type="text" loading={loadingOlder} onClick={loadOlderMessages}
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}>
                  加载更早的消息
                </Button>
              </div>
            )}
            {messages.length === 0 && (
              <div style={{ textAlign: "center", padding: "60px 24px", color: "var(--fj-ink-muted)" }}>
                <RobotOutlined style={{ fontSize: 48, marginBottom: 16, color: "var(--fj-accent)" }} />
                <div style={{ fontSize: 18, fontFamily: '"Noto Serif SC", serif', marginBottom: 8 }}>
                  小津 AI 佛典问答
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                  可以问我关于佛经内容、佛教历史、经典翻译等问题
                  <br />每条回答均附经文原文引用
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
                  {(hotQuestionsData?.questions ?? [
                    "《心经》中「色不异空」的含义是什么？",
                    "鸠摩罗什与玄奘的翻译风格有何不同？",
                    "四圣谛的核心教义是什么？",
                    "禅宗的「不立文字」思想源自哪些经典？",
                  ]).map((q) => (
                    <div
                      key={q}
                      onClick={() => handleSendMessage(q)}
                      style={{
                        padding: "10px 14px",
                        borderRadius: 8,
                        border: "1px solid rgba(217,208,193,0.6)",
                        fontSize: 13,
                        cursor: "pointer",
                        lineHeight: 1.6,
                        transition: "all 0.2s",
                        color: "var(--fj-ink-muted)",
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
                      {q}
                    </div>
                  ))}
                </div>
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
                <div style={{
                  maxWidth: "75%",
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
                            <Markdown rehypePlugins={[rehypeSanitize]} components={markdownComponents}>{tightenLists(injectCitationLinks(cleanContent, m.sources)) + (isStreaming ? " ▌" : "")}</Markdown>
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
                    <>
                      {m.content}
                      <div style={{ marginTop: 6, display: "flex", justifyContent: "flex-end" }}>
                        <Tooltip title="复制">
                          <Button
                            type="text" size="small" icon={<CopyOutlined />}
                            style={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}
                            onClick={() => { navigator.clipboard.writeText(m.content); message.success("已复制"); }}
                          />
                        </Tooltip>
                      </div>
                    </>
                  )}
                  {m.sources && m.sources.length > 0 && (
                    <div style={{
                      marginTop: 8,
                      paddingTop: 8,
                      borderTop: `1px solid ${m.role === "user" ? "rgba(255,255,255,0.2)" : "rgba(217,208,193,0.5)"}`,
                      fontSize: 12,
                      opacity: 0.8,
                    }}>
                      {m.sources.map((s, i) => (
                        <div key={i} style={{ marginBottom: 4 }}>
                          <Tooltip title={s.chunk_text} placement="top" overlayStyle={{ maxWidth: 400 }}>
                            <a
                              onClick={() => s.text_id > 0 && navigate(`/texts/${s.text_id}/read?juan=${s.juan_num}`)}
                              style={{
                                cursor: s.text_id > 0 ? "pointer" : "default",
                                color: "inherit",
                                textDecoration: s.text_id > 0 ? "underline" : "none",
                                borderRadius: 4,
                                padding: "1px 4px",
                                transition: "background 0.2s",
                              }}
                              onMouseEnter={(e) => { if (s.text_id > 0) e.currentTarget.style.background = "rgba(176,141,87,0.15)"; }}
                              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                            >
                              {"📖"}{" "}
                              {s.title_zh
                                ? `《${s.title_zh}》第${s.juan_num}卷`
                                : `文本#${s.text_id} 第${s.juan_num}卷`}
                              {" "}({Math.round(s.score * 100)}%)
                            </a>
                          </Tooltip>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Related reading cards */}
                  {m.role === "assistant" && m.sources && m.sources.length > 0 && streamingIdRef.current !== m.id && (() => {
                    const seen = new Set<number>();
                    const unique = m.sources!.filter((s) => {
                      if (s.text_id <= 0 || seen.has(s.text_id)) return false;
                      seen.add(s.text_id);
                      return true;
                    }).slice(0, 3);
                    return unique.length > 0 ? (
                      <div style={{
                        marginTop: 8, padding: "6px 10px", borderRadius: 8,
                        background: "rgba(176,141,87,0.08)", border: "1px solid rgba(176,141,87,0.2)",
                      }}>
                        {unique.map((s) => (
                          <div key={s.text_id} style={{
                            display: "flex", alignItems: "center", gap: 6, padding: "3px 0", fontSize: 12,
                          }}>
                            <ReadOutlined style={{ color: "var(--fj-accent)", fontSize: 13 }} />
                            <span style={{ fontFamily: '"Noto Serif SC", serif', color: "var(--fj-ink)" }}>
                              {s.title_zh ? `《${s.title_zh}》` : `文本#${s.text_id}`}
                            </span>
                            <a
                              onClick={() => navigate(`/texts/${s.text_id}/read`)}
                              style={{ color: "var(--fj-accent)", cursor: "pointer", marginLeft: "auto", whiteSpace: "nowrap" }}
                            >
                              阅读全文 →
                            </a>
                          </div>
                        ))}
                      </div>
                    ) : null;
                  })()}
                  {/* Action buttons for assistant messages */}
                  {m.role === "assistant" && m.content !== "正在检索经文并生成回答..." && streamingIdRef.current !== m.id && (
                    <div style={{ marginTop: 6, display: "flex", gap: 4 }}>
                      <Tooltip title="复制回答">
                        <Button
                          type="text" size="small" icon={<CopyOutlined />}
                          style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                          onClick={() => { navigator.clipboard.writeText(m.content); message.success("已复制"); }}
                        />
                      </Tooltip>
                      {user && (
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
                      {m.content === "请求失败，请重试" && (
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
            {!keyStatus?.has_api_key && quota && quota.remaining >= 0 && (
              <Alert
                message={<span>每日免费 {quota.limit} 次问答，今日剩余 {quota.remaining} 次。{user
                  ? <><a onClick={() => navigate("/profile?tab=apikey")}>配置 API Key</a> 可无限使用。</>
                  : <><a onClick={() => navigate("/login")}>登录</a>后每日可用 30 次。配置自己的 API Key 可无限使用。</>}</span>}
                type={quota.remaining <= 2 ? "warning" : "info"} showIcon closable
                style={{ marginBottom: 8, fontSize: 12 }}
              />
            )}
            <Space.Compact style={{ width: "100%" }}>
              <Input
                ref={(instance) => { inputRef.current = instance?.input ?? null; }}
                value={input}
                onChange={(e) => { setInput(e.target.value); tabIndexRef.current = -1; }}
                onPressEnter={handleSend}
                placeholder={tabSuggestions.length > 0 ? `${tabSuggestions[(tabIndexRef.current + 1) % tabSuggestions.length]}    ⇥ Tab` : "输入佛学问题，如：《心经》的核心思想是什么？"}
                disabled={sending}
                size="large"
                style={{ fontFamily: '"Noto Serif SC", serif' }}
              />
              {sending ? (
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={handleCancel}
                  size="large"
                >
                  停止
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
      </div>
    </>
  );
}
