import { useContext, useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { ChatSource } from "../api/client";
import type { ParsedCitation } from "../utils/citationLinks";
import { isCheckedQuote } from "../utils/answerCitations";
import { localizeHan } from "../utils/hanScript";
import { CitationPreviewContext } from "./citationPreviewContext";
import "../styles/chat-citation-preview.css";

/** 悬停多久才弹卡片：短了扫过正文就满屏闪卡，长了像没反应。 */
export const PREVIEW_OPEN_DELAY_MS = 300;
/** 移开后多久收：留出鼠标从引文挪到卡片上的时间。 */
export const PREVIEW_CLOSE_DELAY_MS = 150;
const CARD_MAX_W = 340;
const EDGE = 8;
const GAP = 6;
/** 下方剩余空间少于这么多、且上方更宽裕时翻到上方。 */
const FLIP_THRESHOLD = 220;
const EXCERPT_CHARS = 90;

type Via = "inline" | "preview";

function track(event: string, data: Record<string, string | number>) {
  if (typeof umami !== "undefined") umami.track(event, data);
}

/**
 * 把 `【《经名》第N卷】` 拆成三段 span：括号与卷号淡、小，经名保持强调色。
 * 只是给同一串字套上元素 —— 不加任何字符、不用 ::before/::after 文字，所以
 * textContent / 手动选中复制得到的仍是原标记一字不差。不是这个形状（例如散文
 * 里的裸《经名》）就原样返回。
 */
function splitCitationLabel(children: ReactNode): ReactNode {
  const text =
    typeof children === "string"
      ? children
      : Array.isArray(children) && children.length === 1 && typeof children[0] === "string"
        ? children[0]
        : null;
  if (text == null) return children;
  const m = text.match(/^【(《[^》]*》)([^】]*)】$/);
  if (!m) return children;
  return (
    <>
      <span className="chat-cite-mark">【</span>
      <span className="chat-cite-title">{m[1]}</span>
      <span className="chat-cite-mark">{`${m[2]}】`}</span>
    </>
  );
}

function canHover(): boolean {
  try {
    return typeof window !== "undefined" && !!window.matchMedia?.("(hover: hover)").matches;
  } catch {
    return false;
  }
}

/** 引文所在卷、所在段的检索原文 —— 没有引句时拿来当「所引卷片段」。
 *  只认同经同卷：卷号对不上的段落不是这条引文指向的东西。 */
function excerptFor(parsed: ParsedCitation, sources: ChatSource[] | null | undefined): string | null {
  if (!sources) return null;
  const sameJuan = sources.filter(
    (s) => s.text_id === parsed.textId && s.juan_num === parsed.juanNum && s.chunk_text,
  );
  const hit = sameJuan.find((s) => (s.chunk_index ?? -1) === parsed.chunkIndex) ?? sameJuan[0];
  if (!hit) return null;
  const flat = hit.chunk_text.replace(/\s+/g, "");
  return flat.length > EXCERPT_CHARS ? `${flat.slice(0, EXCERPT_CHARS)}…` : flat;
}

interface Placement {
  style: CSSProperties;
  flipped: boolean;
}

/** 最近的纵向滚动容器（/chat 的消息列表）。卡片上下不越出它，免得盖住下方输入框。 */
function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
    const oy = getComputedStyle(n).overflowY;
    if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight) return n;
  }
  return null;
}

/**
 * 卡片放在引文下方，下方不够就翻到上方。左右夹在回答列（.chat-msg-col）以内，
 * 所以宽屏右侧的引文栏展开时卡片不会盖到它上面；上下夹在消息滚动区以内，不会
 * 盖住输入框和发送按钮。用 bottom 锚定上方位置，免得先渲染一遍再量卡片高度。
 */
function computePlacement(btn: HTMLElement): Placement {
  const rects = btn.getClientRects();
  const first = rects.length > 0 ? rects[0] : btn.getBoundingClientRect();
  const last = rects.length > 0 ? rects[rects.length - 1] : first;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const col = btn.closest(".chat-msg-col")?.getBoundingClientRect();
  const minX = Math.max(EDGE, col ? col.left : EDGE);
  const maxX = Math.max(minX + 120, Math.min(vw - EDGE, col ? col.right : vw - EDGE));
  const width = Math.min(CARD_MAX_W, maxX - minX);
  const scroller = scrollParent(btn)?.getBoundingClientRect();
  const topBound = Math.max(EDGE, scroller ? scroller.top : EDGE);
  const bottomBound = Math.min(vh - EDGE, scroller ? scroller.bottom : vh - EDGE);
  const below = bottomBound - last.bottom;
  const above = first.top - topBound;
  const flipped = below < FLIP_THRESHOLD && above > below;
  const anchor = flipped ? first : last;
  const left = Math.min(Math.max(anchor.left, minX), maxX - width);
  const style: CSSProperties = flipped
    ? { left, width, bottom: vh - first.top + GAP, maxHeight: Math.max(120, above - GAP) }
    : { left, width, top: last.bottom + GAP, maxHeight: Math.max(120, below - GAP) };
  return { style, flipped };
}

interface InlineCitationProps {
  parsed: ParsedCitation;
  children?: ReactNode;
  /** 打开原文 —— 与点击引文本身同一个处理器；via 区分入口供埋点。 */
  onOpen: (via: Via) => void;
}

/**
 * 回答正文里的一条内联引文：经名在前、卷号淡化，桌面悬停（或键盘聚焦）约 300ms
 * 弹出预览卡片。触屏不弹卡，点击行为与从前完全一样。
 */
export function InlineCitation({ parsed, children, onOpen }: InlineCitationProps) {
  const { t, i18n } = useTranslation();
  const data = useContext(CitationPreviewContext);
  const cardId = useId();
  const btnRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const openTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pointerDown = useRef(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const open = placement !== null;

  const verified = isCheckedQuote(data?.checkedQuotes, parsed.titleZh, parsed.quote);

  const clearTimers = () => {
    if (openTimer.current) clearTimeout(openTimer.current);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    openTimer.current = null;
    closeTimer.current = null;
  };

  const show = () => {
    clearTimers();
    const btn = btnRef.current;
    if (!btn) return;
    // 每次悬停只记一次展示：已经开着（鼠标在引文与卡片之间来回）就不再记。
    // 埋点不放进 setState 的 updater —— StrictMode 会把 updater 跑两遍。
    if (!open) track("citation_preview_show", { text_id: parsed.textId, checked: verified ? 1 : 0 });
    setPlacement(computePlacement(btn));
  };

  const hide = () => {
    clearTimers();
    setPlacement(null);
  };

  const scheduleOpen = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    if (open || openTimer.current) return;
    openTimer.current = setTimeout(() => {
      openTimer.current = null;
      show();
    }, PREVIEW_OPEN_DELAY_MS);
  };

  const scheduleClose = () => {
    if (openTimer.current) {
      clearTimeout(openTimer.current);
      openTimer.current = null;
    }
    if (!open || closeTimer.current) return;
    closeTimer.current = setTimeout(() => {
      closeTimer.current = null;
      setPlacement(null);
    }, PREVIEW_CLOSE_DELAY_MS);
  };

  const cancelClose = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  // 卸载时别留下一个会去 setState 的定时器。
  useEffect(() => () => clearTimers(), []);

  // 卡片开着时：Esc 只关卡片。挂在 window 的捕获阶段，先于 useChatShortcuts
  // （window 冒泡阶段）执行；preventDefault 后它看到 defaultPrevented 就不会
  // 「停止生成」。卡片没开时不挂，生成中 Esc 照旧停止。滚动/缩放时位置失效，直接收。
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.isComposing) return;
      e.preventDefault();
      setPlacement(null);
    };
    const onMove = (e: Event) => {
      if (cardRef.current && e.target instanceof Node && cardRef.current.contains(e.target)) return;
      setPlacement(null);
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [open]);

  const excerpt = parsed.quote ? null : excerptFor(parsed, data?.sources);
  const title = localizeHan(parsed.titleZh, i18n.language);
  const card = open
    ? createPortal(
        <div
          ref={cardRef}
          id={cardId}
          role="dialog"
          aria-label={t("chat.cite_preview.label")}
          className={`chat-cite-preview${placement.flipped ? " chat-cite-preview--above" : ""}`}
          style={placement.style}
          onPointerEnter={cancelClose}
          onPointerLeave={(e) => {
            if (e.pointerType !== "touch") scheduleClose();
          }}
        >
          <div className="chat-cite-preview-title">
            {t("reader.citation.title_with_juan", { title, n: parsed.juanNum })}
          </div>
          {parsed.quote ? (
            <div className="chat-cite-preview-quote">{t("chat.cite_preview.quote", { q: parsed.quote })}</div>
          ) : excerpt ? (
            <>
              <div className="chat-cite-preview-excerpt-label">{t("chat.cite_preview.excerpt_label")}</div>
              <div className="chat-cite-preview-excerpt">{excerpt}</div>
            </>
          ) : null}
          <div className="chat-cite-preview-foot">
            {/* 只有后端把这一句列进 checked_quotes 才显示；不在表里就什么都不说，
                不写「未核验」也不写「核验中」—— 不知道的事不替它下结论。 */}
            {verified ? (
              <span className="chat-cite-preview-verified">{t("chat.cpanel.verbatim_checked")}</span>
            ) : (
              <span />
            )}
            <button
              type="button"
              className="chat-cite-preview-open"
              onClick={() => {
                hide();
                onOpen("preview");
              }}
            >
              {t("chat.cite_preview.open")}
            </button>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="chat-inline-cite"
        aria-expanded={open ? true : undefined}
        aria-controls={open ? cardId : undefined}
        onPointerDown={() => {
          pointerDown.current = true;
        }}
        onPointerEnter={(e) => {
          if (e.pointerType === "touch" || e.pointerType === "pen" || !canHover()) return;
          scheduleOpen();
        }}
        onPointerLeave={(e) => {
          if (e.pointerType === "touch") return;
          scheduleClose();
        }}
        onFocus={() => {
          // 鼠标/触屏点击也会聚焦按钮 —— 那是要打开抽屉，不是要看预览。只有键盘
          // （Tab）带来的焦点才弹卡片。
          if (pointerDown.current) {
            pointerDown.current = false;
            return;
          }
          show();
        }}
        onBlur={(e) => {
          pointerDown.current = false;
          if (cardRef.current && e.relatedTarget instanceof Node && cardRef.current.contains(e.relatedTarget)) return;
          if (open) hide();
        }}
        onClick={(e) => {
          e.preventDefault();
          hide();
          onOpen("inline");
        }}
      >
        {splitCitationLabel(children)}
      </button>
      {card}
    </>
  );
}
