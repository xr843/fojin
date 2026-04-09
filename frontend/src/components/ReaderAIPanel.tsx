import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { Input, Button, message, Spin } from "antd";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  FileTextOutlined,
  ReadOutlined,
  ClearOutlined,
  CopyOutlined,
} from "@ant-design/icons";
import Markdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import { sendChatMessageStream } from "../api/client";
import type { ChatSource, ChatMessageItem, ReadingContext } from "../api/client";
import type { ReactNode } from "react";

interface ReaderAIPanelProps {
  textId: number;
  juanNum: number;
  textTitle: string;
  /** Raw text content of the current juan/page */
  juanContent?: string;
  /** Text selected by the user in the reader */
  selectedText?: string;
  /** Called after selectedText is consumed */
  onSelectedTextConsumed?: () => void;
}

/** Extract [追问] follow-up suggestions from assistant message text. */
function parseFollowUps(content: string): { cleanContent: string; suggestions: string[] } {
  const lines = content.split("\n");
  const suggestions: string[] = [];
  const cleaned: string[] = [];
  for (const line of lines) {
    const m = line.match(/^\[追问]\s*(.+)/);
    if (m) {
      suggestions.push(m[1].trim());
    } else {
      cleaned.push(line);
    }
  }
  return { cleanContent: cleaned.join("\n").trimEnd(), suggestions };
}

function injectCitationLinks(content: string, sources: ChatSource[] | null): string {
  if (!sources || sources.length === 0) return content;
  const titleMap = new Map<string, ChatSource>();
  for (const s of sources) {
    if (!s.title_zh || s.text_id <= 0) continue;
    const existing = titleMap.get(s.title_zh);
    if (!existing || s.score > existing.score) titleMap.set(s.title_zh, s);
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

function tightenLists(md: string): string {
  return md.replace(/^(\d+\.)\s*\n\n+/gm, "$1 ").replace(/\n\n+(?=\d+\.\s)/g, "\n");
}

function getQuickActions(textTitle: string, juanNum: number) {
  return [
    { key: "explain", icon: <ReadOutlined />, label: "全文解读", prompt: `请对《${textTitle}》第${juanNum}卷进行逐段解读，提供白话翻译和重点术语解释。` },
    { key: "summary", icon: <FileTextOutlined />, label: "全文概要", prompt: `请概括《${textTitle}》第${juanNum}卷的主要内容和核心思想。` },
  ];
}

export default function ReaderAIPanel({
  textId,
  juanNum,
  textTitle,
  juanContent,
  selectedText,
  onSelectedTextConsumed,
}: ReaderAIPanelProps) {
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<number | undefined>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamingIdRef = useRef(0);
  const consumedRef = useRef(false);

  // When selectedText changes, auto-fill it as a question
  useEffect(() => {
    if (selectedText && !consumedRef.current) {
      consumedRef.current = true;
      // Don't auto-send, just show context indicator
    }
    return () => { consumedRef.current = false; };
  }, [selectedText]);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    });
  }, []);

  const readingContext: ReadingContext = useMemo(() => ({
    text_id: textId,
    juan_num: juanNum,
    selected_text: selectedText,
    page_content: juanContent,
  }), [textId, juanNum, selectedText, juanContent]);

  const handleSendMessage = useCallback(async (msg: string) => {
    msg = msg.trim();
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
    // Clear selected text after first message
    if (selectedText) onSelectedTextConsumed?.();
    scrollToBottom();

    const abortController = new AbortController();
    abortRef.current = abortController;
    const timeoutId = setTimeout(() => abortController.abort(), 90_000);

    await sendChatMessageStream(msg, sessionId, null, {
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
          prev.map((m) => m.id === assistantId ? { ...m, sources } : m),
        );
      },
      onSearching: () => {},
      onSessionId: (newSessionId: number) => {
        if (!sessionId) setSessionId(newSessionId);
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
      },
    }, abortController.signal, readingContext);
  }, [sending, sessionId, selectedText, onSelectedTextConsumed, scrollToBottom, readingContext]);

  const handleClearChat = useCallback(() => {
    if (sending) {
      abortRef.current?.abort();
    }
    setMessages([]);
    setSessionId(undefined);
    setSending(false);
  }, [sending]);

  const markdownComponents = useMemo(() => ({
    a: ({ href, children }: { href?: string; children?: ReactNode }) => {
      if (href && href.startsWith("/texts/")) {
        return (
          <Link to={href} style={{ color: "var(--fj-accent)", textDecoration: "none", borderBottom: "1px dashed var(--fj-accent)", fontWeight: 500 }}>
            {children}
          </Link>
        );
      }
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
    p: ({ children }: { children?: ReactNode }) => <p style={{ margin: "6px 0", lineHeight: 1.7 }}>{children}</p>,
  }), []);

  return (
    <div className="reader-ai-panel">
      {/* Selected text context indicator */}
      {selectedText && messages.length === 0 && (
        <div className="reader-ai-context">
          <div className="reader-ai-context-label">选中的经文：</div>
          <div className="reader-ai-context-text">
            「{selectedText.length > 100 ? selectedText.slice(0, 100) + "…" : selectedText}」
          </div>
        </div>
      )}

      {/* Quick actions */}
      {messages.length === 0 && (
        <div className="reader-ai-quick-actions">
          {getQuickActions(textTitle, juanNum).map((action) => (
            <Button
              key={action.key}
              size="small"
              icon={action.icon}
              onClick={() => handleSendMessage(action.prompt)}
              disabled={sending}
            >
              {action.label}
            </Button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="reader-ai-messages">
        {messages.length === 0 && !selectedText && (
          <div className="reader-ai-empty">
            <RobotOutlined style={{ fontSize: 28, color: "#c4b89a", marginBottom: 8 }} />
            <div style={{ color: "#8b7355", fontSize: 13 }}>
              选中经文或输入问题，AI 为你解读《{textTitle}》
            </div>
          </div>
        )}
        {messages.map((m) => {
          const isAssistant = m.role === "assistant";
          const isStreaming = isAssistant && m.id === streamingIdRef.current && sending;
          const { cleanContent, suggestions } = isAssistant
            ? parseFollowUps(m.content)
            : { cleanContent: m.content, suggestions: [] };

          return (
            <div key={m.id} className={`reader-ai-msg reader-ai-msg-${m.role}`}>
              <div className="reader-ai-msg-icon">
                {isAssistant ? <RobotOutlined /> : <UserOutlined />}
              </div>
              <div className="reader-ai-msg-content">
                {isAssistant ? (
                  m.content === "正在检索经文并生成回答..." ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#8b7355" }}>
                      <Spin size="small" /> 正在检索经文并生成回答...
                    </div>
                  ) : (
                    <>
                      <Markdown rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
                        {tightenLists(injectCitationLinks(cleanContent, m.sources)) + (isStreaming ? " ▌" : "")}
                      </Markdown>
                      {suggestions.length > 0 && !sending && (
                        <div className="reader-ai-suggestions">
                          {suggestions.map((q, i) => (
                            <span
                              key={i}
                              className="reader-ai-suggestion"
                              onClick={() => handleSendMessage(q)}
                            >
                              {q}
                            </span>
                          ))}
                        </div>
                      )}
                    </>
                  )
                ) : (
                  <div>{m.content}</div>
                )}
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="reader-ai-input-area">
        <div className="reader-ai-input-row">
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={selectedText ? "针对选中经文提问..." : "输入问题..."}
            autoSize={{ minRows: 1, maxRows: 3 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSendMessage(input);
              }
            }}
            disabled={sending}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={() => handleSendMessage(input)}
            disabled={!input.trim() || sending}
            loading={sending}
          />
        </div>
        <div className="reader-ai-input-footer">
          {messages.length > 0 && (
            <>
              <Button
                size="small"
                type="text"
                icon={<ClearOutlined />}
                onClick={handleClearChat}
              >
                清空
              </Button>
              <Button
                size="small"
                type="text"
                icon={<CopyOutlined />}
                onClick={() => {
                  const lastAssistant = [...messages].reverse().find(m => m.role === "assistant");
                  if (lastAssistant) {
                    const { cleanContent } = parseFollowUps(lastAssistant.content);
                    navigator.clipboard.writeText(cleanContent);
                    message.success("已复制");
                  }
                }}
              >
                复制
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
