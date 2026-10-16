import { lazy, Suspense, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { ArrowLeftOutlined, MenuUnfoldOutlined } from "@ant-design/icons";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { CitationTarget } from "./CitationDrawer";
import CitationPanel from "./CitationPanel";
import { useNarrowViewport } from "../hooks/useNarrowViewport";
import { extractAnswerCitations, findAnswerForTarget, type AnswerCitation } from "../utils/answerCitations";
import "../styles/chat-citation-panel.css";

const CitationDrawer = lazy(() => import("./CitationDrawer"));

/** 常驻面板的断点。低于它维持原样（只在点开引文时出抽屉）：对话列在 1280 以下
 *  再让出一整列给常驻面板就太挤了。改这里同时看 chat-citation-panel.css。 */
export const CITATION_SIDEBAR_QUERY = "(min-width: 1280px)";

const COLLAPSED_KEY = "fojin-citation-sidebar-collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(v: boolean) {
  try {
    localStorage.setItem(COLLAPSED_KEY, v ? "1" : "0");
  } catch {
    /* private mode / blocked storage — the panel just won't remember */
  }
}

function track(event: string, data: Record<string, string | number>) {
  if (typeof umami !== "undefined") umami.track(event, data);
}

/** 选中的回答用 created_at 认，不用 id：流中途 message_id 会把占位 id 换成真 id
 *  （只有登录用户会换），按 id 记的选中会在那一刻失配。created_at 在换 id 时原样保留。 */
interface Selection {
  key: string;
  /** 选中时的「最新回答」。出现更新的回答（用户又问了一句）选中即作废，回到最新。 */
  latestKey: string;
}

interface Props {
  messages: ChatMessageItem[];
  sending: boolean;
  target: CitationTarget | null;
  onTargetChange: (t: CitationTarget | null) => void;
  width: number;
  onResizeStart: (e: ReactMouseEvent) => void;
}

/**
 * /chat 右侧那一列。宽屏（≥1280）常驻：默认列出当前回答的引文（CitationPanel），
 * 点任一条就在同一位置换成原文对照（CitationDrawer），顶部有返回列表。窄屏与旧行为
 * 完全一致：只有点开引文时才出现抽屉。
 */
export default function CitationSidebar({ messages, sending, target, onTargetChange, width, onResizeStart }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const navigate = useNavigate();
  const wide = useNarrowViewport(CITATION_SIDEBAR_QUERY);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [selection, setSelection] = useState<Selection | null>(null);

  const answers = messages.filter((m) => m.role === "assistant");
  const latest = answers.length > 0 ? answers[answers.length - 1] : null;
  const latestKey = latest?.created_at ?? "";
  const selected =
    (selection && selection.latestKey === latestKey
      ? answers.find((m) => m.created_at === selection.key)
      : null) ?? latest;

  // 点了某条回答里的内联引文 → 面板跟到那条回答。按 props 变化调整 state 的
  // React 惯用法（渲染期比较上一次的值），不用 effect。
  const [seenTarget, setSeenTarget] = useState<CitationTarget | null>(target);
  if (seenTarget !== target) {
    setSeenTarget(target);
    if (target) {
      const owner = findAnswerForTarget(messages, target, lang, selected);
      if (owner && owner !== selected) setSelection({ key: owner.created_at, latestKey });
    }
  }

  const toggleCollapsed = (next: boolean) => {
    setCollapsed(next);
    writeCollapsed(next);
    track("citation_panel_toggle", { state: next ? "collapsed" : "expanded" });
  };

  const openCitation = (c: AnswerCitation) => {
    track("citation_click", { text_id: c.target.textId, via: "panel" });
    if (c.target.chunkIndex < 0) {
      navigate(`/texts/${c.target.textId}/read?juan=${c.target.juanNum}`);
      return;
    }
    onTargetChange(c.target);
  };

  const openSource = (s: ChatSource) => {
    track("source_click", { text_id: s.text_id, via: "panel" });
    const chunkIndex = s.chunk_index ?? -1;
    if (chunkIndex < 0) {
      navigate(`/texts/${s.text_id}/read?juan=${s.juan_num}`);
      return;
    }
    onTargetChange({ textId: s.text_id, juanNum: s.juan_num, chunkIndex, titleZh: s.title_zh ?? "" });
  };

  const drawer = target ? (
    <Suspense fallback={<div style={{ padding: 40, textAlign: "center" }}>…</div>}>
      <CitationDrawer target={target} onClose={() => onTargetChange(null)} />
    </Suspense>
  ) : null;

  const column = (children: ReactNode) => (
    <>
      <div className="chat-citation-divider" onMouseDown={onResizeStart} />
      {/* complementary 而不是 dialog：这是个**非模态**侧栏，左边的对话仍可读可点
          （见 global.css 里 .chat-citation-panel 的说明）。标成 dialog 会让读屏
          以为进入了模态上下文。 */}
      <div
        className="chat-citation-panel"
        role="complementary"
        aria-label={t("reader.citation.title")}
        style={{ width }}
      >
        {children}
      </div>
    </>
  );

  // 窄屏 / 中屏：原样。
  if (!wide) return target ? column(drawer) : null;

  // 宽屏，但还没有任何回答（空态首页）：不占列。
  if (!latest && !target) return null;

  if (collapsed && !target) {
    const count = selected
      ? extractAnswerCitations(selected.content, selected.sources, lang).length
      : 0;
    return (
      <button
        type="button"
        className="chat-cpanel-rail"
        aria-label={t("chat.cpanel.expand")}
        title={t("chat.cpanel.expand")}
        onClick={() => toggleCollapsed(false)}
      >
        <MenuUnfoldOutlined />
        <span className="chat-cpanel-rail-label">{t("chat.cpanel.rail_label")}</span>
        {count > 0 && <span className="chat-cpanel-rail-count">{count}</span>}
      </button>
    );
  }

  if (target) {
    return column(
      <>
        {!collapsed && (
          <button type="button" className="chat-cpanel-back" onClick={() => onTargetChange(null)}>
            <ArrowLeftOutlined /> {t("chat.cpanel.back_to_list")}
          </button>
        )}
        {drawer}
      </>,
    );
  }

  return column(
    <CitationPanel
      message={selected}
      isLatest={selected === latest}
      pending={sending && selected === latest}
      onOpenCitation={openCitation}
      onOpenSource={openSource}
      onCollapse={() => toggleCollapsed(true)}
      onShowLatest={() => setSelection(null)}
    />,
  );
}
