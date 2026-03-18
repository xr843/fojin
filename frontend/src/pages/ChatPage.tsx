import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { Input, Button, Space, message, Alert } from "antd";
import Markdown from "react-markdown";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  DeleteOutlined,
  PlusOutlined,
  SettingOutlined,
  MenuOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import {
  sendChatMessageStream,
  getChatSessions,
  getChatSessionMessages,
  deleteChatSession,
  getApiKeyStatus,
  getChatQuota,
  type ChatMessageItem,
  type ChatSource,
} from "../api/client";
import { useAuthStore } from "../stores/authStore";

export default function ChatPage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: sessions, refetch: refetchSessions } = useQuery({
    queryKey: ["chatSessions"],
    queryFn: getChatSessions,
    enabled: !!user,
  });

  const { data: keyStatus } = useQuery({
    queryKey: ["apiKeyStatus"],
    queryFn: getApiKeyStatus,
    enabled: !!user,
  });

  const { data: quota, refetch: refetchQuota } = useQuery({
    queryKey: ["chatQuota"],
    queryFn: getChatQuota,
    enabled: !!user,
  });

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

  const handleDeleteSession = async (sid: number) => {
    try {
      await deleteChatSession(sid);
      if (sessionId === sid) handleNewChat();
      refetchSessions();
    } catch {
      message.error("删除失败");
    }
  };

  const streamingIdRef = useRef<number>(0);

  const handleSend = useCallback(async () => {
    const msg = input.trim();
    if (!msg || sending) return;

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

    await sendChatMessageStream(msg, sessionId, {
      onToken: (content: string) => {
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId) return m;
            // Clear the "thinking" placeholder on first real token
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
      onSessionId: (newSessionId: number) => {
        if (!sessionId) {
          setSessionId(newSessionId);
          refetchSessions();
        }
      },
      onError: (errMsg: string) => {
        message.error(errMsg);
        // Clear thinking placeholder on error
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.content === "正在检索经文并生成回答..."
              ? { ...m, content: "请求失败，请重试" }
              : m,
          ),
        );
      },
      onDone: () => {
        streamingIdRef.current = 0;
        setSending(false);
        refetchQuota();
      },
    });
  }, [input, sending, sessionId, refetchSessions, refetchQuota]);

  if (!user) {
    return (
      <>
        <Helmet><title>小津 AI 佛典问答 — 佛津 FoJin</title></Helmet>
        <div style={{ maxWidth: 600, margin: "80px auto", textAlign: "center", fontFamily: '"Noto Serif SC", serif' }}>
          <RobotOutlined style={{ fontSize: 56, color: "var(--fj-accent)", marginBottom: 24 }} />
          <h2 style={{ color: "var(--fj-ink)", fontWeight: 400, marginBottom: 12 }}>小津 AI 问答</h2>
          <p style={{ color: "var(--fj-ink-muted)", lineHeight: 1.8, marginBottom: 24 }}>
            基于 38 部核心佛典、约 1100 万字经文的 RAG 智能问答系统。
            <br />登录后即可使用，每日免费 10 次。配置自己的 API Key 可无限使用。
          </p>
          <Button type="primary" onClick={() => navigate("/login")}>登录使用</Button>
        </div>
      </>
    );
  }

  return (
    <>
      <Helmet><title>小津 AI 佛典问答 — 佛津 FoJin</title></Helmet>
      <div style={{ display: "flex", height: "calc(100vh - 120px)", maxWidth: 1100, margin: "0 auto", gap: 16 }}>

        {/* Mobile sidebar drawer */}
        {sidebarOpen && (
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
                {sessions?.map((s) => (
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
            </div>
          </>
        )}

        {/* Sidebar (desktop) */}
        <div style={{ width: 220, flexShrink: 0, display: "flex", flexDirection: "column", gap: 8 }}
             className="chat-sidebar">
          <Button icon={<PlusOutlined />} block onClick={handleNewChat}>新对话</Button>
          <Button icon={<SettingOutlined />} block type="text" size="small"
            style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
            onClick={() => navigate("/profile?tab=apikey")}>
            {keyStatus?.has_api_key ? `已配置 Key (${keyStatus.provider})` : "配置 API Key"}
          </Button>
          <div style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
            {sessions?.map((s) => (
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
        </div>

        {/* Chat area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* Mobile menu toggle */}
          <Button
            className="chat-mobile-toggle"
            type="text"
            icon={<MenuOutlined />}
            onClick={() => setSidebarOpen(true)}
            style={{ alignSelf: "flex-start", marginBottom: 4 }}
          >
            会话列表
          </Button>
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
                    <div className="chat-markdown">
                      <Markdown>{m.content + (streamingIdRef.current === m.id ? " ▌" : "")}</Markdown>
                    </div>
                  ) : (
                    m.content
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
                          {s.source_type === "dify" ? (
                            <span>{"📚"} 佛典知识库 ({Math.round(s.score * 100)}%)</span>
                          ) : (
                            <a
                              onClick={() => s.text_id > 0 && navigate(`/texts/${s.text_id}/read?juan=${s.juan_num}`)}
                              style={{ cursor: s.text_id > 0 ? "pointer" : "default", color: "inherit", textDecoration: s.text_id > 0 ? "underline" : "none" }}
                            >
                              {"📖"}{" "}
                              {s.title_zh
                                ? `《${s.title_zh}》第${s.juan_num}卷`
                                : `文本#${s.text_id} 第${s.juan_num}卷`}
                              {" "}({Math.round(s.score * 100)}%)
                            </a>
                          )}
                        </div>
                      ))}
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
            {!keyStatus?.has_api_key && quota && (
              <Alert
                message={<span>今日剩余 {quota.remaining}/{quota.limit} 次免费问答。<a onClick={() => navigate("/profile?tab=apikey")}>配置 API Key</a> 可无限使用。</span>}
                type={quota.remaining <= 2 ? "warning" : "info"} showIcon closable
                style={{ marginBottom: 8, fontSize: 12 }}
              />
            )}
            <Space.Compact style={{ width: "100%" }}>
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPressEnter={handleSend}
                placeholder="输入佛学问题，如：《心经》的核心思想是什么？"
                disabled={sending}
                size="large"
                style={{ fontFamily: '"Noto Serif SC", serif' }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                loading={sending}
                size="large"
                style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}
              />
            </Space.Compact>
          </div>
        </div>
      </div>
    </>
  );
}
