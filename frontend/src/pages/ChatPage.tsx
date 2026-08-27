import { useState, useRef, useCallback, useMemo, useEffect, useSyncExternalStore, lazy, Suspense, memo, type ReactNode } from "react";
import { useNavigate, useSearchParams, Link } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Input, Button, message, Alert, Tooltip, Modal, Tag, Spin, Dropdown } from "antd";
import type { InputRef } from "antd";
import Markdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { CITATION_URL_SCHEME, injectCitationLinks } from "../utils/citationLinks";
import { formatResponseSeconds } from "../utils/responseTiming";
import { localizeHan } from "../utils/hanScript";
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
  DownloadOutlined,
  StopOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  ReloadOutlined,
  RedoOutlined,
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
} from "@ant-design/icons";
const ShareCard = lazy(() => import("../components/ShareCard"));
const CitationDrawer = lazy(() => import("../components/CitationDrawer"));
import ChatModelSelector from "../components/ChatModelSelector";
import MasterGallery, { MasterSeal } from "../components/MasterGallery";
import {
  RailSidebarIcon,
  RailNewChatIcon,
  RailSearchIcon,
  RailChatsIcon,
  RailSettingsIcon,
} from "../components/RailIcons";
import DraggableModal from "../components/DraggableModal";
import ReasoningExcerpt from "../components/ReasoningExcerpt";
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
import {
  sessionExpired,
  sessionExpiredServer,
  subscribeSessionExpired,
  useAuthStore,
  type UserProfile,
} from "../stores/authStore";
import { expectedFirstTokenSeconds, recordFirstTokenMs } from "../utils/firstTokenStats";
import type { TextId } from "../types/branded";

// 登录用户的额度提示只在快用完时出现。常驻一个「今日剩余 198 次」是纯噪音 ——
// 而毫无预警地撞上上限、直接吃一个错误，才是真正会让人懵的那种体验。
const LOW_QUOTA_THRESHOLD = 20;

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
/** 一次发送的来源。空 = 用户主动提的新问题（记 "chat"）；其余是派生动作，各记各的事件。 */
type SendOrigin = "retry" | "continue" | "regenerate";

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
  /** 只有最后一条回答可以「重新生成」：从中间分叉要作废后面的历史，语义复杂而没人需要。 */
  isLast?: boolean;
  /** 本机最近几次首字耗时的中位数（秒）；null = 没有样本，等待期不显示预期。 */
  expectedFirstTokenS?: number | null;
  user: UserProfile | null;
  markdownComponents: Components;
  onSuggestionClick: (q: string) => void;
  onShare: (m: ChatMessageItem) => void;
  onRetry: (m: ChatMessageItem) => void;
  onContinue: (m: ChatMessageItem) => void;
  onRegenerate: (m: ChatMessageItem) => void;
  onFeedback: (m: ChatMessageItem, dir: "up" | "down") => void;
  onSourceClick: (source: ChatSource, phase?: "retrieved") => void;
}

/** One chat message row, memoised on (m, isStreaming, sending, user). A streaming
    token swaps only the streaming message's object identity (onToken does {...m}),
    so only THAT bubble re-renders — history is skipped. Previously the markdown
    preprocessing (parseFollowUps / injectCitationLinks / tightenLists + the
    react-markdown render) re-ran for every historical message on every token,
    which was the dominant "越聊越卡" jank in long conversations. */
function MessageBubbleInner({
  m, isStreaming, sending, user, markdownComponents, isLast = false, expectedFirstTokenS = null,
  onSuggestionClick, onShare, onRetry, onContinue, onRegenerate, onFeedback, onSourceClick,
}: MessageBubbleProps) {
  // Read t here (not as a prop): on a mid-conversation language switch, i18next's
  // subscription re-renders the bubble — which memo does NOT block, since memo
  // only short-circuits parent-driven, prop-equal re-renders — so tooltips/toasts
  // update immediately, without `t` having to enter the comparator (and without
  // risking the per-token memo skip if t's identity weren't stable).
  const { t, i18n } = useTranslation();
  // CBETA 的 title_zh 恒为繁体；经名该用哪种字形由读者的界面语言决定，不由语料决定。
  // 只作用于**经名**——答案正文（尤其是通过了逐字核验的引文）一个字都不改写。
  const lang = i18n.language;
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
    () => (isAssistantText ? tightenLists(injectCitationLinks(cleanContent, m.sources, lang)) + (isStreaming ? " ▌" : "") : ""),
    [isAssistantText, cleanContent, m.sources, isStreaming, lang],
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
              <>
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
                        {/* 有 refs（新后端）就给可点 chip：等答案的同时先读原文。
                            点开走 onSourceClick 的 retrieved 相位 —— 与流末的「参考经文」
                            同一条抽屉。旧后端没有 refs 时退回纯文本经名。 */}
                        {m.retrieval.refs && m.retrieval.refs.length > 0
                          ? m.retrieval.refs.map((r) => (
                              <SourceChipButton
                                key={`${r.text_id}:${r.juan_num}`}
                                label={t("reader.citation.title_with_juan", { title: localizeHan(r.title_zh ?? "", lang), n: r.juan_num })}
                                onClick={() => onSourceClick(
                                  { text_id: r.text_id as TextId, juan_num: r.juan_num, chunk_index: r.chunk_index ?? undefined, chunk_text: "", score: 0, title_zh: r.title_zh ?? undefined },
                                  "retrieved",
                                )}
                              />
                            ))
                          : m.retrieval.titles.map((tt) => (
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
                {/* 等待预期：本机最近几次首字耗时的中位数。首字要等 24-180 秒，不知道
                    该等多久的人等不及就手动停止再发（记成断流）。没有样本不显示 ——
                    宁可不说，也不编一个「通常 1-2 分钟」。 */}
                {expectedFirstTokenS != null && (
                  <div className="chat-wait-expectation">
                    {t("chat.expected_wait", { n: expectedFirstTokenS })}
                  </div>
                )}
                {/* 思考过程片段活窗（打字机组件）。只在哨兵分支里渲染 —— 正文
                    一到（content 被换掉）整块随分支消失，这是渲染层的保险；
                    onToken 另清 reasoningText，两道各自独立。 */}
                {m.reasoningText ? <ReasoningExcerpt text={m.reasoningText} /> : null}
              </>
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
                      <SourceChipButton
                        key={`${s.text_id}:${s.juan_num}`}
                        label={t("reader.citation.title_with_juan", { title: localizeHan(s.title_zh ?? "", lang), n: s.juan_num })}
                        onClick={() => onSourceClick(s)}
                      />
                    ))}
                  </div>
                )}
                {suggestions.length > 0 && !sending && (
                  <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {suggestions.map((q, i) => (
                      // 必须是原生 <button>：浏览器只为真正的可交互元素把 Enter/空格
                      // 合成成 click。span[role=button] 看着一模一样，键盘用户和读屏
                      // 用户却永远触发不了这些追问 —— 而它们是继续对话的主要入口。
                      // fontFamily 要显式 inherit：button 不继承字体族，去掉这行会在
                      // 一堆 Noto Serif 里冒出一颗系统默认字体的胶囊。用长属性而不是
                      // font 简写——简写会连带重置 fontSize，得靠对象键序才能救回来。
                      <button
                        key={i}
                        type="button"
                        onClick={() => onSuggestionClick(q)}
                        style={{
                          display: "inline-block", padding: "4px 12px", borderRadius: 14,
                          border: "1px solid var(--fj-gold, #b08d57)", color: "var(--fj-gold, #b08d57)",
                          fontFamily: "inherit",
                          // button 的 UA 默认是 text-align:center。单行时看不出来，
                          // 长追问换行后每一行都会居中——和改动前的 span 不一样。
                          textAlign: "start",
                          fontSize: 12, cursor: "pointer", background: "transparent", transition: "all 0.2s", lineHeight: 1.6,
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(176,141,87,0.1)"; e.currentTarget.style.color = "var(--fj-accent)"; e.currentTarget.style.borderColor = "var(--fj-accent)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--fj-gold, #b08d57)"; e.currentTarget.style.borderColor = "var(--fj-gold, #b08d57)"; }}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )
          ) : (
            m.content
          )}
        </div>
        {/* 被 max_tokens 截断的回答：一句提示 + 一键续写。只在流结束后显示；失败哨兵不显示。
            按钮文案保持四个字 —— antd 会给恰好两个汉字的按钮插空格，按名字找按钮会恒假。 */}
        {m.role === "assistant" && m.truncated && !isStreaming
          && m.content !== REQUEST_FAILED_SENTINEL && (
          <div className="chat-truncated">
            <span>{t("chat.truncated_hint")}</span>
            <Button size="small" disabled={sending} onClick={() => onContinue(m)}>
              {t("chat.continue")}
            </Button>
          </div>
        )}
        {/* Action buttons outside bubble */}
        {m.content !== THINKING_SENTINEL && !isStreaming && (
          <div style={{ marginTop: 4, display: "flex", gap: 4, alignItems: "center" }}>
            {/* 响应耗时。只对本次会话生成的回答显示：totalMs 的有无就是那个判据，
                历史消息读回来时为空。失败的回答不显示 —— 给一句「请求失败」标上
                用了多少秒，是拿噪音充信息。 */}
            {m.role === "assistant" && m.totalMs != null
              && m.content !== REQUEST_FAILED_SENTINEL && (
              <Tooltip title={t("chat.timing.tooltip")}>
                <span
                  style={{
                    color: "var(--fj-ink-muted)", fontSize: 12,
                    marginRight: 4, whiteSpace: "nowrap",
                    fontVariantNumeric: "tabular-nums", cursor: "default",
                  }}
                >
                  <ClockCircleOutlined style={{ marginRight: 4 }} />
                  {m.firstTokenMs != null && (
                    <>{t("chat.timing.first_token", { n: formatResponseSeconds(m.firstTokenMs) })}
                      {" · "}</>
                  )}
                  {t("chat.timing.total", { n: formatResponseSeconds(m.totalMs) })}
                </span>
              </Tooltip>
            )}
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
            {/* 「重新生成」只给最后一条成功的回答。图标用 Redo 而不是 Reload：Reload
                是失败重试的图标，测试按 .anticon-reload 找它，两者不能撞。 */}
            {m.role === "assistant" && isLast && m.content !== REQUEST_FAILED_SENTINEL && (
              <Tooltip title={t("chat.regenerate")}>
                <Button
                  type="text" size="small" icon={<RedoOutlined />}
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                  disabled={sending}
                  onClick={() => onRegenerate(m)}
                />
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** 经文 chip：流末「参考经文」行与等待期 retrieved.refs 共用一个样子、一条抽屉。 */
function SourceChipButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "3px 10px", borderRadius: 12,
        border: "1px solid rgba(176,141,87,0.5)", background: "rgba(176,141,87,0.06)",
        color: "var(--fj-ink-muted)", fontSize: 12, lineHeight: 1.6, cursor: "pointer", transition: "all 0.2s",
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(176,141,87,0.16)"; e.currentTarget.style.color = "var(--fj-accent)"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(176,141,87,0.06)"; e.currentTarget.style.color = "var(--fj-ink-muted)"; }}
    >
      {label}
    </button>
  );
}

export const MessageBubble = memo(
  MessageBubbleInner,
  (prev, next) =>
    prev.m === next.m &&
    prev.isStreaming === next.isStreaming &&
    prev.sending === next.sending &&
    prev.user === next.user &&
    prev.isLast === next.isLast &&
    prev.expectedFirstTokenS === next.expectedFirstTokenS,
);

export default function ChatPage() {
  const navigate = useNavigate();
  // 必须声明在 loadSession / handleNewChat 之前：引用声明在自己之后的绑定会让
  // React Compiler 对整个组件放弃编译，并把同组件里其它 useCallback 的手写依赖
  // 判成不可保留（见 PR #1077 里踩过的 4 个 lint error）。
  const [searchParams, setSearchParams] = useSearchParams();
  const { t, i18n } = useTranslation();
  const { user, token } = useAuthStore();
  // 不带 context 的 ?q= 是这个输入框的**初值**，不是一次副作用。
  //
  // 在此之前它被彻底丢掉：下面那个 effect 的守卫是
  // `if (!q || !context) return`，于是辞典那颗「问小津」按钮
  // （navigate(`/chat?q=因果`)）送来的词一个都没到过对话框 —— 用户点完只看见
  // 一个空白的 /chat，没有报错、没有日志、没有埋点。30 天里 dictionary→chat
  // 只有 71 次跳转，落地即失望。
  //
  // 只填不发是有意的：来的是一个词头而不是一句问题，用户多半要再改一笔；而且
  // 这种 URL 会被收藏、被分享，自动发送等于每打开一次就烧一次配额。
  // 也因此 ?q= 不必从地址栏抹掉 —— 它已经被消费成初值，留着还能让链接可复现。
  const [input, setInput] = useState(
    // send=1（小津气泡）与带 context 的 ?q= 都会被下面的 effect 直接发送，
    // 不能再灌进输入框，否则消息发出后草稿里还躺着一份同文。
    () => (searchParams.get("context") || searchParams.get("send") === "1" ? "" : searchParams.get("q")) ?? "",
  );
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
  // 等待预期：本机最近几次首字耗时的中位数；每次首字到达后更新。
  const [expectedFirstTokenS, setExpectedFirstTokenS] = useState<number | null>(
    () => expectedFirstTokenSeconds(),
  );
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

  // The key carries the user id so logging in or out refetches instead of
  // serving the other identity's cached answer. With a constant key and the
  // global 5-minute staleTime, a guest quota fetched before login stayed fresh
  // across the login and drove the logged-in banner — this is why the wrong
  // "剩余 10 次" survived signing in.
  //
  // `token` is in the key for a second reason, found the hard way (user 638,
  // 2026-08-18): the id alone separates 游客 from 本人, but NOT 本人-with-a-dead
  // -ticket from 本人-who-just-signed-back-in. /chat/quota answers an expired
  // token with 200 + `authenticated: false` rather than 401, so that "you are a
  // guest" reply gets cached under the *user's* key; signing in again produced
  // the identical key and the 5-minute staleTime served it straight back —
  // the 「登录状态已过期」 banner outlived the very login that fixed it. The
  // quota answer is only true for the credential it was fetched with, so the
  // credential belongs in the key. A renewed token (#1198) changes it too and
  // costs one extra 2ms fetch per rotation; that is the right trade.
  const { data: quota, refetch: refetchQuota } = useQuery({
    queryKey: ["chatQuota", user?.id ?? "anon", token ?? "anon"],
    queryFn: getChatQuota,
  });

  // 登录态是否"自己死掉了"。存在 sessionStorage 里（见 authStore），用
  // useSyncExternalStore 订阅——这是 React 读取外部可变源的正规做法，置位那一刻
  // 就重渲染，不必蹭别的 state 变化。
  const expired = useSyncExternalStore(
    subscribeSessionExpired,
    sessionExpired,
    sessionExpiredServer,
  );

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

  /** 深链 effect（下方）是否已经代用户自动发送过。挂在这里（syncSessionParam
   *  之前）是因为它的闭包要读这个 ref —— 用它区分「自动发送后残留的 ?q=」
   *  与「用户手动收藏的裸 ?q=」，前者清、后者留。 */
  const autoSentRef = useRef(false);

  /** 把「当前在读哪个会话」写进 URL（?s=）。
   *
   * 两个用处：① 去 /profile 配 Key 再返回时能落回原会话 —— 此前 sessionId 只是
   * 组件 state，一离开 /chat 就没了；② 顺带让单条对话可收藏。
   * 一律 replace：不然每切一次会话就往浏览历史塞一条，后退键会变得很难用。 */
  const syncSessionParam = useCallback((sid: number | undefined) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      // ⚠️ prev 不是实时 URL：react-router 的函数式 updater 读的是创建这个闭包
      // 那次渲染的 location。onSessionId 的闭包诞生于带 ?q=&send=（或 context）
      // 的首次渲染 —— 深链 effect 早已把它们 replace 掉，这里的 prev 又原样
      // 还魂，刷新这条 URL 就会重发一次、重扣一次配额（生产实测）。一次性的
      // 入场参数在写入会话号时一并清掉；裸 ?q= 的「只填不发、可收藏」不受影响
      // —— 那条路不发送、不产生会话号，根本走不到这里。
      next.delete("send");
      next.delete("context");
      next.delete("source");
      if (autoSentRef.current) next.delete("q");
      if (sid === undefined) next.delete("s");
      else next.set("s", String(sid));
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  /** silent：按 URL 恢复时用。链接可能是旧的（会话已删、或本就不属于自己，
   *  后端会 403/404），一进页面就弹错误提示只是噪音，退回空白首屏即可。 */
  const loadSession = useCallback(async (sid: number, silent = false) => {
    try {
      const data = await getChatSessionMessages(sid, 1, 50);
      setSessionId(sid);
      syncSessionParam(sid);
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
      syncSessionParam(undefined);   // 别把打不开的 id 留在地址栏里
      if (!silent) message.error(t("chat.load_session_failed"));
    }
  }, [syncSessionParam, handleMessagesScroll, t]);

  // 按 ?s= 恢复会话。**只在挂载后判这一次**，之后 URL 里的 s 一律视为本页面自己
  // 写进去的，不再回头去"恢复"。
  //
  // 守卫必须在读 s 之前就置位。此前它只在真的拿到 s 之后才置位，于是干净进入
  // /chat（没有 s）时守卫一直是 false；等流回传 session_id、syncSessionParam 把
  // ?s= 写进 URL，searchParams 一变这个 effect 就重跑，把**刚写进去的那个 id**
  // 当成历史会话去拉消息 —— 而此刻助手回答还没落库，拿回空数组，setMessages 把
  // 正在流式的对话整个替换掉：页面退回空白首屏，而「停止」按钮还在（sending 没
  // 人动）。用户看到的就是"问第一个问题问到一半，整个对话没了"。
  // 只发生在每次页面加载后的第一问 —— 此后守卫为真。
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const raw = searchParams.get("s");
    if (!raw) return;
    const sid = Number(raw);
    if (!Number.isInteger(sid) || sid <= 0) return;
    // 放进微任务里调：loadSession 第一句就是 await，实际不会同步 setState，但
    // React Compiler 只看调用点、不看 await，会判成 set-state-in-effect（error 级）。
    // 挪进回调既符合规则本意（"外部状态变化时在回调里 setState"），也不改变时序。
    queueMicrotask(() => { loadSession(sid, true); });
  }, [searchParams, loadSession]);

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
    syncSessionParam(undefined);
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
      const res = (err as { response?: { status?: number; data?: unknown } })?.response;
      // detail 只在后端自己回 JSON 时才有。两种情况下它不是字符串：反向代理
      // 挡下请求时 body 是 HTML 错误页；FastAPI 的 422 里 detail 是数组。
      // 不判类型就 `detail || 兜底`，前者掉进兜底、后者把 [object Object] 甩给用户。
      const raw = (res?.data as { detail?: unknown } | undefined)?.detail;
      const detail = typeof raw === "string" ? raw : undefined;
      // 413 常常不是后端发的：nginx 的 client_max_body_size 先于应用层生效，
      // 回的是一张没有 detail 的 HTML 页。此时说「稍后重试」是误导 —— 重试多少
      // 次都一样，用户需要知道的是文件太大。
      const fallback =
        res?.status === 413 ? t("chat.attachment_too_large") : t("chat.upload_failed");
      message.error(detail || fallback);
    } finally {
      setUploadingAttachment(false);
    }
  }, [attachments.length, t]);

  const handleRemoveAttachment = useCallback((id: number) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const handleSendMessage = useCallback(async (
    text: string,
    options?: { hotQuestionId?: number | null; origin?: SendOrigin },
  ) => {
    const msg = text.trim();
    if (!msg || sending) return;
    const hotQuestionId = options?.hotQuestionId ?? null;

    // Umami: 只有用户主动发的新问题才记 "chat"（问题截前 30 字）。重试走的是同一条
    // 函数，此前也无条件记一次 —— 30 天里 94 次 chat_retry 每次都把「提问数」多灌
    // 一次，而重发率、断流率的分母正是 chat。派生动作各记各的事件（见 CHAT_EVENTS）。
    if (typeof umami !== "undefined" && !options?.origin) {
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

    // 断流埋点的两个本地计数。放在闭包里而不是 state / ref：每次发送都要一份
    // 全新的，且绝不能在 setMessages 的 updater 里做统计（StrictMode 会跑两遍）。
    //
    // 为什么非要前端来记：中途断流在服务端量不出来。docker logs 里那行
    // "LLM stream broke mid-stream" 随每次部署重建容器而清空；DB 侧也查不到 ——
    // _save_messages 把 user+assistant 两行一起写，断流时一行都不落，而游客
    // 根本不建 session、完全不落库。只有前端知道「这一条流吐没吐过 token」。
    let tokenCount = 0;
    let sawError = false;

    // 响应耗时。和上面两个计数同理放在闭包里：每次发送要一份全新的，且绝不能在
    // setMessages 的 updater 里读时钟（StrictMode 下 updater 会跑两遍）。
    // Date.now() 只在回调里读、从不在渲染期读 —— 渲染期读时钟会被 React
    // Compiler 判为不纯（「已思考 N 秒」那处 :412 已经栽过一次）。
    const startedAt = Date.now();
    let firstTokenMs: number | null = null;

    // 这条回答在 messages 里的 id 会**在流中途变**：后端在 done 之前先发
    // message_id（services/chat.py:1356 → :1361），onMessageId 用真实的
    // chat_messages.id 换掉 Date.now() 占位符。所以任何在 message_id 之后还要
    // 找到这条消息的回调，都必须认这个活变量，不能再认 assistantId ——
    // 2026-08-21 响应耗时上线当天就栽在这里：onDone 按占位符去找，匹配不上，
    // 耗时一个字都没写进去。而游客不落库、收不到 message_id，id 一直是占位符，
    // 所以以游客身份怎么试都是好的，只有登录用户看不到。
    let liveAssistantId = assistantId;
    // 所有「改这条回答」的 setMessages 都必须走这里：id 在**回调时**捕获，而不是在
    // updater 里读活变量。updater 是延后执行的 —— trust_status / sources / message_id
    // / done 常落在同一个 XHR chunk、同一个同步 tick 里到达，等 updater 跑起来时
    // onMessageId 已经把 liveAssistantId 改成真 id，而消息本身还挂着占位符；在
    // updater 里比较活变量就会去找一个此刻不存在的 id，把 sources 与 trust_status
    // 静默丢掉（生产实锤：登录用户流结束时引文不可点、无信任行，刷新后才有）。
    const patchLive = (patch: (m: ChatMessageItem) => ChatMessageItem) => {
      const id = liveAssistantId;
      setMessages((prev) => prev.map((m) => (m.id === id ? patch(m) : m)));
    };

    await sendChatMessageStream(msg, sessionId, masterId, {
      onToken: (content: string) => {
        tokenCount += 1;
        if (firstTokenMs === null) {
          firstTokenMs = Date.now() - startedAt;
          recordFirstTokenMs(firstTokenMs);
          setExpectedFirstTokenS(expectedFirstTokenSeconds());
        }
        patchLive((m) => {
          const current = m.content === THINKING_SENTINEL ? "" : m.content;
          // reasoningText 随首个 token 销毁：被模型自己推翻的中间结论
          // 不能留在屏幕上（渲染层另有一道保险，两道各自独立）。
          return { ...m, content: current + content, reasoningText: null };
        });
        scrollToBottom();
      },
      onCitationCorrection: (correctedAnswer: string) => {
        // Backend contract (see send_message_stream): no `token` events
        // arrive after `citation_correction`. If that contract is ever
        // broken, a late chunk would append to the corrected answer and
        // re-introduce the hallucination we just stripped.
        patchLive((m) => ({ ...m, content: correctedAnswer }));
      },
      onSources: (sources: ChatSource[]) => {
        patchLive((m) => ({ ...m, sources }));
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
        patchLive((m) => ({ ...m, trust_status: trustStatus }));
      },
      onSearching: (_searchMsg: string) => {
        // 搜索状态由初始占位符 "正在检索经文并生成回答..." 显示，不覆盖 content
      },
      onReasoning: (r) => {
        // 计时（已思考 N 秒）+ 思考片段活窗。等待的 30-180 秒是买质量的钱
        // （削档已被 90 题 eval 证否），能改的只有等待的感受 —— 推理文本是
        // 现成的可读中文，此前整条丢掉。
        // 与 onRetrieved 同一条承重约束：只写独立字段，绝不碰 content。
        patchLive((m) => {
          const next = { ...m };
          if (next.reasoningSince == null) next.reasoningSince = Date.now();
          if (r.text) {
            // 全量累加、不截尾：打字机组件按前缀吐字，截尾会让前缀失配、
            // 整窗重排跳动。上限由推理预算天然封顶（≤ 数万字，流结束即清），
            // 显示端的活窗高度由 CSS clip 管。
            next.reasoningText = (next.reasoningText ?? "") + r.text;
          }
          return next;
        });
        // 活窗把气泡向下撑高 ~100px，而钉底发生在发送时 —— 不跟滚的话，已可
        // 滚动的对话里活窗整段等待期落在折叠线以下，token 一到又被销毁，用户
        // 从头到尾看不见它（对抗审查实锤的失效场景）。scrollToBottom 非 force
        // 自带「贴底才跟随 + 触发时复判」，用户上滚重读时不会被拽回。
        scrollToBottom();
      },
      onRetrieved: (retrieval) => {
        // 只写独立字段。绝不能写进 content —— THINKING_SENTINEL 是按身份比较的
        // 哨兵，onDone 里「流结束但从未收到 token → 转失败哨兵」的兜底靠它；
        // 一旦 content 被顶掉，用户会永远卡在假的「正在检索…」上且没有重试按钮。
        patchLive((m) => ({ ...m, retrieval }));
      },
      onMessageId: (realId: number) => {
        // Replace the in-flight Date.now() placeholder with the real
        // chat_messages.id so feedback / share buttons target the
        // correct row. Without this, every freshly-streamed message
        // would PUT feedback to a nonexistent id, which is why
        // production feedback rate is currently zero.
        // 旧 id 先捕获进 updater 的闭包再改活变量：updater 是延后执行的，
        // 若先改了活变量，它会去找一个还不存在的 id。
        const placeholderId = liveAssistantId;
        liveAssistantId = realId;
        setMessages((prev) =>
          prev.map((m) => (m.id === placeholderId ? { ...m, id: realId } : m)),
        );
      },
      onSessionId: (newSessionId: number) => {
        if (!sessionId) {
          setSessionId(newSessionId);
          syncSessionParam(newSessionId);
          if (user) refetchSessions();
        }
      },
      onTruncated: () => {
        // 截断是产品缺陷的信号（普通问答上限 2000 tokens，对贴长段求白话翻译不够），
        // 单独记一档；分母是 chat + answer_continue。上限先不动，量一周再定（R2b）。
        if (typeof umami !== "undefined") umami.track("answer_truncated");
        patchLive((m) => ({ ...m, truncated: true }));
      },
      onError: (errMsg: string, code?: string) => {
        sawError = true;
        // mid_stream 与 no_token 必须分开：后者前端已能自愈（转失败哨兵 + 给出
        // 重试按钮），前者留下的是一段看似完整的半截答案 —— 没有失败标记、没有
        // 重试按钮，而分享/复制照常可用。分开记才知道真正要修的那部分占多少。
        //
        // 但 stage 只说了「什么时候断的」，没说「为什么断」，而两者的处置完全
        // 不同：配额用完是产品决策，上游超时是运维，空回复是模型选型。带上后端
        // 的 code 才分得开。
        //
        // 「用户按了停止」必须排除：abort 走的也是 onError，而推理模型要等
        // 24-180 秒才吐第一个字（生产日志实测最长 182.95s），等不及手动停止
        // 正是最典型的动作 —— 记进去就是把用户的不耐烦算成系统故障。
        if (typeof umami !== "undefined" && code !== "cancelled") {
          umami.track("chat_stream_error", {
            stage: tokenCount > 0 ? "mid_stream" : "no_token",
            reason: code ?? "unknown",
          });
        }
        message.error(errMsg);
        patchLive((m) =>
          m.content === THINKING_SENTINEL ? { ...m, content: REQUEST_FAILED_SENTINEL } : m,
        );
      },
      onDone: () => {
        clearTimeout(timeoutId);
        abortRef.current = null;
        setStreamingId(0);
        setSending(false);
        // 流结束了，却既没有 error 帧也没有任何 token —— 后端发了个光秃秃的 done。
        // 下面那段兜底会把气泡转成失败哨兵，但服务端不会为此留下任何痕迹，
        // 所以这里单独记一档。sawError 拦住重复计数。
        if (!sawError && tokenCount === 0 && typeof umami !== "undefined") {
          umami.track("chat_stream_error", { stage: "empty_done", reason: "silent_done" });
        }
        // Empty completion: the stream ended without ever delivering a token
        // (and without an error frame — e.g. a bare `done`). If the bubble is
        // still the thinking placeholder, nothing will ever replace it and it
        // hangs on the fake "正在检索…" state forever. Convert it to the failure
        // sentinel so the existing retry button renders (mirrors onError). When
        // the backend already sent an `error`, onError ran first and the content
        // is no longer THINKING_SENTINEL, so this is a no-op — safe either way.
        // 同一次 map 里盖上耗时：totalMs 的有无就是「这条是本次会话生成的」，
        // 历史消息读回来时为空，于是不会显示一个没人计过的时间。失败与空回复
        // 也照记 —— 渲染层负责不给失败哨兵显示耗时，判据留在一处就够了。
        const totalMs = Date.now() - startedAt;
        patchLive((m) => {
          const settled = m.content === THINKING_SENTINEL
            ? { ...m, content: REQUEST_FAILED_SENTINEL }
            : m;
          return { ...settled, firstTokenMs, totalMs };
        });
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
      regenerate: options?.origin === "regenerate",
      // Only send model_id when the user has explicitly picked a non-default
      // model. Treating the default as "no override" lets _resolve_llm_config
      // pick the platform default for whatever LLM_API_URL is configured —
      // important for non-deepseek deployments where forcing a deepseek
      // catalog id would otherwise raise.
      modelId: modelId === "deepseek:v4-pro" ? null : modelId,
      attachmentIds: attachmentIdsForSend.length ? attachmentIdsForSend : null,
    });
  }, [sending, sessionId, masterId, modelId, user, attachments, refetchSessions, refetchQuota, queryClient, scrollToBottom, setShowJumpToBottom, syncSessionParam]);

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
      handleSendMessage(userMsg.content, { origin: "retry" });
    }
  }, [messages, handleSendMessage]);

  const handleRegenerateMessage = useCallback((m: ChatMessageItem) => {
    const idx = messages.findIndex((x) => x.id === m.id);
    const userMsg = idx > 0 ? messages[idx - 1] : null;
    if (!userMsg || userMsg.role !== "user") return;
    // 对答案不满意才会点：30 天里约 88 次「隔一会儿原样再发同一问题」就是没有这个
    // 按钮的代价。替换而不是追加 —— 后端把旧的那对从上下文里去掉（否则模型多半
    // 照抄），新答案落库时删旧的；游客不落库，只在视图里替换。
    if (typeof umami !== "undefined") umami.track("chat_regenerate");
    setMessages((prev) => prev.filter((x) => x.id !== m.id && x.id !== userMsg.id));
    handleSendMessage(userMsg.content, { origin: "regenerate" });
  }, [messages, handleSendMessage]);

  const handleContinueMessage = useCallback((m: ChatMessageItem) => {
    // 带上中断处的结尾：游客不落库、没有服务端历史，光说「继续」模型接不上；
    // 登录用户虽有历史，结尾也帮模型对准断点、少重复。按钮随即收起，免得连点两次
    // 发出两条一样的续写 —— 续写若失败，失败气泡自带重试。
    if (typeof umami !== "undefined") umami.track("answer_continue");
    const tail = parseFollowUps(m.content).cleanContent.trimEnd().slice(-80);
    setMessages((prev) => prev.map((x) => (x.id === m.id ? { ...x, truncated: false } : x)));
    handleSendMessage(t("chat.continue_prompt", { tail }), { origin: "continue" });
  }, [handleSendMessage, t]);

  const handleSourceClick = useCallback((s: ChatSource, phase?: "retrieved") => {
    // Behavioural signal, mirroring inline citation clicks: opening a source
    // from the persistent list is engagement with / trust in the retrieved text.
    // phase=retrieved：答案还没来、用户先点开了原文 —— 单独可分，别混进流末的点击。
    if (typeof umami !== "undefined") {
      umami.track("source_click", phase ? { text_id: s.text_id, phase } : { text_id: s.text_id });
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
  useEffect(() => {
    const q = searchParams.get("q");
    const context = searchParams.get("context");
    const source = searchParams.get("source");
    // 自动发送只认两种显式意图：带 context（阅读页「问小津」）和 send=1
    // （首页小津气泡——用户在气泡里已经按过回车，落地再要他点一次等于吞掉
    // 那次回车）。裸 ?q= 仍然只填不发，由上面 input 的 useState 初值消费——
    // 那种 URL 会被收藏分享，自动发送等于每打开一次烧一次配额。别在这儿
    // setInput：react-hooks/set-state-in-effect 会红（实测），而且多绕一帧。
    const send = searchParams.get("send") === "1";
    if (!q || (!context && !send) || autoSentRef.current) return;

    autoSentRef.current = true;
    // 发送前把参数从 URL 抹掉：send=1 的链接刷新/回退时不该重发重扣配额。
    setSearchParams({}, { replace: true });

    const msg = context
      ? source
        ? `关于《${source}》中的这段经文：\n\n> ${context}\n\n${q}` // i18n-exempt — chat message payload sent to the zh RAG pipeline
        : `关于这段经文：\n\n> ${context}\n\n${q}` // i18n-exempt — chat message payload sent to the zh RAG pipeline
      : q;
    handleSendMessage(msg);
  }, [searchParams, setSearchParams, handleSendMessage]);

  /** 去配 Key。带上来源与当前会话，好让 /profile 给出一个能真正返回原会话的按钮 ——
   *  sessionId 只是组件 state，离开 /chat 就没了，光有「返回」会落在空白新对话上。 */
  const goConfigureKey = useCallback(() => {
    const q = new URLSearchParams({ tab: "apikey", from: "chat" });
    if (sessionId !== undefined) q.set("s", String(sessionId));
    navigate(`/profile?${q.toString()}`);
  }, [navigate, sessionId]);

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
              // 导出的 .md 是给人读的：经名跟随导出时的界面语言，与用户屏幕上
              // 刚看到的 chip 一致，否则文件里的《雜阿含經》对不上页面的《杂阿含经》。
              ? t("chat.export_source_titled", { title: localizeHan(s.title_zh, i18n.language), n: s.juan_num })
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
  }, [messages, sessions, sessionId, t, i18n.language]);

  return (
    <>
      <Helmet><title>{t("chat.page_title")}</title></Helmet>
      {/* className 是必需的，不是装饰：这个外壳的 display:flex 写在行内样式里，
          而行内样式没有任何 CSS 选择器够得到 —— 于是 global.css 里那条
          「移动端把引用面板铺满宽度」的规则结构上不可能生效为「堆叠」，面板
          只会在同一行里把对话列挤成 0 宽。给它一个类名，断点才改得动
          flex-direction。 */}
      {/* 空态打上 chat-shell--empty：手机上（≤768px）据此放开锁高，让标题/横幅/输入框/
          建议卡片按内容铺开、整页滚动；有对话后去掉，恢复锁高 + 输入框钉底。 */}
      <div className={`chat-shell${messages.length === 0 ? " chat-shell--empty" : ""}`}>

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
                  onClick={() => { goConfigureKey(); setSidebarOpen(false); }}>
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
              icon={sidebarCollapsed ? <RailSidebarIcon /> : <MenuFoldOutlined />}
              onClick={toggleSidebarCollapsed}
              aria-label={sidebarCollapsed ? t("chat.expand_sidebar") : t("chat.collapse_sidebar")}
              style={{ alignSelf: sidebarCollapsed ? "center" : "flex-end", color: "var(--fj-ink-muted)" }}
            />
          </Tooltip>
          {/* 收起态是一条图标轨：按钮去掉边框、统一 32×32 居中。带边框的方块在
              48px 宽的窄轨里会显得又挤又重，这也是它和 ChatGPT 观感差最多的地方。 */}
          <Tooltip title={sidebarCollapsed ? t("chat.new_chat") : ""} placement="right">
            <Button
              icon={sidebarCollapsed ? <RailNewChatIcon /> : <PlusOutlined />}
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
                icon={<RailSearchIcon />}
                onClick={handleRailSearch}
                aria-label={t("chat.search_sessions_label")}
              />
            </Tooltip>
          )}
          {/* 最近聊天：展开侧栏露出会话列表。与"展开侧栏"按钮动作相同、意图不同 ——
              一个是"开合面板"，一个是"我的旧对话在哪"。ChatGPT 同样两个都给。
              不设显示条件：一个会话都没有时展开出空列表，正好告诉新用户以后
              会话会出现在这里。 */}
          {sidebarCollapsed && (
            <Tooltip title={t("chat.recent_chats")} placement="right">
              <Button
                type="text"
                className="chat-rail-btn"
                icon={<RailChatsIcon />}
                onClick={() => setCollapsed(false)}
                aria-label={t("chat.recent_chats")}
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
                  icon={<RailSettingsIcon />}
                  onClick={goConfigureKey}
                  aria-label={t("chat.configure_key")}
                />
              </Tooltip>
            </>
          )}
          {!sidebarCollapsed && (
            <div className="chat-sidebar-foot">
              <Button icon={<SettingOutlined />} block type="text" size="small"
                style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                onClick={goConfigureKey}>
                {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
              </Button>
            </div>
          )}
        </div>}

        {/* Chat area */}
        <div className="chat-main-column" style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
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
                <div className="chat-hero-title">
                  {t("chat.title")}
                </div>
                {/* 只留「可核对」这一句。原来上面还有一行「可以问我关于佛经内容、
                    佛教历史、经典翻译等问题」，那是第三次重复：下方四张卡片
                    （白话翻译/经文解读/对比辨析/佛教史话）把同样三个类目演示得更
                    具体、还可点，输入框 placeholder 也在轮播真实例题。而这一句是
                    整个首屏唯一说明「答案可以被核对」的地方 —— 它是差异点，
                    且措辞是「你可以核对」而非「我保证正确」。 */}
                <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                  {t("chat.subtitle")}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <MessageBubble
                key={m.id}
                m={m}
                isStreaming={streamingId === m.id}
                sending={sending}
                isLast={i === messages.length - 1}
                expectedFirstTokenS={expectedFirstTokenS}
                user={user}
                markdownComponents={markdownComponents}
                onSuggestionClick={handleSendMessage}
                onShare={handleShareMessage}
                onRetry={handleRetryMessage}
                onContinue={handleContinueMessage}
                onRegenerate={handleRegenerateMessage}
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
            {/* 过期者此刻确实是游客，但对他说「登录后额度更多」是答非所问 ——
                他刚才就是登录状态。这一条让位给下面那句过期说明。 */}
            {!user && !expired && !keyStatus?.has_api_key && quota && quota.remaining >= 0 && (
              <Alert
                message={<span>{t("chat.quota_info", { limit: quota.limit, remaining: quota.remaining })}<a onClick={() => navigate("/login")}>{t("chat.login")}</a>{t("chat.login_quota_hint")}</span>}
                type={quota.remaining <= 2 ? "warning" : "info"} showIcon closable
                style={{ marginBottom: 8, fontSize: 12 }}
              />
            )}
            {/* 「登录态是自己死的」这件事，只能靠标记传下来：401 拦截器会先
                logout() 把 user 清空，此后 user==null 与「从没登录过」完全一样。
                这里不能只判 user —— 实测那样横幅只在 401 到达前闪一下就没了。

                为什么必须说出来：/chat/quota 对过期 token 返回的是 200 + 游客
                数字（不是 401），而 /chat/stream 走同一套鉴权，过期后配额降为
                按 IP 共享的 10 次、会话不再存进账号。用户以为自己登着录，实际
                提问正被算作游客、历史正在丢。 */}
            {/* 判据只有一个：**服务端此刻说不认识这张票**。`expired` 标记只负责在
                这个前提下区分「你的登录刚死」和「你本来就是游客」，它自己没有
                宣布过期的权力——它存在 sessionStorage 里，活得过页面重载、也活得过
                浏览器「恢复上次标签页」，而全项目只有 setAuth/logout 会清它。让它
                单独驱动横幅，一条残留标记就能在一个完全有效的会话上长期说谎
                （2026-08-18 user 638 反复看到的正是这个）。 */}
            {quota && !quota.authenticated && (expired || !!user) && (
              <Alert
                message={
                  <span>
                    {t("chat.session_expired")}
                    {/* 复用游客 CTA 的那条路：先暂存当前对话再跳登录。过期期间
                        发出的消息本来就没进账号，直接 navigate 会当场销毁它们。
                        returnTo 也在同一个函数里写好（sessionStorage，见 LoginPage）。 */}
                    <a onClick={goLoginKeepingTranscript}>
                      {t("chat.session_expired_action")}
                    </a>
                  </span>
                }
                type="warning" showIcon closable
                style={{ marginBottom: 8, fontSize: 12 }}
              />
            )}
            {/* 登录用户此前在这里什么都看不到 —— 撞到上限是毫无预警的。
                remaining 对自带 Key 的用户是 -1，所以 >= 0 已经把他们排除掉了。
                authenticated 这一项不能省：token 过期时后端回的是匿名配额，
                少了它就会把游客的 10 次当成这位登录用户的余额报出去。 */}
            {user && quota && quota.authenticated && quota.remaining >= 0 && quota.remaining <= LOW_QUOTA_THRESHOLD && (
              <Alert
                message={
                  <span>
                    {t("chat.quota_low", { remaining: quota.remaining })}
                    <a onClick={goConfigureKey}>{t("chat.quota_low_action")}</a>
                  </span>
                }
                type={quota.remaining <= 3 ? "error" : "warning"} showIcon closable
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
                <ChatModelSelector value={modelId} onChange={handleModelChange} onConfigureKey={goConfigureKey} />
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
            {/* complementary 而不是 dialog：这是个**非模态**侧栏，左边的对话仍可读可点
                （见 global.css 里 .chat-citation-panel 的说明）。标成 dialog 会让读屏
                以为进入了模态上下文。整页此前只有一个 <main>，补上这个 landmark 后，
                读屏用户才能直接跳到原文对照区，而不必从对话里一路 Tab 过来。 */}
            <div
              className="chat-citation-panel"
              role="complementary"
              aria-label={t("reader.citation.title")}
              style={{ width: citationPanelWidth }}
            >
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
