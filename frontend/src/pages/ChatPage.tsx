import { useState, useRef, useCallback, useMemo, useEffect, lazy, Suspense, memo, type ReactNode } from "react";
import { useNavigate, useSearchParams, Link } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Input, Button, message, Alert, Tooltip, Modal, Tag, Spin, Dropdown } from "antd";
import type { InputRef } from "antd";
import Markdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { CITATION_URL_SCHEME, injectCitationLinks } from "../utils/citationLinks";
import { quoteCheckDetail } from "../utils/trustDetail";
import { isNearBottom } from "../utils/scrollBottom";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  DeleteOutlined,
  PlusOutlined,
  SettingOutlined,
  MenuOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DownloadOutlined,
  StopOutlined,
  CopyOutlined,
  ReloadOutlined,
  LikeOutlined,
  LikeFilled,
  DislikeOutlined,
  DislikeFilled,
  ShareAltOutlined,
  DownOutlined,
  MoreOutlined,
  EditOutlined,
  PushpinOutlined,
  PushpinFilled,
  SearchOutlined,
} from "@ant-design/icons";
const ShareCard = lazy(() => import("../components/ShareCard"));
const CitationDrawer = lazy(() => import("../components/CitationDrawer"));
import ChatModelSelector from "../components/ChatModelSelector";
import MasterGallery, { MasterSeal } from "../components/MasterGallery";
import DraggableModal from "../components/DraggableModal";
import { getMasters } from "../api/client";
import type { CitationTarget } from "../components/CitationDrawer";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  sendChatMessageStream,
  getChatSessions,
  getChatSessionMessages,
  deleteChatSession,
  updateChatSession,
  getApiKeyStatus,
  getChatQuota,
  getChunkContext,
  getHotQuestions,
  getRandomHotQuestions,
  updateChatMessageFeedback,
  type ChatMessageItem,
  type ChatSource,
  type ChatSessionItem,
  type ChatTrustStatus,
  type HotQuestionCard,
  type HotQuestionCategory,
} from "../api/client";
import {
  uploadChatAttachment,
  type ChatAttachmentMeta,
} from "../api/chatAttachments";
import { useAuthStore, type UserProfile } from "../stores/authStore";

const MAX_ATTACHMENTS = 5;
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const ATTACHMENT_ACCEPT = ".pdf,.txt,.md,.docx,.csv,.html,.htm";

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

// Streaming placeholder / failure sentinels. These exact strings are stored
// in message state and compared by identity in several places below; the
// display sites render t("chat.thinking") / t("chat.request_failed") instead,
// so the stored sentinel survives a UI language switch.
const THINKING_SENTINEL = "正在检索经文并生成回答..."; // i18n-exempt
const REQUEST_FAILED_SENTINEL = "请求失败，请重试"; // i18n-exempt

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

function trustStatusLabelKey(status?: ChatTrustStatus | null): string | null {
  if (!status) return null;
  return `chat.trust.${status.state}`;
}

function trustStatusColor(status?: ChatTrustStatus | null): string {
  switch (status?.state) {
    case "verified":
      return "#3f7d20";
    case "quote_relaxed":
      // A paraphrase-as-quote was relaxed to prose (fixed) — a correction, not
      // a warning, so use the accent tone rather than the legacy amber.
      return "var(--fj-accent)";
    case "quote_unverified":
      return "#a66300";
    case "no_sources":
      return "var(--fj-ink-muted)";
    default:
      return "var(--fj-accent)";
  }
}

interface ParsedCitation {
  textId: number;
  juanNum: number;
  chunkIndex: number;
  titleZh: string;
  quote?: string;
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
  // Segment 5 (optional) carries the quoted passage so the drawer can
  // highlight it. Absent on legacy links built before quote-aware citations.
  const quote = parts[4] ? decodeURIComponent(parts[4]) : undefined;
  if (!Number.isFinite(textId) || !Number.isFinite(juanNum) || !Number.isFinite(chunkIndex)) {
    return null;
  }
  return { textId, juanNum, chunkIndex, titleZh, quote };
}

// Pinned sessions leave the date groups entirely and form their own section at
// the top — that is the whole point of pinning. Leaving them ALSO in 今天/更早
// would show the same conversation twice and give two rows the same React key.
function groupSessions(sessions: ChatSessionItem[]): { label: string; items: ChatSessionItem[] }[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: Record<string, ChatSessionItem[]> = { pinned: [], today: [], yesterday: [], week: [], older: [] };
  for (const s of sessions) {
    if (s.pinned) {
      groups.pinned.push(s);
      continue;
    }
    const d = new Date(s.created_at);
    if (d >= today) groups.today.push(s);
    else if (d >= yesterday) groups.yesterday.push(s);
    else if (d >= weekAgo) groups.week.push(s);
    else groups.older.push(s);
  }

  // label is an i18n key — render with t(group.label)
  const result: { label: string; items: ChatSessionItem[] }[] = [];
  if (groups.pinned.length) result.push({ label: "chat.session_group_pinned", items: groups.pinned });
  if (groups.today.length) result.push({ label: "chat.session_group_today", items: groups.today });
  if (groups.yesterday.length) result.push({ label: "chat.session_group_yesterday", items: groups.yesterday });
  if (groups.week.length) result.push({ label: "chat.session_group_week", items: groups.week });
  if (groups.older.length) result.push({ label: "chat.session_group_older", items: groups.older });
  return result;
}

interface SessionRowProps {
  s: ChatSessionItem;
  active: boolean;
  onSelect: (id: number) => void;
  onRename: (s: ChatSessionItem) => void;
  onTogglePin: (s: ChatSessionItem) => void;
  onDelete: (id: number) => void;
}

/** One conversation in the sidebar, with its ⋯ menu (重命名 / 置顶 / 删除).
 *
 * Shared by the desktop sidebar and the mobile drawer, which render the same
 * list twice. Before this existed the two copies had already drifted apart in
 * their click handlers; a three-item menu duplicated by hand would drift again.
 */
function SessionRow({ s, active, onSelect, onRename, onTogglePin, onDelete }: SessionRowProps) {
  const { t } = useTranslation();
  const pinned = !!s.pinned;
  // 受控 open 有两个理由，都不是为了好看：
  // ① antd 的 Dropdown 不给触发器加任何 aria —— 读屏软件只会念「更多操作，按钮」，
  //    不会说这是个菜单、也不会说它已展开。aria-expanded 需要我们自己知道状态。
  // ② 鼠标点开时 antd 不把焦点移进菜单（实测 activeElement 仍是 body），Esc 因此
  //    没有接收者。挂一个 document 级监听补上。
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <div
      className="chat-session-row"
      data-active={active || undefined}
      // 选中/悬停的配色全部交给 CSS（见 .chat-session-row[data-active]）——
      // 行内 style 的优先级压过类选择器，留在这里会让 :hover 规则永远不生效。
      style={{
        padding: "8px 6px 8px 12px",
        borderRadius: 6,
        cursor: "pointer",
        fontSize: 13,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 4,
      }}
      onClick={() => onSelect(s.id)}
    >
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
        {pinned && (
          <PushpinFilled
            className="chat-session-pin-mark"
            style={{ fontSize: 10, marginRight: 4, opacity: 0.55 }}
          />
        )}
        {s.title || t("chat.new_chat")}
      </span>
      <Dropdown
        trigger={["click"]}
        placement="bottomRight"
        open={open}
        onOpenChange={setOpen}
        menu={{
          items: [
            { key: "rename", icon: <EditOutlined />, label: t("chat.rename") },
            { key: "pin", icon: <PushpinOutlined />, label: pinned ? t("chat.unpin") : t("chat.pin") },
            { type: "divider" },
            { key: "delete", icon: <DeleteOutlined />, label: t("chat.delete"), danger: true },
          ],
          onClick: ({ key, domEvent }) => {
            // 承重。菜单虽然渲染进 portal，但 React 合成事件沿**组件树**冒泡，
            // 而 Dropdown 在组件树里就挂在这一行内部 —— 不拦住的话，点「重命名」
            // 会同时触发整行的 onClick 把用户甩进这个会话。实测过：去掉这一行，
            // ChatPage.test.tsx 的「点菜单项不会顺带切换会话」立刻变红。
            domEvent.stopPropagation();
            if (key === "rename") onRename(s);
            else if (key === "pin") onTogglePin(s);
            else if (key === "delete") onDelete(s.id);
          },
        }}
      >
        {/* 必须是原生 <button>：Dropdown 的 click 触发器只听 click 事件，而浏览器
            只为真正的可交互元素把 Enter/空格合成成 click。span[role=button] 看着
            一样，键盘用户却永远打不开这个菜单。 */}
        <button
          type="button"
          className="chat-session-more"
          aria-label={t("chat.session_actions")}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={(e) => e.stopPropagation()}
        >
          <MoreOutlined style={{ fontSize: 13 }} />
        </button>
      </Dropdown>
    </div>
  );
}

interface MessageBubbleProps {
  m: ChatMessageItem;
  isStreaming: boolean;
  sending: boolean;
  user: UserProfile | null;
  markdownComponents: Components;
  onSuggestionClick: (q: string) => void;
  onShare: (m: ChatMessageItem) => void;
  onRetry: (m: ChatMessageItem) => void;
  onFeedback: (m: ChatMessageItem, dir: "up" | "down") => void;
  onSourceClick: (source: ChatSource) => void;
}

/** One chat message row, memoised on (m, isStreaming, sending, user). A streaming
    token swaps only the streaming message's object identity (onToken does {...m}),
    so only THAT bubble re-renders — history is skipped. Previously the markdown
    preprocessing (parseFollowUps / injectCitationLinks / tightenLists + the
    react-markdown render) re-ran for every historical message on every token,
    which was the dominant "越聊越卡" jank in long conversations. */
function MessageBubbleInner({
  m, isStreaming, sending, user, markdownComponents,
  onSuggestionClick, onShare, onRetry, onFeedback, onSourceClick,
}: MessageBubbleProps) {
  // Read t here (not as a prop): on a mid-conversation language switch, i18next's
  // subscription re-renders the bubble — which memo does NOT block, since memo
  // only short-circuits parent-driven, prop-equal re-renders — so tooltips/toasts
  // update immediately, without `t` having to enter the comparator (and without
  // risking the per-token memo skip if t's identity weren't stable).
  const { t } = useTranslation();
  const isAssistantText =
    m.role === "assistant" && m.content !== THINKING_SENTINEL && m.content !== REQUEST_FAILED_SENTINEL;

  // While streaming the 追问 block is incomplete, so skip parseFollowUps then
  // (matches the previous inline behaviour). Memoised so a re-render that isn't
  // a content change (e.g. `sending` toggling) doesn't re-parse.
  const { cleanContent, suggestions } = useMemo(() => {
    if (!isAssistantText) return { cleanContent: "", suggestions: [] as string[] };
    return isStreaming ? { cleanContent: m.content, suggestions: [] as string[] } : parseFollowUps(m.content);
  }, [isAssistantText, isStreaming, m.content]);

  const rendered = useMemo(
    () => (isAssistantText ? tightenLists(injectCitationLinks(cleanContent, m.sources)) + (isStreaming ? " ▌" : "") : ""),
    [isAssistantText, cleanContent, m.sources, isStreaming],
  );

  // Distinct retrieved sources (deduped by text + fascicle) shown as a
  // persistent "参考经文" list under the answer. Inline 【…】 citations only
  // appear when the LLM names the sutra in prose; this surfaces EVERY retrieved
  // source, so any of them can be opened in the citation drawer and checked
  // against the original one click away — even when the model paraphrased.
  const sourceChips = useMemo(() => {
    if (!isAssistantText || !m.sources) return [] as ChatSource[];
    const seen = new Set<string>();
    const out: ChatSource[] = [];
    for (const s of m.sources) {
      if (!s.title_zh) continue; // no title → nothing meaningful to label the chip with
      const key = `${s.text_id}:${s.juan_num}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
    }
    return out;
  }, [isAssistantText, m.sources]);
  const trustLabelKey = trustStatusLabelKey(m.trust_status);
  const quoteDetail = quoteCheckDetail(m.trust_status);

  // 「已思考 N 秒」要自己走秒 —— 后端只在推理增量到达时发活性信号（约 1 次/秒
  // 且会随推理结束而停），秒数不能靠事件驱动。memo 不拦组件自身的 state 更新，
  // 所以这个 tick 只会重渲染这一个气泡。
  const reasoningSince = m.content === THINKING_SENTINEL ? m.reasoningSince : null;
  const [thinkingSeconds, setThinkingSeconds] = useState(0);
  useEffect(() => {
    if (!reasoningSince) return;
    // Date.now() 只能在 effect 的回调里读，不能在渲染期 —— React Compiler 的
    // react-hooks/purity 会把渲染期调用判为 error（CI 跑 --max-warnings 0）。
    // 也不在 effect 体内同步 setState（react-hooks/set-state-in-effect），所以
    // 只挂 interval：首帧显示「已思考 0 秒」本来就是对的，1 秒后开始走。
    const id = setInterval(
      () => setThinkingSeconds(Math.max(0, Math.floor((Date.now() - reasoningSince) / 1000))),
      1000,
    );
    return () => clearInterval(id);
  }, [reasoningSince]);

  return (
    <div style={{
      display: "flex", gap: 12, marginBottom: 16, padding: "0 16px",
      flexDirection: m.role === "user" ? "row-reverse" : "row",
    }}>
      <div style={{
        width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: m.role === "user" ? "var(--fj-accent)" : "rgba(217,208,193,0.5)",
        color: m.role === "user" ? "#fff" : "var(--fj-ink)", fontSize: 14,
      }}>
        {m.role === "user" ? <UserOutlined /> : <RobotOutlined />}
      </div>
      <div style={{ maxWidth: "75%", display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start" }}>
        <div style={{
          padding: "10px 16px", borderRadius: 12,
          background: m.role === "user" ? "var(--fj-accent)" : "rgba(217,208,193,0.2)",
          color: m.role === "user" ? "#fff" : "var(--fj-ink)",
          fontSize: 14, lineHeight: 1.8, whiteSpace: "pre-wrap", wordBreak: "break-word",
        }}>
          {m.role === "assistant" ? (
            m.content === THINKING_SENTINEL ? (
              <div className="chat-thinking">
                {/* 收进单个 span：.chat-thinking 是 inline-flex，为「一句短文案 +
                    三个点」设计的；多段内容直接铺进去会各自变成 flex 项，被挤成
                    竖排窄列。包一层后它仍只有两个 flex 项，内部按正常文本流换行。 */}
                {/* 三段独立组合，不要把推理嵌进检索分支里 —— 生产上 retrieved
                    确实总先于 reasoning 到达，但那是时序巧合而非契约，任一方缺席
                    时另一方都应照常显示。 */}
                <span className="chat-thinking-text">
                  {m.retrieval && (
                    <>
                      {t("chat.retrieved_hint", { n: m.retrieval.count })}
                      {m.retrieval.titles.map((tt) => (
                        <span key={tt} className="chat-retrieved-title">
                          {t("chat.retrieved_title", { title: tt })}
                        </span>
                      ))}
                      <span className="chat-retrieved-sep">·</span>
                    </>
                  )}
                  {/* 括号并在翻译值里，不写死在这里 —— 全角（）是 U+FF08/FF09，
                      落在半宽全宽形式区，i18n 扫描器的 CJK 正则结构上扫不到它，
                      门禁绿灯不能当作「英文界面没问题」的证据。英文值自带半角括号。 */}
                  {reasoningSince
                    ? `${t("chat.reasoning_hint")}${t("chat.thinking_seconds", { n: thinkingSeconds })}`
                    : m.retrieval
                      ? t("chat.generating")
                      : t("chat.thinking")}
                </span>
                <span className="chat-thinking-dots"><span /><span /><span /></span>
              </div>
            ) : m.content === REQUEST_FAILED_SENTINEL ? (
              t("chat.request_failed")
            ) : (
              <>
                <div className="chat-markdown">
                  <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeSanitize, CHAT_SANITIZE_SCHEMA]]} urlTransform={chatUrlTransform} components={markdownComponents}>{rendered}</Markdown>
                </div>
                {trustLabelKey && (
                  <div
                    style={{
                      marginTop: 8,
                      paddingTop: 6,
                      borderTop: "1px solid rgba(217,208,193,0.45)",
                      color: trustStatusColor(m.trust_status),
                      fontSize: 12,
                      lineHeight: 1.5,
                    }}
                  >
                    {t(trustLabelKey)}
                    {quoteDetail && (
                      <span style={{ color: "var(--fj-ink-muted)" }}>
                        {" · "}
                        {quoteDetail.key === "chat.trust.quotes_checked"
                          ? t(quoteDetail.key, { n: quoteDetail.count })
                          : t(quoteDetail.key)}
                      </span>
                    )}
                  </div>
                )}
                {sourceChips.length > 0 && (
                  <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                    <span style={{ fontSize: 12, color: "var(--fj-ink-muted)" }}>{t("chat.reference_sources")}</span>
                    {sourceChips.map((s) => (
                      <button
                        key={`${s.text_id}:${s.juan_num}`}
                        type="button"
                        onClick={() => onSourceClick(s)}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 4,
                          padding: "3px 10px", borderRadius: 12,
                          border: "1px solid rgba(176,141,87,0.5)", background: "rgba(176,141,87,0.06)",
                          color: "var(--fj-ink-muted)", fontSize: 12, lineHeight: 1.6, cursor: "pointer", transition: "all 0.2s",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(176,141,87,0.16)"; e.currentTarget.style.color = "var(--fj-accent)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(176,141,87,0.06)"; e.currentTarget.style.color = "var(--fj-ink-muted)"; }}
                      >
                        {t("reader.citation.title_with_juan", { title: s.title_zh, n: s.juan_num })}
                      </button>
                    ))}
                  </div>
                )}
                {suggestions.length > 0 && !sending && (
                  <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {suggestions.map((q, i) => (
                      <span
                        key={i}
                        onClick={() => onSuggestionClick(q)}
                        style={{
                          display: "inline-block", padding: "4px 12px", borderRadius: 14,
                          border: "1px solid var(--fj-gold, #b08d57)", color: "var(--fj-gold, #b08d57)",
                          fontSize: 12, cursor: "pointer", background: "transparent", transition: "all 0.2s", lineHeight: 1.6,
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(176,141,87,0.1)"; e.currentTarget.style.color = "var(--fj-accent)"; e.currentTarget.style.borderColor = "var(--fj-accent)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--fj-gold, #b08d57)"; e.currentTarget.style.borderColor = "var(--fj-gold, #b08d57)"; }}
                      >
                        {q}
                      </span>
                    ))}
                  </div>
                )}
              </>
            )
          ) : (
            m.content
          )}
        </div>
        {/* Action buttons outside bubble */}
        {m.content !== THINKING_SENTINEL && !isStreaming && (
          <div style={{ marginTop: 4, display: "flex", gap: 4 }}>
            <Tooltip title={t("chat.copy")}>
              <Button
                type="text" size="small" icon={<CopyOutlined />}
                style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                onClick={() => {
                  const textToCopy = m.role === "assistant" ? parseFollowUps(m.content).cleanContent : m.content;
                  navigator.clipboard.writeText(textToCopy);
                  message.success(t("chat.copied"));
                  // Behavioural quality signal: copying an answer = found it useful.
                  if (m.role === "assistant" && typeof umami !== "undefined") {
                    umami.track("chat_copy");
                  }
                }}
              />
            </Tooltip>
            {m.role === "assistant" && m.content !== REQUEST_FAILED_SENTINEL && (
              <Tooltip title={t("chat.share_card_tooltip")}>
                <Button
                  type="text" size="small" icon={<ShareAltOutlined />}
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                  onClick={() => onShare(m)}
                />
              </Tooltip>
            )}
            {/* Hide feedback affordances until the real chat_messages.id has
                replaced the in-flight Date.now() placeholder (≥ ~1.7e12); a click
                during the streaming-but-not-yet-saved window would PUT to a
                nonexistent id and 404 silently. */}
            {m.role === "assistant" && user && m.id < 1e12 && (
              <>
                <Tooltip title={t("chat.feedback_helpful")}>
                  <Button
                    type="text" size="small"
                    icon={m.feedback === "up" ? <LikeFilled /> : <LikeOutlined />}
                    style={{ color: m.feedback === "up" ? "var(--fj-accent)" : "var(--fj-ink-muted)", fontSize: 12 }}
                    onClick={() => onFeedback(m, "up")}
                  />
                </Tooltip>
                <Tooltip title={t("chat.feedback_not_helpful")}>
                  <Button
                    type="text" size="small"
                    icon={m.feedback === "down" ? <DislikeFilled /> : <DislikeOutlined />}
                    style={{ color: m.feedback === "down" ? "#e74c3c" : "var(--fj-ink-muted)", fontSize: 12 }}
                    onClick={() => onFeedback(m, "down")}
                  />
                </Tooltip>
              </>
            )}
            {m.role === "assistant" && m.content === REQUEST_FAILED_SENTINEL && (
              <Tooltip title={t("chat.retry")}>
                <Button
                  type="text" size="small" icon={<ReloadOutlined />}
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                  onClick={() => onRetry(m)}
                />
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export const MessageBubble = memo(
  MessageBubbleInner,
  (prev, next) =>
    prev.m === next.m &&
    prev.isStreaming === next.isStreaming &&
    prev.sending === next.sending &&
    prev.user === next.user,
);

export default function ChatPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { user } = useAuthStore();
  const [input, setInput] = useState("");
  const [masterId, setMasterId] = useState<string | null>(null);
  // 祖师长廊: opened from .chat-lineage-btn in the composer toolbar — the sole
  // entry point, in every state (empty and mid-thread alike).
  const [galleryOpen, setGalleryOpen] = useState(false);
  const { data: mastersData } = useQuery({
    queryKey: ["chat-masters"],
    queryFn: getMasters,
    staleTime: 60 * 60 * 1000, // curated data; effectively static
  });
  const selectedMaster = useMemo(
    () => mastersData?.find((m) => m.id === masterId) ?? null,
    [mastersData, masterId],
  );
  const [modelId, setModelId] = useState<string>(() => {
    if (typeof window === "undefined") return "deepseek:v4-pro";
    return window.localStorage.getItem("fojin.chat.modelId") || "deepseek:v4-pro";
  });
  const handleModelChange = useCallback((id: string) => {
    setModelId(id);
    try { window.localStorage.setItem("fojin.chat.modelId", id); } catch { /* ignore */ }
  }, []);
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [messages, setMessages] = useState<ChatMessageItem[]>(() => {
    // 登录归来恢复暂存对话（无论登录成功与否，回到 /chat 都不该丢对话）。
    // 读取放在惰性初始化（纯读取），removeItem 留给下面的挂载 effect。
    try {
      const raw = sessionStorage.getItem("fojin.chat.guestTranscript");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch { /* ignore */ }
    return [];
  });
  const [sending, setSending] = useState(false);
  // 游客转化钩子：游客拿到第一条 AI 回复后提示"登录可保存历史"。
  // 数据背景：月 730 chat 用户 vs 65 注册——多数游客不知道对话会丢。
  // 关闭后 14 天静默（localStorage）。
  const SAVE_HINT_KEY = "fojin.chat.saveHintDismissedAt";
  const [saveHintDismissed, setSaveHintDismissed] = useState(() => {
    try {
      const ts = Number(window.localStorage.getItem(SAVE_HINT_KEY));
      return Number.isFinite(ts) && Date.now() - ts < 14 * 86400_000;
    } catch { return false; }
  });
  const dismissSaveHint = useCallback(() => {
    setSaveHintDismissed(true);
    try { window.localStorage.setItem(SAVE_HINT_KEY, String(Date.now())); } catch { /* ignore */ }
  }, []);
  // CTA：先暂存游客对话再去登录——navigate 卸载本组件，不存就把用户
  // 想保存的对话当场销毁。LoginPage 读 returnTo 回跳，本组件 mount 恢复。
  const goLoginKeepingTranscript = useCallback(() => {
    try {
      sessionStorage.setItem("fojin.chat.guestTranscript", JSON.stringify(messages));
      sessionStorage.setItem("fojin.login.returnTo", "/chat");
    } catch { /* ignore */ }
    navigate("/login");
  }, [messages, navigate]);
  useEffect(() => {
    try { sessionStorage.removeItem("fojin.chat.guestTranscript"); } catch { /* ignore */ }
  }, []);
  const [attachments, setAttachments] = useState<ChatAttachmentMeta[]>([]);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("fojin.chat.sidebarCollapsed") === "1";
  });
  const setCollapsed = useCallback((next: boolean) => {
    setSidebarCollapsed(next);
    try { window.localStorage.setItem("fojin.chat.sidebarCollapsed", next ? "1" : "0"); } catch { /* ignore */ }
  }, []);
  const toggleSidebarCollapsed = () => setCollapsed(!sidebarCollapsed);
  const [sessionFilter, setSessionFilter] = useState("");
  // 收起态点搜索图标 → 展开侧栏并把光标送进搜索框。展开是异步的（输入框此刻还
  // 没挂载），所以用一个 ref 记下意图，等 sidebarCollapsed 落地后再 focus。
  // 用 ref 而不是 state：effect 里改 state 会被 React Compiler 判成
  // set-state-in-effect（本仓库是 error 级）。
  const sessionSearchRef = useRef<InputRef>(null);
  const wantSearchFocusRef = useRef(false);
  useEffect(() => {
    if (sidebarCollapsed || !wantSearchFocusRef.current) return;
    wantSearchFocusRef.current = false;
    sessionSearchRef.current?.focus();
  }, [sidebarCollapsed]);
  const handleRailSearch = useCallback(() => {
    wantSearchFocusRef.current = true;
    setCollapsed(false);
  }, [setCollapsed]);
  const [tabIndex, setTabIndex] = useState(-1);
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
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  const scrollTimerRef = useRef<number | null>(null);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);

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
    () => groupSessions(filteredSessions ?? []),
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
                // Behavioural quality signal: clicking a citation = engaging
                // with / trusting the cited source.
                if (typeof umami !== "undefined") {
                  umami.track("citation_click", { text_id: parsed.textId });
                }
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
                color: "var(--fj-highlight)",
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
              color: "var(--fj-highlight)",
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

  /** 自动跟随流式输出，但用户上滚阅读时不抢滚动条。
   *
   *  `atBottomRef` 而非 state：onToken 的回调闭包在 handleSendMessage 内创建，
   *  不随 state 更新重建 —— 读 state 只会永远拿到闭包创建时的旧值。
   *  force 用于「用户刚发出消息」与「点击回到底部」这两处必须跟到底的场景。 */
  const scrollToBottom = useCallback((force = false) => {
    if (!force && !atBottomRef.current) return;
    // 单个待触发句柄、覆盖式重排：token 频率约 20/s，每次都新起一个 setTimeout
    // 会在一条长答案里排出上千个定时器，而它们要做的是同一件事。
    if (scrollTimerRef.current !== null) clearTimeout(scrollTimerRef.current);
    scrollTimerRef.current = window.setTimeout(() => {
      scrollTimerRef.current = null;
      // 触发时必须复判。上面的守卫只在「调用时」判过一次，而真正滚动发生在
      // 100ms 之后 —— 这 100ms 里用户完全可能已经上滚。少了这次复判，存量定时器
      // 会把视口拽回底部，而那次程序化滚动又触发 scroll 事件把 atBottom 翻回真，
      // 跟随重新锁死 —— 「流式生成中途上滚重读」这个正主场景等于没修。
      if (!force && !atBottomRef.current) return;
      // behavior:"auto" 而非 "smooth"，两个理由：
      //   1. 按 token 频率重复调 smooth 会互相打断，而目标位置又一直在下移，
      //      动画永远追不上；
      //   2. 平滑动画途中的中间态会持续触发 scroll 事件，把下面的 atBottom 判定
      //      误翻成「用户已离开底部」，在动画走完之前就把跟随关掉。
      // （另有实测：在 CDP 驱动的标签页里 smooth 完全不推进。但那可能是自动化
      //  环境属性而非页面缺陷，所以不作为改动依据 —— 上面两条才是。）
      bottomRef.current?.scrollIntoView({ behavior: "auto" });
    }, 100);
  }, []);

  const handleMessagesScroll = useCallback(() => {
    const near = isNearBottom(messagesScrollRef.current);
    atBottomRef.current = near;
    setShowJumpToBottom((prev) => (prev === !near ? prev : !near));
  }, [setShowJumpToBottom]);

  const loadSession = async (sid: number) => {
    try {
      const data = await getChatSessionMessages(sid, 1, 50);
      setSessionId(sid);
      setMessages(data.messages);
      setCurrentPage(1);
      setHasOlderMessages(data.total > data.messages.length);
      // 加载历史会话时滚到顶部，让用户先看到问题。
      // behavior:"auto" 与上面的 scrollToBottom 保持一致 —— 平滑滚动在实测环境里
      // 是空操作，会让这个「滚到顶」的意图静默失效；而且这里是一次离散跳转，
      // 本来就不需要动画。
      setTimeout(() => {
        messagesTopRef.current?.scrollIntoView({ behavior: "auto" });
        // 跳到顶部后底部有大量未读内容，把「回到底部」按钮的状态同步过来 ——
        // 程序化滚动不一定触发 scroll 事件，不能只靠事件更新。
        handleMessagesScroll();
      }, 100);
    } catch {
      message.error(t("chat.load_session_failed"));
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
      message.error(t("chat.load_older_failed"));
    } finally {
      setLoadingOlder(false);
    }
  };

  const handleNewChat = () => {
    setSessionId(undefined);
    setMessages([]);
    setHasOlderMessages(false);
    setCurrentPage(1);
    // 必须显式复位这对状态。路径：打开历史会话 → loadSession 故意滚到顶、
    // atBottom 转假、↓ 按钮显示 → 点「新对话」→ messages 清空，但此时 scrollTop
    // 已是 0，内容收缩不会触发 scroll 事件（无需 clamp），所以按钮会留在空首屏
    // 右下角，点了什么也不会发生。handleDeleteSession 走的是同一条路。
    atBottomRef.current = true;
    setShowJumpToBottom(false);
  };

  // 声明在 handleDeleteSession 之前是必需的，不是排版偏好：删除当前会话要中断
  // 流，而 React Compiler 对「引用了声明在自己之后的绑定」会整支放弃编译，连带
  // 把同组件里其它 useCallback 的手写依赖数组判成不可保留（实测 4 个 error）。
  const [streamingId, setStreamingId] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const handleDeleteSession = (sid: number) => {
    Modal.confirm({
      title: t("chat.delete_session_title"),
      content: t("chat.delete_session_confirm"),
      okText: t("chat.delete"),
      cancelText: t("chat.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteChatSession(sid);
          if (sessionId === sid) {
            // 删掉正在生成的那个会话时必须先中断流。handleNewChat 只清 messages，
            // 而解锁 `sending` 的唯一出口是 onDone —— 不 abort 的话流会继续跑到
            // 天然结束（首字就要 6-18s，长答案更久），这期间 onToken 在空数组上
            // map（无声无息），输入框却因 `if (!msg || sending) return` 一直发不出
            // 东西。abort 会走 onError→onDone，把 sending/streamingId 一并复位。
            handleCancel();
            handleNewChat();
          }
          refetchSessions();
        } catch {
          message.error(t("chat.delete_failed"));
        }
      },
    });
  };

  // Rename runs through a real Modal rather than Modal.confirm: confirm()'s
  // content is rendered once and never re-rendered, so a controlled <Input>
  // inside it can't show what the user types.
  const [renameTarget, setRenameTarget] = useState<ChatSessionItem | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);

  const handleOpenRename = useCallback((s: ChatSessionItem) => {
    setRenameTarget(s);
    setRenameValue(s.title || "");
  }, []);

  const handleSubmitRename = useCallback(async () => {
    if (!renameTarget) return;
    const title = renameValue.trim();
    if (!title || title === renameTarget.title) {
      setRenameTarget(null);
      return;
    }
    setRenameSaving(true);
    try {
      await updateChatSession(renameTarget.id, { title });
      setRenameTarget(null);
      refetchSessions();
    } catch {
      message.error(t("chat.rename_failed"));
    } finally {
      setRenameSaving(false);
    }
  }, [renameTarget, renameValue, refetchSessions, t]);

  const handleTogglePin = useCallback(async (s: ChatSessionItem) => {
    try {
      await updateChatSession(s.id, { pinned: !s.pinned });
      refetchSessions();
    } catch {
      message.error(t("chat.pin_failed"));
    }
  }, [refetchSessions, t]);

  const handleFileChange = useCallback(async (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = e.target.files?.[0];
    // Reset so picking the same file again fires onChange.
    e.target.value = "";
    if (!file) return;
    if (attachments.length >= MAX_ATTACHMENTS) {
      message.warning(t("chat.attachments_max", { n: MAX_ATTACHMENTS }));
      return;
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      message.error(t("chat.attachment_too_large"));
      return;
    }
    setUploadingAttachment(true);
    try {
      const meta = await uploadChatAttachment(file);
      setAttachments((prev) => [...prev, meta]);
      message.success(t("chat.attachment_uploaded", { filename: meta.filename, n: meta.char_count }));
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response
          ?.data?.detail;
      message.error(detail || t("chat.upload_failed"));
    } finally {
      setUploadingAttachment(false);
    }
  }, [attachments.length, t]);

  const handleRemoveAttachment = useCallback((id: number) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
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
    // Snapshot attachment ids for this send. Don't clear chips yet —
    // if the stream errors before the backend marks them consumed,
    // keeping the chips lets the user retry by hitting Send again
    // (consumed_at IS NULL on the backend means re-use is safe).
    // Cleared in onDone (success path) below.
    const attachmentIdsForSend = attachments.map((a) => a.id);
    // 用户刚按下发送，无条件跟到底部：这一下是用户自己的动作，不是流式推动的
    atBottomRef.current = true;
    setShowJumpToBottom(false);
    scrollToBottom(true);

    const abortController = new AbortController();
    abortRef.current = abortController;

    // 5 min — must exceed backend LLM call budget (120s for reader page_content)
    // plus the fallback chain, otherwise reasoning models on long passages
    // abort mid-stream and surface as "请求失败，请重试".
    const timeoutId = setTimeout(() => abortController.abort(), 300_000);

    await sendChatMessageStream(msg, sessionId, masterId, {
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
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: correctedAnswer } : m,
          ),
        );
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
      onTrustStatus: (trustStatus: ChatTrustStatus) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, trust_status: trustStatus } : m,
          ),
        );
      },
      onSearching: (_searchMsg: string) => {
        // 搜索状态由初始占位符 "正在检索经文并生成回答..." 显示，不覆盖 content
      },
      onReasoning: () => {
        // 只当作活性信号：把等待期文案换成「正在推敲经文…（已思考 N 秒）」。
        // 秒数由前端自己计时，后端只负责证明「还在推进」——静态文案在 7-13 秒里
        // 读起来像卡死，一个在动的计数器才说明系统活着。
        // 与 onRetrieved 同一条承重约束：只写独立字段，绝不碰 content。
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.reasoningSince == null
              ? { ...m, reasoningSince: Date.now() }
              : m,
          ),
        );
      },
      onRetrieved: (retrieval) => {
        // 只写独立字段。绝不能写进 content —— THINKING_SENTINEL 是按身份比较的
        // 哨兵，onDone 里「流结束但从未收到 token → 转失败哨兵」的兜底靠它；
        // 一旦 content 被顶掉，用户会永远卡在假的「正在检索…」上且没有重试按钮。
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, retrieval } : m)),
        );
      },
      onMessageId: (realId: number) => {
        // Replace the in-flight Date.now() placeholder with the real
        // chat_messages.id so feedback / share buttons target the
        // correct row. Without this, every freshly-streamed message
        // would PUT feedback to a nonexistent id, which is why
        // production feedback rate is currently zero.
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, id: realId } : m)),
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
            m.id === assistantId && m.content === THINKING_SENTINEL
              ? { ...m, content: REQUEST_FAILED_SENTINEL }
              : m,
          ),
        );
      },
      onDone: () => {
        clearTimeout(timeoutId);
        abortRef.current = null;
        setStreamingId(0);
        setSending(false);
        // Empty completion: the stream ended without ever delivering a token
        // (and without an error frame — e.g. a bare `done`). If the bubble is
        // still the thinking placeholder, nothing will ever replace it and it
        // hangs on the fake "正在检索…" state forever. Convert it to the failure
        // sentinel so the existing retry button renders (mirrors onError). When
        // the backend already sent an `error`, onError ran first and the content
        // is no longer THINKING_SENTINEL, so this is a no-op — safe either way.
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.content === THINKING_SENTINEL
              ? { ...m, content: REQUEST_FAILED_SENTINEL }
              : m,
          ),
        );
        // Clear attachment chips only after successful stream completion.
        // On error the chips stay so the user can retry without re-uploading.
        if (attachmentIdsForSend.length > 0) {
          setAttachments((prev) => prev.filter((a) => !attachmentIdsForSend.includes(a.id)));
        }
        refetchQuota();
      },
    }, {
      signal: abortController.signal,
      hotQuestionId,
      // Only send model_id when the user has explicitly picked a non-default
      // model. Treating the default as "no override" lets _resolve_llm_config
      // pick the platform default for whatever LLM_API_URL is configured —
      // important for non-deepseek deployments where forcing a deepseek
      // catalog id would otherwise raise.
      modelId: modelId === "deepseek:v4-pro" ? null : modelId,
      attachmentIds: attachmentIdsForSend.length ? attachmentIdsForSend : null,
    });
  }, [sending, sessionId, masterId, modelId, user, attachments, refetchSessions, refetchQuota, queryClient, scrollToBottom, setShowJumpToBottom]);

  const handleSend = useCallback(async () => {
    await handleSendMessage(input);
  }, [input, handleSendMessage]);

  // Hoisted so MessageBubble can stay memoised. These depend on `messages`, so
  // their identity changes when the list does — but the memo comparator ignores
  // callback props, and the history is append-only, so a memoised historical
  // bubble keeps a closure over an older `messages` whose relevant prefix (the
  // preceding user question / the message to retry) is unchanged. Feedback uses
  // the functional setMessages form, so it's correct regardless of staleness.
  const handleShareMessage = useCallback((m: ChatMessageItem) => {
    const idx = messages.findIndex((x) => x.id === m.id);
    let question = "";
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].role === "user") { question = messages[i].content; break; }
    }
    setShareTarget({
      question: question || t("chat.share_default_question"),
      answer: parseFollowUps(m.content).cleanContent,
      sources: m.sources,
    });
  }, [messages, t]);

  const handleRetryMessage = useCallback((m: ChatMessageItem) => {
    const idx = messages.findIndex((x) => x.id === m.id);
    const userMsg = idx > 0 ? messages[idx - 1] : null;
    if (userMsg && userMsg.role === "user") {
      // Behavioural signal: the retry button only appears on a failed answer,
      // so this measures failure-retries (reliability), not regenerate-on-dislike.
      if (typeof umami !== "undefined") {
        umami.track("chat_retry");
      }
      setMessages((prev) => prev.filter((x) => x.id !== m.id && x.id !== userMsg.id));
      handleSendMessage(userMsg.content);
    }
  }, [messages, handleSendMessage]);

  const handleSourceClick = useCallback((s: ChatSource) => {
    // Behavioural signal, mirroring inline citation clicks: opening a source
    // from the persistent list is engagement with / trust in the retrieved text.
    if (typeof umami !== "undefined") {
      umami.track("source_click", { text_id: s.text_id });
    }
    const chunkIndex = s.chunk_index ?? -1;
    if (chunkIndex < 0) {
      // No chunk anchor (legacy / non-chunked source) — fall back to the reader,
      // same as the inline-citation legacy path.
      navigate(`/texts/${s.text_id}/read?juan=${s.juan_num}`);
      return;
    }
    setCitationTarget({
      textId: s.text_id,
      juanNum: s.juan_num,
      chunkIndex,
      titleZh: s.title_zh ?? "",
    });
  }, [navigate]);

  const handleFeedbackMessage = useCallback((m: ChatMessageItem, dir: "up" | "down") => {
    const newFeedback = m.feedback === dir ? null : dir;
    setMessages((prev) => prev.map((x) => x.id === m.id ? { ...x, feedback: newFeedback } : x));
    updateChatMessageFeedback(m.id, newFeedback as "up" | "down" | null).catch(() => {
      setMessages((prev) => prev.map((x) => x.id === m.id ? { ...x, feedback: m.feedback } : x));
    });
  }, []);

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
      const nextIndex = (tabIndex + 1) % tabSuggestions.length;
      setTabIndex(nextIndex);
      setInput(tabSuggestions[nextIndex]);
    };
    el.addEventListener("keydown", handler);
    return () => el.removeEventListener("keydown", handler);
  }, [tabSuggestions, tabIndex]);

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
      ? `关于《${source}》中的这段经文：\n\n> ${context}\n\n${q}` // i18n-exempt — chat message payload sent to the zh RAG pipeline
      : `关于这段经文：\n\n> ${context}\n\n${q}`; // i18n-exempt — chat message payload sent to the zh RAG pipeline
    handleSendMessage(msg);
  }, [searchParams, setSearchParams, handleSendMessage]);

  const handleExport = useCallback(() => {
    if (messages.length === 0) {
      message.warning(t("chat.export_empty"));
      return;
    }
    const sessionTitle = sessions?.find((s) => s.id === sessionId)?.title || t("chat.new_chat");
    const now = new Date().toLocaleString("zh-CN");
    let md = `# ${sessionTitle}\n${t("chat.export_time", { time: now })}\n\n`;
    for (const m of messages) {
      if (m.role === "user") {
        md += `## ${t("chat.export_role_user")}\n${m.content}\n\n`;
      } else {
        const { cleanContent } = parseFollowUps(m.content);
        md += `## ${t("chat.export_role_assistant")}\n${cleanContent}\n\n`;
        if (m.sources && m.sources.length > 0) {
          md += `**${t("chat.export_sources_label")}**\n`;
          for (const s of m.sources) {
            const title = s.title_zh
              ? t("chat.export_source_titled", { title: s.title_zh, n: s.juan_num })
              : t("chat.export_source_untitled", { id: s.text_id, n: s.juan_num });
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
        gap: 16,
      }}>

        {/* Mobile sidebar drawer (logged in only) */}
        {user && sidebarOpen && (
          <>
            <div className="chat-sidebar-overlay" onClick={() => setSidebarOpen(false)} />
            <div className="chat-sidebar-drawer">
              <Button icon={<PlusOutlined />} block onClick={() => { handleNewChat(); setSidebarOpen(false); }}>{t("chat.new_chat")}</Button>
              <div className="chat-session-list" style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
                {groupedSessions.map((group) => (
                  <div key={group.label}>
                    <div style={{ fontSize: 11, color: "var(--fj-ink-muted)", opacity: 0.6, padding: "6px 12px 2px", fontWeight: 500 }}>
                      {t(group.label)}
                    </div>
                    {group.items.map((s) => (
                      <SessionRow
                        key={s.id}
                        s={s}
                        active={sessionId === s.id}
                        onSelect={(id) => { loadSession(id); setSidebarOpen(false); }}
                        onRename={handleOpenRename}
                        onTogglePin={handleTogglePin}
                        onDelete={handleDeleteSession}
                      />
                    ))}
                  </div>
                ))}
              </div>
              <div className="chat-sidebar-foot">
                <Button icon={<SettingOutlined />} block type="text" size="small"
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                  onClick={() => { navigate("/profile?tab=apikey"); setSidebarOpen(false); }}>
                  {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
                </Button>
              </div>
            </div>
          </>
        )}

        {/* Sidebar (desktop, logged in only) */}
        {user && <div style={{ width: sidebarCollapsed ? 48 : 220, flexShrink: 0, display: "flex", flexDirection: "column", gap: 8, transition: "width 0.18s ease" }}
             className="chat-sidebar"
             data-collapsed={sidebarCollapsed || undefined}>
          <Tooltip title={sidebarCollapsed ? t("chat.expand_sidebar") : t("chat.collapse_sidebar")} placement="right">
            <Button
              type="text"
              size="small"
              className={sidebarCollapsed ? "chat-rail-btn" : undefined}
              icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={toggleSidebarCollapsed}
              aria-label={sidebarCollapsed ? t("chat.expand_sidebar") : t("chat.collapse_sidebar")}
              style={{ alignSelf: sidebarCollapsed ? "center" : "flex-end", color: "var(--fj-ink-muted)" }}
            />
          </Tooltip>
          {/* 收起态是一条图标轨：按钮去掉边框、统一 32×32 居中。带边框的方块在
              48px 宽的窄轨里会显得又挤又重，这也是它和 ChatGPT 观感差最多的地方。 */}
          <Tooltip title={sidebarCollapsed ? t("chat.new_chat") : ""} placement="right">
            <Button
              icon={<PlusOutlined />}
              type={sidebarCollapsed ? "text" : "default"}
              className={sidebarCollapsed ? "chat-rail-btn" : undefined}
              block={!sidebarCollapsed}
              onClick={handleNewChat}
              aria-label={t("chat.new_chat")}
            >
              {!sidebarCollapsed && t("chat.new_chat")}
            </Button>
          </Tooltip>
          {/* 搜索在收起态原本整个消失。这里给它一个入口：点开即展开并聚焦。
              显示条件与展开态的搜索框严格一致，否则会展开出一个没有搜索框的侧栏。 */}
          {sidebarCollapsed && sessions && sessions.length > 5 && (
            <Tooltip title={t("chat.search_sessions_label")} placement="right">
              <Button
                type="text"
                className="chat-rail-btn"
                icon={<SearchOutlined />}
                onClick={handleRailSearch}
                aria-label={t("chat.search_sessions_label")}
              />
            </Tooltip>
          )}
          {!sidebarCollapsed && sessions && sessions.length > 5 && (
            <Input
              ref={sessionSearchRef}
              placeholder={t("chat.search_sessions")}
              size="small"
              allowClear
              value={sessionFilter}
              onChange={(e) => setSessionFilter(e.target.value)}
              style={{ marginTop: 4, fontSize: 12 }}
            />
          )}
          {!sidebarCollapsed && <div className="chat-session-list" style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
            {groupedSessions.map((group) => (
              <div key={group.label}>
                <div style={{ fontSize: 11, color: "var(--fj-ink-muted)", opacity: 0.6, padding: "6px 12px 2px", fontWeight: 500 }}>
                  {t(group.label)}
                </div>
                {group.items.map((s) => (
                  <SessionRow
                    key={s.id}
                    s={s}
                    active={sessionId === s.id}
                    onSelect={loadSession}
                    onRename={handleOpenRename}
                    onTogglePin={handleTogglePin}
                    onDelete={handleDeleteSession}
                  />
                ))}
              </div>
            ))}
          </div>}
          {/* 收起态原本连 Key 状态一起消失了 —— 但「有没有配 Key」直接决定问答
              能不能用，是这条轨上唯一必须留住的状态。压成一个图标沉到底部。 */}
          {sidebarCollapsed && (
            <>
              <div style={{ flex: 1 }} />
              <Tooltip
                placement="right"
                title={keyStatus?.has_api_key
                  ? `${t("chat.key_configured")} (${keyStatus.provider})`
                  : t("chat.configure_key")}
              >
                <Button
                  type="text"
                  className="chat-rail-btn"
                  icon={<SettingOutlined />}
                  onClick={() => navigate("/profile?tab=apikey")}
                  aria-label={t("chat.configure_key")}
                />
              </Tooltip>
            </>
          )}
          {!sidebarCollapsed && (
            <div className="chat-sidebar-foot">
              <Button icon={<SettingOutlined />} block type="text" size="small"
                style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                onClick={() => navigate("/profile?tab=apikey")}>
                {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
              </Button>
            </div>
          )}
        </div>}

        {/* Chat area */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {/* Chat header: mobile toggle + export */}
          <div style={{ display: "flex", marginBottom: 4 }}>
            <div className="chat-column-inner" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              {user ? (
                <Button
                  className="chat-mobile-toggle"
                  type="text"
                  icon={<MenuOutlined />}
                  onClick={() => setSidebarOpen(true)}
                >
                  {t("chat.session_list")}
                </Button>
              ) : <div />}
              {messages.length > 0 && (
                <Tooltip title={t("chat.export_tooltip")}>
                  <Button
                    type="text"
                    icon={<DownloadOutlined />}
                    onClick={handleExport}
                    style={{ color: "var(--fj-ink-muted)" }}
                  />
                </Tooltip>
              )}
            </div>
          </div>
          {/* Messages */}
          <div
            ref={messagesScrollRef}
            onScroll={handleMessagesScroll}
            style={{ flex: messages.length === 0 ? "1 1 auto" : 1, overflow: "auto", padding: "16px 0" }}
          >
            <div className={messages.length === 0 ? "chat-column-inner chat-msgs-empty" : "chat-column-inner"}>
            <div ref={messagesTopRef} />
            {messages.length === 0 && <div className="chat-hero-lead" />}
            {hasOlderMessages && (
              <div style={{ textAlign: "center", marginBottom: 12 }}>
                <Button size="small" type="text" loading={loadingOlder} onClick={loadOlderMessages}
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}>
                  {t("chat.load_older")}
                </Button>
              </div>
            )}
            {messages.length === 0 && (
              <div style={{ textAlign: "center", padding: "0 24px 14px", color: "var(--fj-ink-muted)" }}>
                {selectedMaster && (
                  <div style={{ display: "flex", justifyContent: "center", marginBottom: 10 }}>
                    <MasterSeal text={Array.from(selectedMaster.name_zh).slice(0, 2).join("")} size={40} />
                  </div>
                )}
                <div style={{ fontSize: 22, fontFamily: '"Noto Serif SC", serif', marginBottom: 6 }}>
                  {t("chat.title")}
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                  {t("chat.subtitle")}
                  <br />{t("chat.subtitle2")}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                m={m}
                isStreaming={streamingId === m.id}
                sending={sending}
                user={user}
                markdownComponents={markdownComponents}
                onSuggestionClick={handleSendMessage}
                onShare={handleShareMessage}
                onRetry={handleRetryMessage}
                onFeedback={handleFeedbackMessage}
                onSourceClick={handleSourceClick}
              />
            ))}
            {/* Streaming cursor is shown inline via ▌ in the message bubble */}
            <div ref={bottomRef} />
            {/* 「回到底部」：sticky + height:0 的锚点，贴在滚动视口下沿且不占布局
                空间 —— 不用给滚动容器套 position:relative 的外层包裹，避免扰动
                空状态那套「上下撑高块均分」的 flex 链。 */}
            <div className="chat-jump-anchor">
              {showJumpToBottom && (
                <button
                  type="button"
                  className="chat-jump-bottom"
                  aria-label={t("chat.jump_to_bottom")}
                  title={t("chat.jump_to_bottom")}
                  onClick={() => {
                    atBottomRef.current = true;
                    setShowJumpToBottom(false);
                    scrollToBottom(true);
                  }}
                >
                  <DownOutlined />
                </button>
              )}
            </div>
            </div>
          </div>

          {/* Input */}
          {/* 顶部横线必须画在 840px 的内列上，不能画在满宽外层：根容器改满宽后
              外层宽达 chat area 全宽（1920 屏上 1620px），横线会比它要分隔的对话列
              左右各悬空约 390px，成为一条两端不着地的孤线。 */}
          <div style={{ paddingBottom: 12 }}>
            <div
              className="chat-column-inner"
              style={{
                paddingTop: 12,
                borderTop: messages.length === 0 ? undefined : "1px solid rgba(217,208,193,0.5)",
              }}
            >
            {/* 游客转化钩子：拿到第一条成功回复后提示保存历史（可关闭，14 天
                静默）。固定在输入区上方而非消息流末尾：消息流尾部的 mount 受
                scrollToBottom 时序影响可能落在视口外，用户永远看不到。
                排除失败哨兵回复——在报错下面劝人"保存这段对话"很荒谬。 */}
            {!user && !sending && !saveHintDismissed
              && messages.some((m) => m.role === "assistant" && m.content !== REQUEST_FAILED_SENTINEL) && (
              <Alert
                type="info"
                showIcon
                closable
                onClose={dismissSaveHint}
                style={{ marginBottom: 8, fontSize: 12 }}
                message={
                  <span>
                    {t("chat.guest_save_hint")}
                    <a onClick={goLoginKeepingTranscript} style={{ marginLeft: 4 }}>
                      {t("chat.guest_save_hint_cta")}
                    </a>
                  </span>
                }
              />
            )}
            {/* 宗风 selector lives in the composer toolbar below (.chat-lineage-btn).
                It used to be a grey <Select> reading "通用助手" — the 15 master
                personas, this product's sharpest differentiator, hid inside it. It
                then became a full-width row to state the chosen lineage plainly;
                the toolbar control keeps that plain text label while giving the
                row's vertical space back to the first screen. Wording is
                "依此宗风解经", never "和祖师聊天" — you are choosing an
                interpretive lens, not a chat character. */}
            <DraggableModal
              open={galleryOpen}
              onCancel={() => setGalleryOpen(false)}
              width={880}
              title={t("chat.gallery_title")}
            >
              <MasterGallery
                selectedId={masterId}
                onSelect={(id) => {
                  setMasterId(id);
                  setGalleryOpen(false);
                }}
                onOpenSource={(textId, juan) =>
                  window.open(`/texts/${textId}/read?juan=${juan}`, "_blank", "noopener")
                }
              />
            </DraggableModal>
            {!user && !keyStatus?.has_api_key && quota && quota.remaining >= 0 && (
              <Alert
                message={<span>{t("chat.quota_info", { limit: quota.limit, remaining: quota.remaining })}<a onClick={() => navigate("/login")}>{t("chat.login")}</a>{t("chat.login_quota_hint")}</span>}
                type={quota.remaining <= 2 ? "warning" : "info"} showIcon closable
                style={{ marginBottom: 8, fontSize: 12 }}
              />
            )}
            <div className="chat-input-shell">
              <Input.TextArea
                ref={(instance) => { inputRef.current = instance?.resizableTextArea?.textArea ?? null; }}
                value={input}
                onChange={(e) => { setInput(e.target.value); setTabIndex(-1); }}
                onPressEnter={(e) => {
                  if (e.shiftKey) return;
                  e.preventDefault();
                  handleSend();
                }}
                placeholder={tabSuggestions.length > 0 ? `${tabSuggestions[(tabIndex + 1) % tabSuggestions.length]}    ⇥ Tab    ⇧⏎ ${t("chat.newline_hint")}` : t("chat.input_placeholder")}
                disabled={sending}
                autoSize={{ minRows: 2, maxRows: 8 }}
                variant="borderless"
                style={{ fontFamily: '"Noto Serif SC", serif', fontSize: 16, resize: "none" }}
              />
              {attachments.length > 0 && (
                <div className="chat-input-chips">
                  {attachments.map((a) => (
                    <Tag
                      key={a.id}
                      closable
                      onClose={() => handleRemoveAttachment(a.id)}
                      color="default"
                      style={{ margin: 0 }}
                    >
                      {a.filename} · {(a.size_bytes / 1024).toFixed(1)} KB
                    </Tag>
                  ))}
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept={ATTACHMENT_ACCEPT}
                onChange={handleFileChange}
                style={{ display: "none" }}
              />
              <div className="chat-input-toolbar">
                <Tooltip title={t("chat.attachment_tooltip")}>
                  <Button
                    type="text"
                    size="small"
                    icon={uploadingAttachment ? <Spin size="small" /> : <PlusOutlined />}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingAttachment || attachments.length >= MAX_ATTACHMENTS}
                  />
                </Tooltip>
                <Tooltip title={t("chat.change_master")}>
                  <Button
                    type="text"
                    size="small"
                    className="chat-lineage-btn"
                    onClick={() => setGalleryOpen(true)}
                  >
                    {/* 不放印章：18px 的 MasterSeal 字号只有 6px（size*0.32），两个汉字
                        挤成一团认不出，而紧邻的文字标签已经把名号写明了。变化的文字
                        本身就是「已选宗风」的指示器。印章留在空状态 hero 里 —— 那里
                        它 40px、字号 13px 可读，且不与名号重复（hero 标题是产品名）。 */}
                    <span>{selectedMaster ? selectedMaster.name_zh : t("chat.general_assistant")}</span>
                    <DownOutlined style={{ fontSize: 10 }} />
                  </Button>
                </Tooltip>
                <ChatModelSelector value={modelId} onChange={handleModelChange} />
                <span className="chat-input-spacer" />
                {sending ? (
                  <Button
                    danger
                    icon={<StopOutlined />}
                    onClick={handleCancel}
                  >
                    {t("chat.stop")}
                  </Button>
                ) : (
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}
                  >
                    {t("chat.send", "发送")}
                  </Button>
                )}
              </div>
            </div>
              {selectedMaster && (
                <div className="mg-disclaimer" style={{ marginTop: 8 }}>
                  {t("chat.master_disclaimer")}
                </div>
              )}
              {messages.length === 0 && (welcomeCardsData?.questions?.length ?? 0) > 0 && (
                <>
                  <div className="chat-hero-cards">
                    {(welcomeCardsData?.questions ?? []).map((card: HotQuestionCard) => (
                      <button
                        key={card.id}
                        type="button"
                        className="chat-hero-card"
                        onClick={() => handleSendMessage(card.display_text, { hotQuestionId: card.id })}
                      >
                        <span className="chat-hero-card-tag">
                          {t(`chat.hot_question_category_${HOT_QUESTION_CATEGORY_SLUGS[card.category]}`, card.category)}
                        </span>
                        <span>{card.display_text}</span>
                      </button>
                    ))}
                  </div>
                  <div style={{ textAlign: "center", marginTop: 8 }}>
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
                </>
              )}
            </div>
          </div>
          {messages.length === 0 && <div className="chat-hero-trail" />}
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
      <Modal
        open={renameTarget !== null}
        title={t("chat.rename_session_title")}
        okText={t("chat.save")}
        cancelText={t("chat.cancel")}
        confirmLoading={renameSaving}
        onOk={handleSubmitRename}
        onCancel={() => setRenameTarget(null)}
        destroyOnHidden
        width={400}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={handleSubmitRename}
          placeholder={t("chat.rename_placeholder")}
          maxLength={200}
          autoFocus
        />
      </Modal>
    </>
  );
}
