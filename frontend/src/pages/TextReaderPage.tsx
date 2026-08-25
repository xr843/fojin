import { useState, useRef, useEffect, useCallback, useMemo, type ReactNode } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Helmet } from "react-helmet-async";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Typography, Spin, Button, Select, Breadcrumb, Row, Col, message, Tooltip, Tag, Popover, Dropdown, Drawer } from "antd";
import { getLastPosition, recordReading } from "../utils/readingHistory";
import {
  HomeOutlined,
  LeftOutlined,
  RightOutlined,
  FontSizeOutlined,
  BookOutlined,
  EditOutlined,
  HeartOutlined,
  HeartFilled,
  RobotOutlined,
  GlobalOutlined,
  DiffOutlined,
  VerticalAlignTopOutlined,
  DownloadOutlined,
  SoundOutlined,
} from "@ant-design/icons";
import { trackAudio } from "../audio/telemetry";
import { useAudioPlayer } from "../audio/useAudioPlayback";
import { getJuanList, getJuanContent, getJuanLanguages, getTextDetail, checkBookmark, addBookmark, removeBookmark, searchDictionaryGrouped, getJuanApparatus, getJuanLineAnchors, getJuanAudio, type ApparatusEntryItem } from "../api/client";
import { isNarrowViewport, useNarrowViewport } from "../hooks/useNarrowViewport";
import { useAuthStore } from "../stores/authStore";
import CitationGenerator from "../components/CitationGenerator";
import SourceAttribution from "../components/SourceAttribution";
import AnnotationPanel from "../components/AnnotationPanel";
import { ReaderDictPopover } from "../components/ReaderDictPopover";
import { DICT_POPOVER_INIT, MAX_WORD_LEN, type DictPopoverState } from "../components/ReaderDictPopover.types";
import ReaderAIPanel from "../components/ReaderAIPanel";
import ReaderParallelPanel from "../components/ReaderParallelPanel";

import "../styles/versions-panel.css";
import "../styles/reader.css";

const LANG_LABEL_KEYS: Record<string, string> = {
  lzh: "reader.lang.lzh",
  pi: "reader.lang.pi",
  en: "reader.lang.en",
  sa: "reader.lang.sa",
  bo: "reader.lang.bo",
  ja: "reader.lang.ja",
};

const FONT_SIZE_MIN = 14;
const FONT_SIZE_MAX = 28;
const FONT_SIZE_STEP = 2;
const FONT_SIZE_KEY = "fojin-reader-font-size";

import { reflowText, type TextSegment } from "../utils/textReflow";


type TFn = (key: string, opts?: Record<string, unknown>) => string;
// start/end are UTF-16 offsets into the content string (converted from the
// backend's Python code-point offsets) so they index the reflowed segments.
interface ApparatusNumbered { entry: ApparatusEntryItem; no: number; start: number; end: number }
// off = UTF-16 offset of a CBETA <lb> line anchor within the content.
interface LineAnchorConv { off: number; ref: string }
type ReaderCtx = { numbered: ApparatusNumbered[]; lineAnchors: LineAnchorConv[]; t: TFn } | null;

/** Build a map from Python code-point index → JS UTF-16 index for `raw`.
 * Backend offsets are code-point indices; supplementary-plane CJK (surrogate
 * pairs) would otherwise drift the mapping. Index `[n]` = UTF-16 offset; the
 * final sentinel covers an offset at end-of-string. */
function cpToU16Map(raw: string): number[] {
  const map: number[] = [];
  let u = 0;
  for (const ch of raw) {
    map.push(u);
    u += ch.length;
  }
  map.push(u);
  return map;
}

/** CBETA-style inline apparatus marker: a clickable superscript [n] placed
 * right after the lemma; clicking opens a 校注 popover with base text + variants. */
function ApparatusMarker({ no, entry, t }: { no: number; entry: ApparatusEntryItem; t: TFn }) {
  const content = (
    <div style={{ maxWidth: 320 }}>
      <div style={{ marginBottom: 6 }}>
        {entry.lemma_siglum && <Tag color="gold" style={{ marginInlineEnd: 4 }}>{entry.lemma_siglum}</Tag>}
        <span style={{ fontWeight: 600 }}>{entry.lemma}</span>
      </div>
      {entry.readings.map((r, idx) => (
        <div key={idx} style={{ marginTop: 2 }}>
          {r.witnesses.map((w) => (
            <Tag key={w} style={{ marginInlineEnd: 2 }}>{w}</Tag>
          ))}
          <span>{r.is_omission ? t("reader.apparatus.omission") : r.reading}</span>
          {r.resp && (
            <span style={{ color: "var(--fj-text-secondary)", fontSize: 12, marginInlineStart: 4 }}>
              {t("reader.apparatus.corrector", { resp: r.resp })}
            </span>
          )}
        </div>
      ))}
    </div>
  );
  return (
    <Popover content={content} title={t("reader.apparatus.note")} trigger="click">
      <sup className="apparatus-marker">[{no}]</sup>
    </Popover>
  );
}

/** Splice into a text-bearing segment, by content offset: visible apparatus
 * markers (校勘 [n]) after each lemma, and zero-width line-anchor spans (carrying
 * the CBETA page-col-line ref) for the on-demand citation locator and URN scroll. */
function renderSegmentChildren(seg: Extract<TextSegment, { text: string }>, ctx: NonNullable<ReaderCtx>): ReactNode {
  const { numbered, lineAnchors, t } = ctx;
  const { text, offsets } = seg;
  if (!offsets.length || (!numbered.length && !lineAnchors.length)) return text;
  const segStart = offsets[0];
  const segEnd = offsets[offsets.length - 1];
  const offToLocal = new Map<number, number>();
  for (let k = 0; k < offsets.length; k++) offToLocal.set(offsets[k], k);

  // order: line anchors (0) before apparatus markers (1) when at the same position.
  const ins: { pos: number; order: number; node: ReactNode }[] = [];
  for (const la of lineAnchors) {
    if (la.off < segStart || la.off > segEnd || !offToLocal.has(la.off)) continue;
    const pos = offToLocal.get(la.off)!;
    // Zero-width anchor for the citation locator + URN scroll.
    ins.push({ pos, order: 0, node: <span key={`ln${la.ref}`} className="cbeta-line" data-ref={la.ref} /> });
  }
  for (const m of numbered) {
    const cs = m.start;
    if (cs < segStart || cs > segEnd || !offToLocal.has(cs)) continue;
    // Marker goes right after the lemma. The lemma's chars are contiguous in the
    // reflowed segment (any "\n" between source lines was dropped), so its end is
    // locStart + the lemma's own length — robust when the lemma is followed by or
    // spans a line break (where char_end would point at a dropped "\n").
    const pos = Math.min(offToLocal.get(cs)! + m.entry.lemma.length, text.length);
    ins.push({ pos, order: 1, node: <ApparatusMarker key={`ap${m.no}`} no={m.no} entry={m.entry} t={t} /> });
  }
  if (!ins.length) return text;
  ins.sort((a, b) => a.pos - b.pos || a.order - b.order);
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const it of ins) {
    if (it.pos > cursor) nodes.push(text.slice(cursor, it.pos));
    nodes.push(it.node);
    cursor = Math.max(cursor, it.pos);
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function renderSegment(seg: TextSegment, i: number, ctx?: ReaderCtx) {
  if (seg.type === "break") return <br key={i} />;
  const children = ctx ? renderSegmentChildren(seg, ctx) : seg.text;
  return <p key={i} className={`text-${seg.type}`}>{children}</p>;
}

/** CBETA line ref (e.g. "0001a09") of the embedded <span class="cbeta-line">
 * nearest before `startNode` — i.e. the page-col-line the selection sits in. */
function nearestLineRef(container: HTMLElement, startNode: Node): string | null {
  let ref: string | null = null;
  for (const el of Array.from(container.querySelectorAll<HTMLElement>(".cbeta-line"))) {
    const pos = el.compareDocumentPosition(startNode);
    if (pos === 0 || pos & Node.DOCUMENT_POSITION_FOLLOWING) {
      ref = el.dataset.ref ?? ref; // el is at/before the selection → candidate
    } else {
      break; // anchors are in document order; rest are after the selection
    }
  }
  return ref;
}

function getInitialFontSize(): number {
  try {
    const v = localStorage.getItem(FONT_SIZE_KEY);
    if (v) return Math.min(Math.max(Number(v), FONT_SIZE_MIN), FONT_SIZE_MAX);
  } catch { /* noop */ }
  return 18;
}

/**
 * 找到 el 实际所在的滚动容器。AI 面板打开时（默认即打开）reader.css 把
 * .reader-with-sidebar 锁高、滚动权交给 .reader-container；面板关闭时滚动
 * 的是 document（返回 null）。续读与 highlight 深链都必须按真实 scroller 操作。
 */
function findScrollContainer(el: HTMLElement): HTMLElement | null {
  let p = el.parentElement;
  while (p) {
    const style = getComputedStyle(p);
    if ((style.overflowY === "auto" || style.overflowY === "scroll") && p.scrollHeight > p.clientHeight) {
      return p;
    }
    p = p.parentElement;
  }
  return null;
}

/** 划词查辞典浮层状态 */
export default function TextReaderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const textId = Number(id);
  const initialJuanParam = searchParams.get("juan");
  const initialJuan = initialJuanParam ? parseInt(initialJuanParam, 10) : 1;
  const highlightChunkParam = searchParams.get("highlight_chunk");
  const highlightChunkIndex = highlightChunkParam ? parseInt(highlightChunkParam, 10) : null;
  // 续读：URL 显式指定卷或深链高亮时尊重 URL；否则恢复上次阅读位置。
  // 首次渲染时一次性决定（惰性 state），resumeRef 用它做初值，供滚动恢复
  // effect 消费后置空。
  const [initialReading] = useState<{ juan: number; resume: { juan: number; ratio: number } | null }>(() => {
    const last = highlightChunkParam ? null : getLastPosition(Number(id));
    if (initialJuanParam && Number.isFinite(initialJuan) && initialJuan > 0) {
      // URL 显式指定卷：尊重 URL；若与记录同卷（如详情页"继续阅读"），仍恢复滚动。
      const resume = last && last.juan === initialJuan && last.ratio > 0.03
        ? { juan: initialJuan, ratio: last.ratio }
        : null;
      return { juan: initialJuan, resume };
    }
    if (last && last.juan > 0 && (last.juan > 1 || last.ratio > 0.03)) {
      return { juan: last.juan, resume: { juan: last.juan, ratio: last.ratio } };
    }
    return { juan: 1, resume: null };
  });
  const resumeRef = useRef<{ juan: number; ratio: number } | null>(initialReading.resume);
  const [juanNum, setJuanNum] = useState(initialReading.juan);
  const [fontSize, setFontSize] = useState(getInitialFontSize);
  const { t } = useTranslation();
  const getLangLabel = useCallback((lang: string) => {
    const key = LANG_LABEL_KEYS[lang];
    return key ? t(key) : lang;
  }, [t]);
  const [citationOpen, setCitationOpen] = useState(false);
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [apparatusOn, setApparatusOn] = useState(false);
  const [parallelPanelOpen, setParallelPanelOpen] = useState(false);

  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  const [compareLang, setCompareLang] = useState<string | null>(null);
  // 回到顶部按钮：滚过一屏后浮现；落点跟随"阅读列"右下角
  const [showBackTop, setShowBackTop] = useState(false);
  const [backTopStyle, setBackTopStyle] = useState<{ right: number; bottom: number }>({ right: 24, bottom: 84 });
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const readerContentRef = useRef<HTMLDivElement>(null);

  // AI panel state
  // 窄屏（≤1024px，与 reader.css 的 Tablet 断点同值）默认收起：内联侧栏在列布局里
  // 会把经文挤进一个 178px 的滚动盒、一行都不露（2026-08-25 Playwright 390px 实测），
  // 用户得先发现并关掉 AI 面板才能读经。惰性初值而不是 effect 里 setState ——
  // react-hooks/set-state-in-effect 会红。
  const narrow = useNarrowViewport();
  const [aiPanelOpen, setAiPanelOpen] = useState(() => !isNarrowViewport());
  const [aiPanelWidth, setAiPanelWidth] = useState(420);
  const [aiSelectedText, setAiSelectedText] = useState<string | undefined>();
  const isDraggingRef = useRef(false);

  // 多语对读 panel state (inline flex sidebar, same pattern as AI panel)
  const [parallelPanelWidth, setParallelPanelWidth] = useState(480);
  const isDraggingParallelRef = useRef(false);

  const handleAskXiaojin = useCallback((text: string) => {
    setAiSelectedText(text);
    setAiPanelOpen(true);
  }, []);

  // Drag to resize 多语对读 panel
  const handleParallelDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingParallelRef.current = true;
    const startX = e.clientX;
    const startWidth = parallelPanelWidth;
    const onMouseMove = (ev: MouseEvent) => {
      if (!isDraggingParallelRef.current) return;
      const delta = startX - ev.clientX;
      setParallelPanelWidth(Math.max(320, Math.min(startWidth + delta, 720)));
    };
    const onMouseUp = () => {
      isDraggingParallelRef.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [parallelPanelWidth]);

  // Drag to resize AI panel
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    const startX = e.clientX;
    const startWidth = aiPanelWidth;

    const onMouseMove = (ev: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const delta = startX - ev.clientX;
      setAiPanelWidth(Math.max(300, Math.min(startWidth + delta, 700)));
    };
    const onMouseUp = () => {
      isDraggingRef.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [aiPanelWidth]);
  const handleSelectedTextConsumed = useCallback(() => {
    setAiSelectedText(undefined);
  }, []);

  // 划词查辞典
  const [dictPopover, setDictPopover] = useState<DictPopoverState>(DICT_POPOVER_INIT);
  // On-demand citation locator: the CBETA line ref at the current selection.
  const [lineLocator, setLineLocator] = useState<{ ref: string; x: number; y: number } | null>(null);
  const closeDictPopover = useCallback(() => {
    setDictPopover(DICT_POPOVER_INIT);
    setLineLocator(null);
  }, []);

  const downloadExport = useCallback((format: "txt" | "html" | "docx" | "epub", juan: number | null) => {
    const params = new URLSearchParams({ format });
    if (juan != null) params.set("juan", String(juan));
    // A plain anchor navigation lets the browser handle the Content-Disposition
    // download; no auth header is needed (export is a public read endpoint).
    const a = document.createElement("a");
    a.href = `/api/texts/${textId}/export?${params.toString()}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }, [textId]);

  const handleTextSelect = useCallback(async () => {
    const sel = window.getSelection();
    const text = sel?.toString().trim() || "";
    // 1–500 字才弹浮层；>500 视为误选，忽略
    if (text.length < 1 || text.length > 500) return;

    // 获取选中文字的位置
    const range = sel?.getRangeAt(0);
    if (!range) return;
    const rect = range.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.bottom;

    // Citation locator: CBETA page-col-line at the selection (needs embedded anchors).
    const containerEl = readerContentRef.current;
    const ref = containerEl ? nearestLineRef(containerEl, range.startContainer) : null;
    setLineLocator(ref ? { ref, x, y: rect.top } : null);

    // 短词查辞典；整句选择只显示「问小津」，不查辞典
    const isWord = text.length <= MAX_WORD_LEN;
    setDictPopover({ visible: true, text, x, y, loading: isWord, result: null });
    if (!isWord) return;

    try {
      const result = await searchDictionaryGrouped({ q: text });
      setDictPopover((prev) =>
        prev.text === text ? { ...prev, loading: false, result } : prev,
      );
    } catch {
      setDictPopover((prev) =>
        prev.text === text ? { ...prev, loading: false, result: { total: 0, page: null, page_size: null, groups: [] } } : prev,
      );
    }
  }, []);

  // 监听 mouseup / touchend 划词事件
  useEffect(() => {
    const container = readerContentRef.current;
    if (!container) return;

    const onMouseUp = (e: MouseEvent) => {
      // 点击浮层内部不处理
      const target = e.target as HTMLElement;
      if (target.closest(".reader-dict-popover")) return;
      handleTextSelect();
    };

    const onTouchEnd = () => {
      // 延迟以确保 selection 已更新
      setTimeout(handleTextSelect, 100);
    };

    container.addEventListener("mouseup", onMouseUp);
    container.addEventListener("touchend", onTouchEnd);
    return () => {
      container.removeEventListener("mouseup", onMouseUp);
      container.removeEventListener("touchend", onTouchEnd);
    };
  }, [handleTextSelect]);

  // 点击浮层外部关闭
  useEffect(() => {
    if (!dictPopover.visible) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(".reader-dict-popover")) {
        closeDictPopover();
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [dictPopover.visible, closeDictPopover]);

  const { data: bookmarked = false } = useQuery({
    queryKey: ["bookmark", textId],
    queryFn: () => checkBookmark(textId),
    enabled: !!textId && !!user,
  });

  const toggleBookmark = async () => {
    if (!user) {
      message.info(t("reader.bookmark.login_required"));
      return;
    }
    setBookmarkLoading(true);
    try {
      if (bookmarked) {
        await removeBookmark(textId);
        message.success(t("reader.bookmark.removed"));
      } else {
        await addBookmark(textId);
        message.success(t("reader.bookmark.added"));
      }
      queryClient.invalidateQueries({ queryKey: ["bookmark", textId] });
    } catch {
      message.error(t("reader.bookmark.failed"));
    } finally {
      setBookmarkLoading(false);
    }
  };

  const { data: juanList } = useQuery({
    queryKey: ["juanList", textId],
    queryFn: () => getJuanList(textId),
    enabled: !!textId,
  });

  const { data: content, isLoading } = useQuery({
    queryKey: ["juanContent", textId, juanNum],
    queryFn: () => getJuanContent(textId, juanNum),
    enabled: !!textId,
  });

  const { data: textDetail } = useQuery({
    queryKey: ["text", textId],
    queryFn: () => getTextDetail(textId),
    enabled: !!textId,
  });

  const { data: langData } = useQuery({
    queryKey: ["juanLanguages", textId, juanNum],
    queryFn: () => getJuanLanguages(Number(textId), juanNum),
    enabled: !!textId,
  });

  // Umami: track text reading when detail loads
  useEffect(() => {
    if (textDetail && typeof umami !== "undefined") {
      umami.track("read", { id: String(textId), title: textDetail.title_zh || "" });
    }
  }, [textId, textDetail]);

  // 续读 · 恢复滚动位置。坐标系说明：阅读锚点取视口上 1/3 处。测量公式
  // (innerHeight/3 - rect.top) / rect.height 只依赖 viewport 坐标，对
  // document 滚动和 .reader-container 元素滚动（AI 面板打开时 reader.css
  // 把滚动权交给容器）都成立；恢复用 scrollBy 增量同理对两种 scroller 通用。
  useEffect(() => {
    const resume = resumeRef.current;
    if (!resume || resume.juan !== juanNum) return;
    if (!content?.content) return;
    const raf = requestAnimationFrame(() => {
      // 消费 ref 放在 rAF 内：StrictMode 下 effect 第一轮的 cleanup 会取消
      // rAF，此时 ref 未消费，第二轮才能重试（否则暖缓存时续读静默失效）。
      if (!resumeRef.current) return;
      resumeRef.current = null;
      const el = readerContentRef.current;
      if (!el) return;
      if (resume.ratio > 0.03) {
        const rect = el.getBoundingClientRect();
        const delta = rect.top + rect.height * resume.ratio - window.innerHeight / 3;
        const scroller = findScrollContainer(el);
        if (scroller) scroller.scrollTop += delta;
        else window.scrollBy({ top: delta });
      }
      message.info(t("reader.resume.positioned", { n: resume.juan }), 2.5);
    });
    return () => cancelAnimationFrame(raf);
  }, [content, juanNum, t]);

  // 续读 · 记录阅读位置。trailing-throttle 1.5s；进卷时也记录一次；卸载时
  // flush 未落盘的最后位置。capture: true 是关键 —— AI 面板打开时滚动发生在
  // .reader-container 上，scroll 事件不冒泡，只有捕获阶段能在 window 收到。
  useEffect(() => {
    if (!content?.content) return;
    let timer: number | undefined;
    const record = () => {
      timer = undefined;
      const el = readerContentRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.height <= 0) return;
      recordReading({
        textId,
        title: content.title_zh || t("reader.text_fallback", { id: textId }),
        juan: juanNum,
        ratio: (window.innerHeight / 3 - rect.top) / rect.height,
      });
    };
    const onScroll = () => {
      if (timer !== undefined) return;
      timer = window.setTimeout(record, 1500);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true, capture: true });
    return () => {
      window.removeEventListener("scroll", onScroll, { capture: true });
      if (timer !== undefined) {
        window.clearTimeout(timer);
        record(); // flush：离开页面/换卷前把最后 1.5s 内的滚动落盘
      }
    };
  }, [content, textId, juanNum, t]);

  // 回到顶部：滚过 ~一屏后浮现按钮。和续读同理，AI 面板打开时滚动发生在
  // .reader-container（不冒泡），只能在 window 捕获阶段收到 scroll 事件；
  // 偏移量按真实 scroller 取值，document 滚动时回退 window.scrollY。
  useEffect(() => {
    const update = () => {
      const el = readerContentRef.current;
      const scroller = el ? findScrollContainer(el) : null;
      const offset = scroller ? scroller.scrollTop : window.scrollY;
      setShowBackTop(offset > 400);
    };
    update();
    window.addEventListener("scroll", update, { passive: true, capture: true });
    return () => window.removeEventListener("scroll", update, { capture: true });
    // aiPanelOpen/parallelPanelOpen 都会切换真实 scroller（reader-ai-active），需重评
  }, [content, aiPanelOpen, parallelPanelOpen]);

  // 按钮落点跟随"阅读列"右下角：实测 .reader-container 右缘，让按钮右缘落在其内侧 16px。
  // 直接量 DOM 而非按面板宽度推算 —— 面板未必贴视口右缘（滚动条/留白），且移动端面板纵向
  // 堆叠、阅读列占满宽度，量 DOM 对桌面并排 / 移动堆叠 / 居中三种布局都成立。
  // AI 面板关闭时右下角被 AI FAB 占据（bottom:24），按钮上移一档避免重叠。
  useEffect(() => {
    const compute = () => {
      const rc = readerContentRef.current?.closest(".reader-container");
      const viewportRight = document.documentElement.clientWidth;
      const right = rc
        ? Math.max(24, Math.round(viewportRight - rc.getBoundingClientRect().right + 16))
        : 24;
      setBackTopStyle({ right, bottom: aiPanelOpen ? 24 : 84 });
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, [content, aiPanelOpen, parallelPanelOpen, aiPanelWidth, parallelPanelWidth]);

  const scrollToTop = useCallback(() => {
    const el = readerContentRef.current;
    const scroller = el ? findScrollContainer(el) : null;
    if (scroller) scroller.scrollTo({ top: 0, behavior: "smooth" });
    else window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  // Deep-link from the chat citation drawer: ?highlight_chunk=N
  // Chunks are 500 chars wide with 50-char overlap (see scripts/archive/misc/generate_embeddings.py),
  // so chunk N starts at approximately char N * 450 in the juan body. After the
  // juan content paints, scroll the reader container to the matching fraction of
  // its scrollable height. Precision is ±1 paragraph, which is close enough for
  // the user to visually confirm — the drawer already showed them the exact text.
  const lastHighlightedChunkRef = useRef<string | null>(null);
  useEffect(() => {
    if (highlightChunkIndex === null || !Number.isFinite(highlightChunkIndex) || highlightChunkIndex < 0) return;
    if (!content?.content) return;
    const key = `${textId}-${juanNum}-${highlightChunkIndex}`;
    if (lastHighlightedChunkRef.current === key) return;
    lastHighlightedChunkRef.current = key;

    const chunkCharOffset = highlightChunkIndex * 450;
    const totalChars = content.content.length;
    if (totalChars <= 0) return;
    const ratio = Math.min(chunkCharOffset / totalChars, 0.95);

    // Wait for paint so the DOM reflects the juan's full rendered height.
    // Scroll the REAL scroller: with the AI panel open (the default) reader.css
    // hands scrolling to .reader-container, where window.scrollTo is a no-op.
    const raf = requestAnimationFrame(() => {
      const el = readerContentRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const delta = rect.top + rect.height * ratio - window.innerHeight / 3;
      const scroller = findScrollContainer(el);
      if (scroller) scroller.scrollTo({ top: scroller.scrollTop + delta, behavior: "smooth" });
      else window.scrollBy({ top: delta, behavior: "smooth" });
    });
    return () => cancelAnimationFrame(raf);
  }, [highlightChunkIndex, content, textId, juanNum]);

  const { data: compareContent, isLoading: compareLoading } = useQuery({
    queryKey: ["juanContent", textId, juanNum, compareLang],
    queryFn: () => getJuanContent(Number(textId), juanNum, compareLang!),
    enabled: !!compareLang,
    staleTime: 3600000,
  });

  // reflowText is a full line-by-line parse of the juan body (tens of thousands
  // of chars). Memoize on the raw content so font-size changes, bookmark toggles,
  // dict-popover opens, and AI-panel resize-drags don't re-parse the whole text
  // on every render. Keyed on content only — render-time concerns (font size) are
  // CSS, not part of the parse.
  const contentText = content?.content ?? null;
  const compareText = compareContent?.content ?? null;
  const reflowedContent = useMemo(
    () => (contentText ? reflowText(contentText) : []),
    [contentText],
  );
  const reflowedCompare = useMemo(
    () => (compareText ? reflowText(compareText) : []),
    [compareText],
  );

  // Critical apparatus (校勘异文): fetched lazily only when the 校勘 toggle is on.
  const { data: apparatusData } = useQuery({
    queryKey: ["juanApparatus", textId, juanNum],
    queryFn: () => getJuanApparatus(Number(textId), juanNum),
    enabled: apparatusOn && !!textId,
    staleTime: 3600000,
  });
  // Number aligned entries 1..N in reading order, converting the backend's
  // Python code-point offsets to JS UTF-16 offsets (see cpToU16Map).
  const apparatusNumbered = useMemo<ApparatusNumbered[]>(() => {
    const raw = content?.content;
    if (!apparatusData?.entries || !raw) return [];
    const m = cpToU16Map(raw);
    const conv = (cp: number) => (cp >= 0 && cp < m.length ? m[cp] : m[m.length - 1]);
    return [...apparatusData.entries]
      .sort((a, b) => a.char_start - b.char_start)
      .map((entry, idx) => ({ entry, no: idx + 1, start: conv(entry.char_start), end: conv(entry.char_end) }));
  }, [apparatusData, content?.content]);

  // CBETA <lb> line anchors for citation locating + URN scroll. Fetched for
  // every juan (small read); offsets converted code-point → UTF-16 like apparatus.
  const { data: lineAnchorData } = useQuery({
    queryKey: ["juanLineAnchors", textId, juanNum],
    queryFn: () => getJuanLineAnchors(Number(textId), juanNum),
    enabled: !!textId,
    staleTime: 3600000,
  });

  // 读诵音频：只有预生成过的卷才有，404 是正常态（不重试、不报错）。
  const { data: audioData } = useQuery({
    queryKey: ["juanAudio", textId, juanNum],
    queryFn: () => getJuanAudio(Number(textId), juanNum),
    // 只有本卷真有音频才问：此前每换一卷都无条件请求，只有心經有音频，其余全是 404。
    enabled: !!textId && content?.has_audio === true,
    staleTime: 3600000,
    retry: false,
  });
  const audioPlayer = useAudioPlayer();
  const lineAnchors = useMemo<LineAnchorConv[]>(() => {
    const raw = content?.content;
    if (!lineAnchorData?.anchors || !raw) return [];
    const m = cpToU16Map(raw);
    const conv = (cp: number) => (cp >= 0 && cp < m.length ? m[cp] : m[m.length - 1]);
    return lineAnchorData.anchors.map((a) => ({ off: conv(a.char_offset), ref: a.line_ref }));
  }, [lineAnchorData, content?.content]);

  // One context drives the inline layers: apparatus markers (only when toggled on)
  // and always-embedded zero-width line anchors (so selection/URN can locate a line).
  const readerCtx: ReaderCtx = (apparatusOn && apparatusNumbered.length) || lineAnchors.length
    ? { numbered: apparatusOn ? apparatusNumbered : [], lineAnchors, t }
    : null;

  // URN deep-link: ?anchor=p0001a09 → scroll to that CBETA line + brief flash.
  //
  // Keeps trying for a second instead of looking once. `lineAnchors` being
  // non-empty means the *data* arrived, not that React has painted the spans
  // that carry it — a single requestAnimationFrame lands in the gap, finds
  // nothing, and returns. That is what it did in production: the target line
  // was in the DOM (verified: 640 anchors rendered, the wanted one 2,940px
  // down) and scrollIntoView on it worked when called by hand, but the page
  // sat at the top of the juan. Every URN, verify_quote hit and commentary
  // link that carried an anchor silently dropped the reader at the top.
  useEffect(() => {
    const anchorParam = searchParams.get("anchor");
    if (!anchorParam || !lineAnchors.length) return;
    const ref = anchorParam.replace(/^p/, "");
    let raf = 0;
    let flash: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    let tries = 0;

    const attempt = () => {
      if (cancelled) return;
      const el = readerContentRef.current?.querySelector<HTMLElement>(
        `.cbeta-line[data-ref="${CSS.escape(ref)}"]`,
      );
      if (!el) {
        // ~1s at 60fps. Give up quietly after that: the anchor may belong to
        // another juan, and nudging the reader somewhere arbitrary is worse
        // than leaving it where the reader put it.
        if (tries++ < 60) raf = requestAnimationFrame(attempt);
        return;
      }
      // Instant, not smooth. Measured on prod: a smooth scrollIntoView to this
      // line left .reader-container at scrollTop 0 even six seconds later,
      // while the same call without `behavior` landed it at 23,315 — a juan is
      // tens of thousands of pixels tall and the smooth path never completes
      // over that distance in this container. Instant is also what a deep link
      // wants: arrive at the line, don't animate past everything before it.
      el.scrollIntoView({ block: "center" });
      const p = el.closest("p");
      if (p) {
        p.classList.add("cbeta-line-flash");
        flash = setTimeout(() => p.classList.remove("cbeta-line-flash"), 2200);
      }
    };

    raf = requestAnimationFrame(attempt);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      if (flash) clearTimeout(flash);
    };
  }, [searchParams, lineAnchors, juanNum]);

  // 播到哪，高亮到哪。复用 URN 深链已有的 .cbeta-line 定位机制 ——
  // 那里是瞬时 flash，这里是持续态。
  //
  // ⚠️ 自动滚屏必须真机验收：behavior:"smooth" 在 CDP 驱动的浏览器里
  //    完全不推进（疑 rAF 节流），CDP 下看不到问题不代表生产没问题。
  useEffect(() => {
    const root = readerContentRef.current;
    const raw = content?.content;
    if (!root || !raw || !audioData) return;
    const cur = audioPlayer.cueIndex;
    const isThisJuan =
      audioPlayer.track?.textId === Number(textId) && audioPlayer.track?.juanNum === juanNum;

    const clear = () =>
      root
        .querySelectorAll<HTMLElement>(".cbeta-line-playing")
        .forEach((el) => el.classList.remove("cbeta-line-playing"));

    if (!isThisJuan || cur < 0) {
      clear();
      return;
    }
    const cue = audioData.cues[cur];
    if (!cue) return;

    // cue.char_start 是 code-point 偏移，与 lineAnchors 同坐标系；
    // 取「不晚于该点」的最后一个行锚，即这一段所在的 CBETA 行。
    const m = cpToU16Map(raw);
    const startU16 = cue.char_start < m.length ? m[cue.char_start] : m[m.length - 1];
    let target: LineAnchorConv | null = null;
    for (const a of lineAnchors) {
      if (a.off <= startU16) target = a;
      else break;
    }
    if (!target) return;

    const el = root.querySelector<HTMLElement>(
      `.cbeta-line[data-ref="${CSS.escape(target.ref)}"]`,
    );
    if (!el) return;
    clear();
    const line = el.closest("p") ?? el;
    line.classList.add("cbeta-line-playing");

    // 只在该行滚出视野时才滚 —— 逐句跟随时每句都重新居中会晃得难受。
    //
    // ⚠️ 瞬时，不要 behavior:"smooth"。#1173 在生产上实测过：平滑
    // scrollIntoView 到某一行，六秒后 .reader-container 的 scrollTop 仍是 0，
    // 而去掉 behavior 的同一调用落到了 23,315 —— 一卷有几万像素高，
    // 平滑路径在这个容器里根本走不完。
    const box = line.getBoundingClientRect();
    const view = root.getBoundingClientRect();
    if (box.top < view.top || box.bottom > view.bottom) {
      line.scrollIntoView({ block: "center" });
    }
  }, [
    audioPlayer.cueIndex,
    audioPlayer.track,
    audioData,
    content,
    lineAnchors,
    textId,
    juanNum,
  ]);

  const changeFontSize = (delta: number) => {
    setFontSize((prev) => {
      const next = Math.min(Math.max(prev + delta, FONT_SIZE_MIN), FONT_SIZE_MAX);
      try { localStorage.setItem(FONT_SIZE_KEY, String(next)); } catch { /* noop */ }
      return next;
    });
  };

  // 关闭态的入口：两种形态（内联 / 抽屉）共用同一颗浮动按钮。
  const aiFab = (
    <Tooltip title={t("reader.ai.title")} placement="left">
      <Button
        className="reader-ai-fab"
        type="primary"
        shape="circle"
        size="large"
        icon={<RobotOutlined />}
        onClick={() => setAiPanelOpen(true)}
        aria-label={t("reader.ai.title")}
      />
    </Tooltip>
  );

  return (
    <div className={`reader-with-sidebar${!narrow && (aiPanelOpen || parallelPanelOpen) ? " reader-ai-active" : ""}`}>
    <div className={`reader-container${compareLang ? " reader-bilingual" : ""}`}>
      <Helmet>
        <title>
          {content?.title_zh
            ? t("reader.seo.title", { title: content.title_zh, n: juanNum })
            : t("reader.seo.online_reading")}
        </title>
      </Helmet>

      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          {
            title: (
              <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}>
                <HomeOutlined /> {t("reader.breadcrumb.home")}
              </span>
            ),
          },
          {
            title: (
              <span
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/texts/${textId}`)}
              >
                {t("reader.breadcrumb.detail")}
              </span>
            ),
          },
          { title: t("reader.breadcrumb.online_reading") },
        ]}
      />

      {/* Header */}
      <div className="reader-header">
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          {content?.title_zh || juanList?.title_zh || t("reader.loading")}
          {content?.canon_label && (
            <Tooltip
              title={t("reader.canon.tooltip")}
              placement="right"
            >
              <Tag
                color="geekblue"
                style={{
                  marginLeft: 12,
                  verticalAlign: "middle",
                  fontSize: 13,
                  fontWeight: "normal",
                }}
              >
                {content.canon_label}
              </Tag>
            </Tooltip>
          )}
        </Typography.Title>

        {/* 数据源署名。上面的徽章是**藏经名**（大正藏 / 甘珠尔 / 巴利三藏），
            不是来源 —— CBETA(CC BY-NC-SA) 与 84000 都把署名列为许可条件，
            而 84000 的条款明确「只写译者不写 84000 本身不算数」。 */}
        <SourceAttribution textId={textId} />

        <div className="reader-nav">
          <Select
            className="juan-select"
            value={juanNum}
            onChange={setJuanNum}
            options={
              juanList?.juans.map((j) => ({
                value: j.juan_num,
                label: t("reader.juan.option", {
                  n: j.juan_num,
                  chars: j.char_count.toLocaleString(),
                }),
              })) || [{ value: 1, label: t("reader.juan.first") }]
            }
          />
          <div className="nav-btn-group">
            <Button
              icon={<LeftOutlined />}
              disabled={!content?.prev_juan}
              onClick={() =>
                content?.prev_juan && setJuanNum(content.prev_juan)
              }
            >
              {t("reader.nav.prev")}
            </Button>
            <Button
              disabled={!content?.next_juan}
              onClick={() =>
                content?.next_juan && setJuanNum(content.next_juan)
              }
            >
              {t("reader.nav.next")} <RightOutlined />
            </Button>
          </div>
          <Button
            size="small"
            icon={bookmarked ? <HeartFilled style={{ color: "var(--fj-accent)" }} /> : <HeartOutlined />}
            loading={bookmarkLoading}
            onClick={toggleBookmark}
          >
            {bookmarked ? t("reader.bookmark.added") : t("reader.bookmark.add")}
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => setAnnotationOpen(true)}
          >
            {t("reader.annotation.button")}
          </Button>
          <Button
            size="small"
            icon={<BookOutlined />}
            onClick={() => setCitationOpen(true)}
          >
            {t("reader.citation.button")}
          </Button>
          <Dropdown
            trigger={["click"]}
            menu={{
              items: (["txt", "html", "docx", "epub"] as const).flatMap((fmt) => [
                {
                  key: `${fmt}-juan`,
                  label: `${t(`reader.export.${fmt}`)} · ${t("reader.export.this_juan")}`,
                  onClick: () => downloadExport(fmt, juanNum),
                },
                {
                  key: `${fmt}-all`,
                  label: `${t(`reader.export.${fmt}`)} · ${t("reader.export.whole_text")}`,
                  onClick: () => downloadExport(fmt, null),
                },
              ]),
            }}
          >
            <Button size="small" icon={<DownloadOutlined />}>
              {t("reader.export.button")}
            </Button>
          </Dropdown>
          <Tooltip title={t("reader.apparatus.tooltip")}>
            <Button
              size="small"
              type={apparatusOn ? "primary" : "default"}
              icon={<DiffOutlined />}
              onClick={() => setApparatusOn((v) => !v)}
            >
              {t("reader.apparatus.toggle")}
            </Button>
          </Tooltip>
          {audioData && (
            <Tooltip title={t("reader.audio.tooltip")}>
              <Button
                size="small"
                type={
                  audioPlayer.track?.textId === Number(textId) &&
                  audioPlayer.track?.juanNum === juanNum
                    ? "primary"
                    : "default"
                }
                icon={<SoundOutlined />}
                onClick={() => {
                  // 意图信号：点了按钮 ≠ 听完，两个数的比值才是转化率
                  trackAudio("audio_open", Number(textId), juanNum);
                  audioPlayer.play({
                    textId: Number(textId),
                    juanNum,
                    title: t("reader.seo.title", {
                      title: content?.title_zh ?? "",
                      n: juanNum,
                    }),
                    audio: audioData,
                  });
                }}
              >
                {t("reader.audio.button")}
              </Button>
            </Tooltip>
          )}
          <Tooltip title={t("reader.parallel.tooltip")}>
            <Button
              size="small"
              type={parallelPanelOpen ? "primary" : "default"}
              icon={<GlobalOutlined />}
              onClick={() => setParallelPanelOpen((v) => !v)}
            >
              {t("reader.parallel.button")}
            </Button>
          </Tooltip>
          {textDetail?.kabc_url && (
            <Tooltip title={t("reader.kabc.tooltip", { k: textDetail.goryeo_k })}>
              <Button
                size="small"
                icon={<GlobalOutlined />}
                onClick={() =>
                  window.open(
                    // Jump to the current juan in KABC: work URL + _T_{juan:03d}
                    // (Goryeo juan numbering matches Taishō for the vast majority).
                    `${textDetail.kabc_url}_T_${String(juanNum).padStart(3, "0")}`,
                    "_blank",
                    "noopener",
                  )
                }
              >
                {t("reader.kabc.button")}
              </Button>
            </Tooltip>
          )}
          <div className="reader-font-controls">
            <Button
              size="small"
              icon={<FontSizeOutlined />}
              disabled={fontSize <= FONT_SIZE_MIN}
              onClick={() => changeFontSize(-FONT_SIZE_STEP)}
            >
              A-
            </Button>
            <span className="font-size-label">{fontSize}</span>
            <Button
              size="small"
              icon={<FontSizeOutlined />}
              disabled={fontSize >= FONT_SIZE_MAX}
              onClick={() => changeFontSize(FONT_SIZE_STEP)}
            >
              A+
            </Button>
          </div>
          {langData && langData.languages.length > 1 && (
            <Select
              value={compareLang}
              onChange={(val) => setCompareLang(val || null)}
              placeholder={t("reader.compare.placeholder")}
              allowClear
              style={{ width: 120 }}
            >
              {langData.languages
                .filter((l) => l !== langData.default_lang)
                .map((l) => (
                  <Select.Option key={l} value={l}>{getLangLabel(l)}</Select.Option>
                ))
              }
            </Select>
          )}
        </div>
      </div>

      {/* Content */}
      <div ref={readerContentRef} style={{ position: "relative" }}>
      {isLoading ? (
        <div style={{ textAlign: "center", padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : content ? (
        compareLang ? (
          <Row gutter={24}>
            <Col xs={24} lg={12}>
              <div className="bilingual-column">
                <div className="bilingual-label">
                  {langData?.default_lang ? getLangLabel(langData.default_lang) : t("reader.compare.original")}
                </div>
                <div
                  className="reader-body"
                  style={{ "--reader-font-size": `${fontSize}px` } as React.CSSProperties}
                >
                  {reflowedContent.map((seg, i) => renderSegment(seg, i, readerCtx))}
                </div>
              </div>
            </Col>
            <Col xs={24} lg={12}>
              <div className="bilingual-column">
                <div className="bilingual-label">{getLangLabel(compareLang)}</div>
                {compareLoading ? (
                  <div style={{ textAlign: "center", padding: 80 }}><Spin /></div>
                ) : (
                  <div
                    className="reader-body"
                    style={{ "--reader-font-size": `${fontSize}px` } as React.CSSProperties}
                  >
                    {compareContent?.content
                      ? reflowedCompare.map((seg, i) => renderSegment(seg, i))
                      : t("reader.empty")}
                  </div>
                )}
              </div>
            </Col>
          </Row>
        ) : (
          <div
            className="reader-body"
            style={{ "--reader-font-size": `${fontSize}px` } as React.CSSProperties}
          >
            {reflowedContent.map((seg, i) => renderSegment(seg, i, readerCtx))}
          </div>
        )
      ) : (
        <Typography.Text type="secondary">{t("reader.empty")}</Typography.Text>
      )}
      <ReaderDictPopover
        state={dictPopover}
        onClose={closeDictPopover}
        onAsk={handleAskXiaojin}
      />
      {lineLocator && content && (
        <div
          className="cbeta-line-locator"
          style={{ position: "fixed", left: lineLocator.x, top: Math.max(lineLocator.y - 40, 8), transform: "translateX(-50%)" }}
        >
          <span className="cbeta-line-locator-ref">{content.cbeta_id} · {lineLocator.ref}</span>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard?.writeText(
                t("reader.lineref.citation", { title: content.title_zh, juan: juanNum, id: content.cbeta_id, ref: lineLocator.ref }),
              );
              message.success(t("reader.lineref.copied"));
            }}
          >
            {t("reader.lineref.copy_citation")}
          </button>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard?.writeText(`fojin:cbeta/${content.cbeta_id}.${juanNum}#p${lineLocator.ref}`);
              message.success(t("reader.lineref.copied"));
            }}
          >
            {t("reader.lineref.copy_link")}
          </button>
        </div>
      )}
      </div>

      {/* Bottom navigation */}
      {content && (
        <div className="reader-bottom-nav">
          <Button
            disabled={!content.prev_juan}
            onClick={() =>
              content.prev_juan && setJuanNum(content.prev_juan)
            }
          >
            <LeftOutlined /> {t("reader.nav.prev")}
          </Button>
          <Button
            disabled={!content.next_juan}
            onClick={() =>
              content.next_juan && setJuanNum(content.next_juan)
            }
          >
            {t("reader.nav.next")} <RightOutlined />
          </Button>
        </div>
      )}

      <CitationGenerator
        textId={textId}
        textData={textDetail}
        open={citationOpen}
        onClose={() => setCitationOpen(false)}
      />

      <AnnotationPanel
        textId={textId}
        juanNum={juanNum}
        visible={annotationOpen}
        onClose={() => setAnnotationOpen(false)}
      />

    </div>

    {/* 多语对读：右侧内联面板 + 拖拽分割条（在 AI 面板左侧） */}
    {parallelPanelOpen && (
      <>
        <div className="reader-ai-divider" onMouseDown={handleParallelDragStart} />
        <div className="reader-ai-sidebar" style={{ width: parallelPanelWidth }}>
          <div className="reader-ai-sidebar-header">
            <span className="reader-ai-sidebar-title"><GlobalOutlined /> {t("reader.parallel.button")}</span>
            <Button type="text" size="small" onClick={() => setParallelPanelOpen(false)}>✕</Button>
          </div>
          <ReaderParallelPanel textId={textId} juanNum={juanNum} />
        </div>
      </>
    )}

    {/* AI 解读：宽屏是最右侧内联面板 + 拖拽分割条；窄屏改底部抽屉 —— 内联侧栏在
        列布局里会把经文挤到看不见（.reader-ai-active 锁高 + 侧栏 60vh），抽屉盖在
        经文之上、随手可关，经文始终留在正常文档流里。 */}
    {narrow ? (
      <>
        <Drawer
          placement="bottom"
          height="62vh"
          open={aiPanelOpen}
          onClose={() => setAiPanelOpen(false)}
          title={<span className="reader-ai-sidebar-title"><RobotOutlined /> {t("reader.ai.title")}</span>}
          rootClassName="reader-ai-drawer"
        >
          <ReaderAIPanel
            textId={textId}
            juanNum={juanNum}
            textTitle={content?.title_zh || textDetail?.title_zh || ""}
            juanContent={content?.content}
            selectedText={aiSelectedText}
            onSelectedTextConsumed={handleSelectedTextConsumed}
          />
        </Drawer>
        {!aiPanelOpen && aiFab}
      </>
    ) : aiPanelOpen ? (
      <>
        <div className="reader-ai-divider" onMouseDown={handleDragStart} />
        <div className="reader-ai-sidebar" style={{ width: aiPanelWidth }}>
          <div className="reader-ai-sidebar-header">
            <span className="reader-ai-sidebar-title"><RobotOutlined /> {t("reader.ai.title")}</span>
            <Button type="text" size="small" onClick={() => setAiPanelOpen(false)}>✕</Button>
          </div>
          <ReaderAIPanel
            textId={textId}
            juanNum={juanNum}
            textTitle={content?.title_zh || textDetail?.title_zh || ""}
            juanContent={content?.content}
            selectedText={aiSelectedText}
            onSelectedTextConsumed={handleSelectedTextConsumed}
          />
        </div>
      </>
    ) : (
      aiFab
    )}

    {/* 回到顶部：落点由 backTopStyle 动态计算（让开 AI 面板与 AI FAB） */}
    {showBackTop && (
      <Tooltip title={t("reader.backtop")} placement="left">
        <Button
          className="reader-backtop-fab"
          style={backTopStyle}
          shape="circle"
          size="large"
          icon={<VerticalAlignTopOutlined />}
          onClick={scrollToTop}
          aria-label={t("reader.backtop")}
        />
      </Tooltip>
    )}
    </div>
  );
}
