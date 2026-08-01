import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { isNearBottom } from "../utils/scrollBottom";
import { Input, Button, message, Spin, Tooltip } from "antd";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  FileTextOutlined,
  ReadOutlined,
  ClearOutlined,
  CopyOutlined,
  LikeOutlined,
  LikeFilled,
  DislikeOutlined,
  DislikeFilled,
} from "@ant-design/icons";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { sendChatMessageStream, updateChatMessageFeedback } from "../api/client";
import type { ChatSource, ChatMessageItem, ReadingContext } from "../api/client";
import type { ReactNode } from "react";

type TFn = (key: string, opts?: Record<string, unknown>) => string;

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
    return `[${_match}](${url})`;
  });
}

function tightenLists(md: string): string {
  return md.replace(/^(\d+\.)\s*\n\n+/gm, "$1 ").replace(/\n\n+(?=\d+\.\s)/g, "\n");
}

function getQuickActions(textTitle: string, juanNum: number, t: TFn) {
  return [
    {
      key: "explain",
      icon: <ReadOutlined />,
      label: t("reader.ai.quick.explain"),
      prompt: t("reader.ai.prompt.explain", { title: textTitle, n: juanNum }),
    },
    {
      key: "summary",
      icon: <FileTextOutlined />,
      label: t("reader.ai.quick.summary"),
      prompt: t("reader.ai.prompt.summary", { title: textTitle, n: juanNum }),
    },
  ];
}

/** 思考中/失败 的占位哨兵。
 *
 * 此前这里用的是 `t("reader.ai.thinking")` —— 一个**翻译字符串**，在四处被拿来做
 * 相等比较（设置、onToken、onError、渲染）。只要 UI 语言在这次问答中途变一次，
 * t() 的返回值就变了，四处比较全部失配，后果是叠加的：
 *   · onToken  —— 首个 token 追加在占位符后面，答案读起来是「正在思考…色即是空」
 *   · onError  —— 失败兜底不触发，用户永远停在「正在思考」
 * 改成模块级常量按**身份**比较，与语言无关。前缀 \u0000 保证它不可能与真实答案
 * 内容相撞。 */
const THINKING_SENTINEL = "\u0000reader-thinking";
const FAILED_SENTINEL = "\u0000reader-failed";

/** 等待期的进度显示。
 *
 * 单独成组件是因为「已思考 N 秒」需要一个 setInterval 驱动的 state，而它只能挂在
 * 组件里 —— 塞进 messages.map 的回调里就是在渲染中调 Hook。
 * reasoningSince 只在内容仍是哨兵时才读：答案开始出字后这块整体消失，计时器也随
 * 之卸载。 */
function ReaderThinking({ m, t }: { m: ChatMessageItem; t: TFunction }) {
  const reasoningSince = m.reasoningSince ?? null;
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!reasoningSince) return;
    const id = setInterval(
      () => setSeconds(Math.max(0, Math.floor((Date.now() - reasoningSince) / 1000))),
      1000,
    );
    return () => clearInterval(id);
  }, [reasoningSince]);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#8b7355", flexWrap: "wrap" }}>
      <Spin size="small" />
      <span>
        {m.retrieval && (
          <>
            {t("chat.retrieved_hint", { n: m.retrieval.count })}
            {m.retrieval.titles.map((title) => (
              <span key={title} className="chat-retrieved-title">{t("chat.retrieved_title", { title })}</span>
            ))}
            <span className="chat-retrieved-sep">·</span>
          </>
        )}
        {reasoningSince
          ? `${t("chat.reasoning_hint")}${t("chat.thinking_seconds", { n: seconds })}`
          : m.retrieval
            ? t("chat.generating")
            : t("reader.ai.thinking")}
      </span>
    </div>
  );
}

export default function ReaderAIPanel({
  textId,
  juanNum,
  textTitle,
  juanContent,
  selectedText,
  onSelectedTextConsumed,
}: ReaderAIPanelProps) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<number | undefined>();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [streamingId, setStreamingId] = useState(0);
  const consumedRef = useRef(false);

  // When selectedText changes, auto-fill it as a question
  useEffect(() => {
    if (selectedText && !consumedRef.current) {
      consumedRef.current = true;
      // Don't auto-send, just show context indicator
    }
    return () => { consumedRef.current = false; };
  }, [selectedText]);

  /** 消息滚动容器。自动跟随只在用户本来就贴着底部时才做 —— 此前是无条件滚动，
   *  用户往上翻看前文时会被每一个 token 拽回底部（与 ChatPage 修复前同一个毛病）。 */
  const messagesRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  const handleMessagesScroll = useCallback(() => {
    atBottomRef.current = isNearBottom(messagesRef.current);
  }, []);

  const scrollToBottom = useCallback((force = false) => {
    if (!force && !atBottomRef.current) return;
    requestAnimationFrame(() => {
      // 触发时再判一次：rAF 回调排到下一帧才跑，这中间用户可能已经往上滚了。
      // 只在调用点判断的话，存量的 rAF 仍会把人拽回去 —— ChatPage 的终审就是
      // 在这里翻车的。
      if (!force && !atBottomRef.current) return;
      messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
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
    setStreamingId(assistantId);
    const assistantMsg: ChatMessageItem = {
      id: assistantId,
      role: "assistant",
      content: THINKING_SENTINEL,
      sources: null,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput("");
    setSending(true);
    // Clear selected text after first message
    if (selectedText) onSelectedTextConsumed?.();
    atBottomRef.current = true;   // 自己刚发了一句，必然是想看新内容
    scrollToBottom(true);

    const abortController = new AbortController();
    abortRef.current = abortController;
    // 5 min — see client.ts xhr.timeout comment. Reader mode regularly
    // hits 90-180s end-to-end on long juan + reasoning models.
    const timeoutId = setTimeout(() => abortController.abort(), 300_000);

    await sendChatMessageStream(msg, sessionId, null, {
      onToken: (content: string) => {
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== assistantId) return m;
            const current = m.content === THINKING_SENTINEL ? "" : m.content;
            return { ...m, content: current + content };
          }),
        );
        scrollToBottom();
      },
      onCitationCorrection: (correctedAnswer: string) => {
        // Backend contract (see send_message_stream): no `token` events
        // arrive after `citation_correction`. If that contract is ever
        // broken, a late chunk would append to the corrected answer and
        // re-introduce the hallucination we just stripped.
        setMessages((prev) =>
          prev.map((m) => m.id === assistantId ? { ...m, content: correctedAnswer } : m),
        );
      },
      onMessageId: (realId: number) => {
        // Swap Date.now() placeholder for real chat_messages.id so the
        // feedback button below targets the correct row. Without this
        // every freshly-streamed message's feedback PUT 404'd silently
        // — see ChatPage for the full context.
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, id: realId } : m)),
        );
      },
      onSources: (sources: ChatSource[]) => {
        setMessages((prev) =>
          prev.map((m) => m.id === assistantId ? { ...m, sources } : m),
        );
      },
      onSearching: () => {},
      // 这条路径的超时预算是 300 秒，注释写明「regularly hits 90-180s」——
      // 全站等待最长的一条路，此前用户在这 1.5-3 分钟里只看得到一句静态文案。
      // 两个事件只写各自独立的字段，绝不碰 content：一旦写进 content，上面那条
      // 「空转兜底」就失效了（它按 THINKING_SENTINEL 的身份判断）。
      onRetrieved: (info) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, retrieval: info } : m)),
        );
      },
      onReasoning: () => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && !m.reasoningSince
              ? { ...m, reasoningSince: Date.now() }
              : m,
          ),
        );
      },
      onSessionId: (newSessionId: number) => {
        if (!sessionId) setSessionId(newSessionId);
      },
      onError: (errMsg: string) => {
        message.error(errMsg);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.content === THINKING_SENTINEL
              ? { ...m, content: FAILED_SENTINEL }
              : m,
          ),
        );
      },
      onDone: () => {
        clearTimeout(timeoutId);
        abortRef.current = null;
        setStreamingId(0);
        setSending(false);
        // 流结束了却一个 token 都没来过（也没有 error 帧，例如后端只发了个裸
        // done）。不兜住的话，这个气泡会永远停在「正在思考」，而 sending 已复位、
        // 连重试的由头都没有。转成失败态，与 onError 走同一条出口。
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.content === THINKING_SENTINEL
              ? { ...m, content: FAILED_SENTINEL }
              : m,
          ),
        );
      },
    }, { signal: abortController.signal, readingContext });
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
          <Link to={href} style={{ color: "var(--fj-highlight)", textDecoration: "none", borderBottom: "1px dashed var(--fj-accent)", fontWeight: 500 }}>
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
          <div className="reader-ai-context-label">{t("reader.ai.selected_label")}</div>
          <div className="reader-ai-context-text">
            「{selectedText.length > 100 ? selectedText.slice(0, 100) + "…" : selectedText}」
          </div>
        </div>
      )}

      {/* Quick actions */}
      {messages.length === 0 && (
        <div className="reader-ai-quick-actions">
          {getQuickActions(textTitle, juanNum, t).map((action) => (
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
      <div className="reader-ai-messages" ref={messagesRef} onScroll={handleMessagesScroll}>
        {messages.length === 0 && !selectedText && (
          <div className="reader-ai-empty">
            <RobotOutlined style={{ fontSize: 28, color: "#c4b89a", marginBottom: 8 }} />
            <div style={{ color: "#8b7355", fontSize: 13 }}>
              {t("reader.ai.empty", { title: textTitle })}
            </div>
          </div>
        )}
        {messages.map((m) => {
          const isAssistant = m.role === "assistant";
          const isStreaming = isAssistant && m.id === streamingId && sending;
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
                  m.content === FAILED_SENTINEL ? (
                    <div style={{ color: "var(--fj-ink-muted)" }}>{t("chat.request_failed")}</div>
                  ) : m.content === THINKING_SENTINEL ? (
                    <ReaderThinking m={m} t={t} />
                  ) : (
                    <>
                      <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
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
                      {/* Feedback row — only after streaming completes
                          and only on a real persisted message id (the
                          backend swaps the local Date.now() placeholder
                          via the message_id SSE event). Mirrors
                          ChatPage's pattern so the two chat surfaces
                          collect feedback uniformly. */}
                      {!isStreaming && m.id < 1e12 && (
                        <div style={{ marginTop: 8, display: "flex", gap: 4 }}>
                          <Tooltip title={t("chat.feedback_helpful")}>
                            <Button
                              type="text"
                              size="small"
                              icon={m.feedback === "up" ? <LikeFilled /> : <LikeOutlined />}
                              style={{
                                color: m.feedback === "up" ? "var(--fj-accent)" : "var(--fj-ink-muted)",
                                fontSize: 12,
                              }}
                              onClick={() => {
                                const newFeedback = m.feedback === "up" ? null : "up";
                                const prevFeedback = m.feedback;
                                setMessages((prev) =>
                                  prev.map((x) => (x.id === m.id ? { ...x, feedback: newFeedback } : x)),
                                );
                                updateChatMessageFeedback(m.id, newFeedback as "up" | "down" | null).catch(() => {
                                  setMessages((prev) =>
                                    prev.map((x) => (x.id === m.id ? { ...x, feedback: prevFeedback } : x)),
                                  );
                                });
                              }}
                            />
                          </Tooltip>
                          <Tooltip title={t("chat.feedback_not_helpful")}>
                            <Button
                              type="text"
                              size="small"
                              icon={m.feedback === "down" ? <DislikeFilled /> : <DislikeOutlined />}
                              style={{
                                color: m.feedback === "down" ? "#e74c3c" : "var(--fj-ink-muted)",
                                fontSize: 12,
                              }}
                              onClick={() => {
                                const newFeedback = m.feedback === "down" ? null : "down";
                                const prevFeedback = m.feedback;
                                setMessages((prev) =>
                                  prev.map((x) => (x.id === m.id ? { ...x, feedback: newFeedback } : x)),
                                );
                                updateChatMessageFeedback(m.id, newFeedback as "up" | "down" | null).catch(() => {
                                  setMessages((prev) =>
                                    prev.map((x) => (x.id === m.id ? { ...x, feedback: prevFeedback } : x)),
                                  );
                                });
                              }}
                            />
                          </Tooltip>
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
            placeholder={selectedText ? t("reader.ai.placeholder_selected") : t("reader.ai.placeholder")}
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
                {t("reader.ai.clear")}
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
                    message.success(t("chat.copied"));
                  }
                }}
              >
                {t("chat.copy")}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
