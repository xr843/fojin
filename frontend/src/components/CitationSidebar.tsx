import { lazy, Suspense, useEffect, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeftOutlined } from "@ant-design/icons";
import type { ChatMessageItem, ChatSource } from "../api/client";
import type { CitationTarget } from "./CitationDrawer";
import CitationPanel from "./CitationPanel";
import { useNarrowViewport } from "../hooks/useNarrowViewport";
import { findAnswerForTarget, isExplicitCitationOf, type AnswerCitation } from "../utils/answerCitations";
import "../styles/chat-citation-panel.css";

const CitationDrawer = lazy(() => import("./CitationDrawer"));

/** 并排面板的断点。≥1280 时右栏与对话列并排、展开状态记在 localStorage；
 *  低于它右栏仍是原来的抽屉位（769–1279 并排、≤768 堆到对话下方，见 global.css），
 *  展开只在本页有效、不记忆 —— 手机上一进来就被半屏面板盖住不可接受。 */
export const CITATION_SIDEBAR_QUERY = "(min-width: 1280px)";

/** 宽屏「用户手动展开过」的记忆。默认 false = 收起（DeepSeek 式：靠回答下方的入口按需展开）。
 *
 *  换了新键而不是沿用 #1344 的 `fojin-citation-sidebar-collapsed`：那个键缺省 = 展开，
 *  老用户大多没有它，沿用就会把他们留在旧默认里。旧键不再读取。 */
export const OPEN_KEY = "fojin-citation-sidebar-open";

function readOpen(): boolean {
  try {
    return localStorage.getItem(OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

function writeOpen(v: boolean) {
  try {
    localStorage.setItem(OPEN_KEY, v ? "1" : "0");
  } catch {
    /* private mode / blocked storage — the panel just won't remember */
  }
}

function track(event: string, data: Record<string, string | number>) {
  if (typeof umami !== "undefined") umami.track(event, data);
}

/** 「打开某条回答的引文面板」的请求。每次点击是一个新对象（按身份比较，不带计数）。
 *  用 created_at 认回答，不用 id：流中途 message_id 会把占位 id 换成真 id（只有登录用户会换），
 *  created_at 在换 id 时原样保留。 */
export interface CitationPanelRequest {
  key: string;
}

/** 选中的回答，同样按 created_at 认。 */
interface Selection {
  key: string;
  /** 选中时的「最新回答」。出现更新的回答（用户又问了一句）选中即作废，回到最新。 */
  latestKey: string;
}

/** 渲染期决定的「面板被打开了」，交给 effect 去打点 / 记忆（渲染期不做副作用）。 */
interface OpenEvent {
  /** null = 面板本来就开着，不算一次「打开」，不打点。 */
  via: "chip" | "inline" | "source" | null;
  /** 宽屏是否记住「展开」：只有入口胶囊（用户明确要看列表）记，点内联引文顺带打开的不记。 */
  remember: boolean;
}

interface Props {
  messages: ChatMessageItem[];
  sending: boolean;
  target: CitationTarget | null;
  onTargetChange: (t: CitationTarget | null) => void;
  /** 回答下方入口胶囊的点击（AnswerCitationEntry）。 */
  request: CitationPanelRequest | null;
  width: number;
  onResizeStart: (e: ReactMouseEvent) => void;
}

/**
 * /chat 右侧那一列，默认收起。三种打开方式：
 *  - 回答下方的入口胶囊（request）→ 列出**那条**回答的引文（CitationPanel）；宽屏记住「展开」；
 *  - 点正文内联引文 / 参考经文 / 定位卡片（target）→ 直接进原文对照（CitationDrawer），
 *    顶部「返回引文列表」回到该回答的列表；这种打开不记忆；
 *  - 宽屏上次手动展开过 → 进页即展开。
 * 关闭只有一个语义：右上角 ×（列表视图在 CitationPanel 顶栏，原文视图在 CitationDrawer 顶栏），
 * 关掉整列，宽屏记住「收起」。窄屏同一套逻辑，落在原来的抽屉位里。
 */
export default function CitationSidebar({
  messages, sending, target, onTargetChange, request, width, onResizeStart,
}: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const wide = useNarrowViewport(CITATION_SIDEBAR_QUERY);
  const [wideOpen, setWideOpen] = useState(readOpen);
  const [narrowOpen, setNarrowOpen] = useState(false);
  const open = wide ? wideOpen : narrowOpen;
  const setOpen = (next: boolean) => (wide ? setWideOpen(next) : setNarrowOpen(next));
  const [selection, setSelection] = useState<Selection | null>(null);
  const [openEvent, setOpenEvent] = useState<OpenEvent | null>(null);

  const answers = messages.filter((m) => m.role === "assistant");
  const latest = answers.length > 0 ? answers[answers.length - 1] : null;
  const latestKey = latest?.created_at ?? "";
  const selected =
    (selection && selection.latestKey === latestKey
      ? answers.find((m) => m.created_at === selection.key)
      : null) ?? latest;

  // 下面两段是「按 props 变化调整 state」的 React 惯用法（渲染期比较上一次的值），不用 effect。
  // 点了某条回答里的内联引文 → 面板跟到那条回答；收起状态下顺带展开（不记忆）。
  const [seenTarget, setSeenTarget] = useState<CitationTarget | null>(target);
  if (seenTarget !== target) {
    setSeenTarget(target);
    if (target) {
      const owner = findAnswerForTarget(messages, target, lang, selected);
      if (owner && owner !== selected) setSelection({ key: owner.created_at, latestKey });
      if (!open) {
        setOpen(true);
        setOpenEvent({
          via: owner && isExplicitCitationOf(owner, target, lang) ? "inline" : "source",
          remember: false,
        });
      }
    }
  }

  // 点了某条回答下方的入口胶囊 → 展开并列出那条回答。
  const [seenRequest, setSeenRequest] = useState<CitationPanelRequest | null>(request);
  if (seenRequest !== request) {
    setSeenRequest(request);
    if (request) {
      setSelection({ key: request.key, latestKey });
      if (!open) setOpen(true);
      // 已经开着（例如被内联引文临时打开）也算一次手动展开：照样记住。埋点只记「从关到开」。
      setOpenEvent({ via: open ? null : "chip", remember: wide });
    }
  }

  useEffect(() => {
    if (!openEvent) return;
    if (openEvent.via) track("citation_panel_open", { via: openEvent.via });
    if (openEvent.remember) writeOpen(true);
  }, [openEvent]);

  const close = () => {
    setOpen(false);
    if (wide) writeOpen(false);
    track("citation_panel_close", { view: target ? "passage" : "list" });
    if (target) onTargetChange(null);
  };

  const openCitation = (c: AnswerCitation) => {
    track("citation_click", { text_id: c.target.textId, via: "panel" });
    onTargetChange(c.target); // chunkIndex < 0 也在本栏打开：抽屉取整卷原文
  };

  const openSource = (s: ChatSource) => {
    track("source_click", { text_id: s.text_id, via: "panel" });
    const chunkIndex = s.chunk_index ?? -1;
    onTargetChange({ textId: s.text_id, juanNum: s.juan_num, chunkIndex, titleZh: s.title_zh ?? "" });
  };

  if (!open) return null;
  // 还没有任何回答（空态首页）：不占列。
  if (!latest && !target) return null;

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

  if (target) {
    return column(
      <>
        <button type="button" className="chat-cpanel-back" onClick={() => onTargetChange(null)}>
          <ArrowLeftOutlined /> {t("chat.cpanel.back_to_list")}
        </button>
        <Suspense fallback={<div style={{ padding: 40, textAlign: "center" }}>…</div>}>
          <CitationDrawer target={target} onClose={close} />
        </Suspense>
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
      onClose={close}
      onShowLatest={() => setSelection(null)}
    />,
  );
}
