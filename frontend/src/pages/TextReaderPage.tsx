import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Typography, Spin, Button, Select, Breadcrumb, Row, Col, message, Tooltip, Tag } from "antd";
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
} from "@ant-design/icons";
import { getJuanList, getJuanContent, getJuanLanguages, getTextDetail, checkBookmark, addBookmark, removeBookmark, searchDictionaryGrouped } from "../api/client";
import { useAuthStore } from "../stores/authStore";
import CitationGenerator from "../components/CitationGenerator";
import AnnotationPanel from "../components/AnnotationPanel";
import ApparatusPanel from "../components/ApparatusPanel";
import { ReaderDictPopover } from "../components/ReaderDictPopover";
import { DICT_POPOVER_INIT, MAX_WORD_LEN, type DictPopoverState } from "../components/ReaderDictPopover.types";
import ReaderAIPanel from "../components/ReaderAIPanel";
import ReaderParallelPanel from "../components/ReaderParallelPanel";

import "../styles/versions-panel.css";
import "../styles/reader.css";

const LANG_LABELS: Record<string, string> = {
  lzh: "中文",
  pi: "巴利文",
  en: "English",
  sa: "梵文",
  bo: "藏文",
  ja: "日本語",
};

const FONT_SIZE_MIN = 14;
const FONT_SIZE_MAX = 28;
const FONT_SIZE_STEP = 2;
const FONT_SIZE_KEY = "fojin-reader-font-size";

/** Segment type for rendering */
type TextSegment =
  | { type: "prose"; text: string }
  | { type: "verse"; text: string }
  | { type: "break" }
  | { type: "head"; text: string }
  | { type: "juan"; text: string }
  | { type: "byline"; text: string }
  | { type: "section"; text: string };

/**
 * Reflow raw text into segments matching CBETA Online layout.
 *
 * CBETA source data has hard line breaks every ~18 chars. We need to:
 * 1. Merge consecutive prose lines into flowing paragraphs
 * 2. Keep verse/gatha (偈颂) lines as separate indented lines
 * 3. Break paragraphs at blank lines and markers like 論曰/頌曰
 *
 * Verse detection: a line is a verse if it ends with ，or 。and the
 * text before the final punctuation contains no other ，。(i.e. it's
 * a single clause per line, typical of Buddhist verse structure).
 * Prose lines have multiple clauses (multiple ，。) within one line.
 */
function reflowText(raw: string): TextSegment[] {
  const lines = raw.split("\n");
  const segments: TextSegment[] = [];
  let proseBuf = "";

  const flushProse = () => {
    if (proseBuf) {
      segments.push({ type: "prose", text: proseBuf });
      proseBuf = "";
    }
  };

  // Verse detection: Buddhist verse lines are typically 5-char or 7-char
  // clauses joined by ，。 at the end, with at most one ，in the middle
  // connecting two equal-length half-lines.
  // e.g. "諸一切種諸冥滅，拔眾生出生死泥，" (7+7 = ~16 chars with punct)
  // vs prose: "聖眾，故先讚德方申敬禮。諸言所表謂佛" (multiple clauses, ~18 chars)
  const isVerse = (line: string): boolean => {
    if (line.length < 4 || line.length > 22) return false;
    // Must end with Chinese punctuation
    if (!/[，。；]$/.test(line)) return false;
    // Count ALL Chinese punctuation in the line
    const allPuncts = (line.match(/[，。、；：！？]/g) || []).length;
    // Strict verse: at most 2 punctuation total (e.g. "五言，五言，" or "七言，")
    // Prose lines typically have 3+ punctuation marks
    if (allPuncts > 2) return false;
    // Lines with whitespace gaps are CBETA verse formatting
    if (/\s{2,}/.test(line)) return true;
    // For lines with exactly 1-2 punctuation, check symmetry
    // Verse halves should be roughly equal length (e.g. 5+5, 7+7)
    if (allPuncts === 2) {
      const parts = line.split(/[，。、；]/);
      if (parts.length >= 2 && parts[0].length > 0 && parts[1].length > 0) {
        const ratio = Math.min(parts[0].length, parts[1].length) / Math.max(parts[0].length, parts[1].length);
        return ratio >= 0.5; // halves within 2:1 ratio
      }
    }
    // Single punctuation at end: likely a verse half-line
    return allPuncts === 1 && line.length <= 12;
  };

  // Structural detection helpers
  const isHead = (line: string, idx: number): boolean => {
    // First non-empty line, short (经名标题), e.g. "長阿含經序"
    if (idx > 2) return false;
    if (line.length > 15 || line.length < 2) return false;
    // Must contain 經/論/律/品/序/疏 etc.
    return /[經论論律品序疏記集傳]/.test(line) && !/[，。；：！？、]/.test(line);
  };

  const isJuan = (line: string): boolean => {
    // 卷标题: e.g. "佛說長阿含經卷第一", "大般若波羅蜜多經卷第二"
    return /卷第?[一二三四五六七八九十百千\d]+/.test(line) && line.length <= 25 && !/[，。]/.test(line);
  };

  const isByline = (line: string): boolean => {
    // 译者署名: e.g. "後秦弘始年佛陀耶舍共竺佛念譯", "長安釋僧肇述"
    return /[譯译述撰注疏記造]$/.test(line) && line.length <= 25 && !/[，。；]/.test(line);
  };

  const isSection = (line: string): boolean => {
    // 品名/章节: e.g. "（一）第一分初大本經第一", "大緣方便經第二"
    // Starts with （number） or contains 品第/分第/經第
    if (/^[（(][一二三四五六七八九十\d]+[）)]/.test(line)) return true;
    if (/[品分經]第[一二三四五六七八九十百\d]+/.test(line) && line.length <= 20 && !/[，。]/.test(line)) return true;
    return false;
  };

  let inVerseBlock = false;
  // Before the first 論曰, verse-like lines are opening verses
  let beforeFirstProse = true;
  let firstNonEmptyIdx = -1;
  let lastNonEmptyLine = "";

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();

    // Blank line → paragraph break, but ONLY if the previous non-empty line
    // ends with sentence-final punctuation. CBETA XML <p> boundaries sometimes
    // fall mid-word (e.g. 淨\n\n色), so we must not break there.
    if (trimmed === "") {
      if (/[。！？」』]$/.test(lastNonEmptyLine)) {
        flushProse();
        segments.push({ type: "break" });
      }
      continue;
    }

    // Track non-empty lines
    lastNonEmptyLine = trimmed;
    if (firstNonEmptyIdx < 0) firstNonEmptyIdx = i;
    const relIdx = i - firstNonEmptyIdx;

    // Structural elements: head, juan, byline, section
    if (isJuan(trimmed)) {
      flushProse();
      segments.push({ type: "juan", text: trimmed });
      continue;
    }

    if (isByline(trimmed)) {
      flushProse();
      segments.push({ type: "byline", text: trimmed });
      continue;
    }

    if (isSection(trimmed)) {
      flushProse();
      segments.push({ type: "section", text: trimmed });
      continue;
    }

    if (isHead(trimmed, relIdx)) {
      flushProse();
      segments.push({ type: "head", text: trimmed });
      continue;
    }

    // Check paragraph markers
    const hasVerseMarker = /頌曰[：:]?|偈曰[：:]?/.test(trimmed);
    const isProseMarker = /^(論曰|述曰|疏曰|解曰|釋曰)/.test(trimmed);

    if (isProseMarker) {
      beforeFirstProse = false;
      inVerseBlock = false;
      if (proseBuf) flushProse();
      proseBuf = trimmed;
      continue;
    }

    // "頌曰" anywhere in line triggers verse mode
    if (hasVerseMarker) {
      beforeFirstProse = false;
      proseBuf += trimmed;
      flushProse();
      inVerseBlock = true;
      continue;
    }

    // Verse mode (after 頌曰 or at opening before first 論曰)
    if ((inVerseBlock || beforeFirstProse) && isVerse(trimmed)) {
      flushProse();
      segments.push({ type: "verse", text: trimmed });
      continue;
    }

    // If we were in verse block but line doesn't look like verse, exit
    if (inVerseBlock && !isVerse(trimmed)) {
      inVerseBlock = false;
    }
    if (beforeFirstProse && !isVerse(trimmed)) {
      beforeFirstProse = false;
    }

    // Default: merge into prose paragraph
    proseBuf += trimmed;
  }
  flushProse();
  return segments;
}

function renderSegment(seg: TextSegment, i: number) {
  switch (seg.type) {
    case "break": return <br key={i} />;
    case "head": return <p key={i} className="text-head">{seg.text}</p>;
    case "juan": return <p key={i} className="text-juan">{seg.text}</p>;
    case "byline": return <p key={i} className="text-byline">{seg.text}</p>;
    case "section": return <p key={i} className="text-section">{seg.text}</p>;
    case "verse": return <p key={i} className="text-verse">{seg.text}</p>;
    case "prose": return <p key={i} className="text-prose">{seg.text}</p>;
  }
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
  // resumeRef 在首次渲染时一次性决定，供后续滚动恢复 effect 消费。
  const resumeRef = useRef<{ juan: number; ratio: number } | null>(null);
  const [juanNum, setJuanNum] = useState(() => {
    const last = highlightChunkParam ? null : getLastPosition(Number(id));
    if (initialJuanParam && Number.isFinite(initialJuan) && initialJuan > 0) {
      // URL 显式指定卷：尊重 URL；若与记录同卷（如详情页"继续阅读"），仍恢复滚动。
      if (last && last.juan === initialJuan && last.ratio > 0.03) {
        resumeRef.current = { juan: initialJuan, ratio: last.ratio };
      }
      return initialJuan;
    }
    if (last && last.juan > 0 && (last.juan > 1 || last.ratio > 0.03)) {
      resumeRef.current = { juan: last.juan, ratio: last.ratio };
      return last.juan;
    }
    return 1;
  });
  const [fontSize, setFontSize] = useState(getInitialFontSize);
  const [citationOpen, setCitationOpen] = useState(false);
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [apparatusOpen, setApparatusOpen] = useState(false);
  const [parallelPanelOpen, setParallelPanelOpen] = useState(false);

  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  const [compareLang, setCompareLang] = useState<string | null>(null);
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const readerContentRef = useRef<HTMLDivElement>(null);

  // AI panel state
  const [aiPanelOpen, setAiPanelOpen] = useState(true);
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
  const closeDictPopover = useCallback(() => setDictPopover(DICT_POPOVER_INIT), []);

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
      message.info("请登录后收藏");
      return;
    }
    setBookmarkLoading(true);
    try {
      if (bookmarked) {
        await removeBookmark(textId);
        message.success("已取消收藏");
      } else {
        await addBookmark(textId);
        message.success("已收藏");
      }
      queryClient.invalidateQueries({ queryKey: ["bookmark", textId] });
    } catch {
      message.error("操作失败");
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
      message.info(`已定位到上次阅读位置 · 第${resume.juan}卷`, 2.5);
    });
    return () => cancelAnimationFrame(raf);
  }, [content, juanNum]);

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
        title: content.title_zh || `文本 ${textId}`,
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
  }, [content, textId, juanNum]);

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
  const reflowedContent = useMemo(
    () => (content?.content ? reflowText(content.content) : []),
    [content?.content],
  );
  const reflowedCompare = useMemo(
    () => (compareContent?.content ? reflowText(compareContent.content) : []),
    [compareContent?.content],
  );

  const changeFontSize = (delta: number) => {
    setFontSize((prev) => {
      const next = Math.min(Math.max(prev + delta, FONT_SIZE_MIN), FONT_SIZE_MAX);
      try { localStorage.setItem(FONT_SIZE_KEY, String(next)); } catch { /* noop */ }
      return next;
    });
  };

  return (
    <div className={`reader-with-sidebar${aiPanelOpen || parallelPanelOpen ? " reader-ai-active" : ""}`}>
    <div className={`reader-container${compareLang ? " reader-bilingual" : ""}`}>
      <Helmet>
        <title>
          {content?.title_zh
            ? `${content.title_zh} 第${juanNum}卷`
            : "在线阅读"}{" "}
          — 佛津
        </title>
      </Helmet>

      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          {
            title: (
              <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}>
                <HomeOutlined /> 首页
              </span>
            ),
          },
          {
            title: (
              <span
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/texts/${textId}`)}
              >
                经典详情
              </span>
            ),
          },
          { title: "在线阅读" },
        ]}
      />

      {/* Header */}
      <div className="reader-header">
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          {content?.title_zh || juanList?.title_zh || "加载中..."}
          {content?.canon_label && (
            <Tooltip
              title="本经所属藏经（底本）— 据 CBETA 编号推导"
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

        <div className="reader-nav">
          <Select
            className="juan-select"
            value={juanNum}
            onChange={setJuanNum}
            options={
              juanList?.juans.map((j) => ({
                value: j.juan_num,
                label: `第 ${j.juan_num} 卷 (${j.char_count.toLocaleString()}字)`,
              })) || [{ value: 1, label: "第 1 卷" }]
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
              上一卷
            </Button>
            <Button
              disabled={!content?.next_juan}
              onClick={() =>
                content?.next_juan && setJuanNum(content.next_juan)
              }
            >
              下一卷 <RightOutlined />
            </Button>
          </div>
          <Button
            size="small"
            icon={bookmarked ? <HeartFilled style={{ color: "var(--fj-accent)" }} /> : <HeartOutlined />}
            loading={bookmarkLoading}
            onClick={toggleBookmark}
          >
            {bookmarked ? "已收藏" : "收藏"}
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => setAnnotationOpen(true)}
          >
            标注
          </Button>
          <Button
            size="small"
            icon={<BookOutlined />}
            onClick={() => setCitationOpen(true)}
          >
            引用
          </Button>
          <Tooltip title="校勘异文（底本与宋/元/明等校本的异读）">
            <Button
              size="small"
              type={apparatusOpen ? "primary" : "default"}
              icon={<DiffOutlined />}
              onClick={() => setApparatusOpen((v) => !v)}
            >
              校勘
            </Button>
          </Tooltip>
          <Tooltip title="跨藏对照（其他版本 · 经级/段级对读）">
            <Button
              size="small"
              type={parallelPanelOpen ? "primary" : "default"}
              icon={<GlobalOutlined />}
              onClick={() => setParallelPanelOpen((v) => !v)}
            >
              跨藏对照
            </Button>
          </Tooltip>
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
              placeholder="对照语言"
              allowClear
              style={{ width: 120 }}
            >
              {langData.languages
                .filter((l) => l !== langData.default_lang)
                .map((l) => (
                  <Select.Option key={l} value={l}>{LANG_LABELS[l] || l}</Select.Option>
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
                <div className="bilingual-label">{LANG_LABELS[langData?.default_lang || ""] || "原文"}</div>
                <div
                  className="reader-body"
                  style={{ "--reader-font-size": `${fontSize}px` } as React.CSSProperties}
                >
                  {reflowedContent.map(renderSegment)}
                </div>
              </div>
            </Col>
            <Col xs={24} lg={12}>
              <div className="bilingual-column">
                <div className="bilingual-label">{LANG_LABELS[compareLang] || compareLang}</div>
                {compareLoading ? (
                  <div style={{ textAlign: "center", padding: 80 }}><Spin /></div>
                ) : (
                  <div
                    className="reader-body"
                    style={{ "--reader-font-size": `${fontSize}px` } as React.CSSProperties}
                  >
                    {compareContent?.content
                      ? reflowedCompare.map(renderSegment)
                      : "暂无内容"}
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
            {reflowedContent.map(renderSegment)}
          </div>
        )
      ) : (
        <Typography.Text type="secondary">暂无内容</Typography.Text>
      )}
      <ReaderDictPopover
        state={dictPopover}
        onClose={closeDictPopover}
        onAsk={handleAskXiaojin}
      />
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
            <LeftOutlined /> 上一卷
          </Button>
          <Button
            disabled={!content.next_juan}
            onClick={() =>
              content.next_juan && setJuanNum(content.next_juan)
            }
          >
            下一卷 <RightOutlined />
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

      <ApparatusPanel
        textId={textId}
        juanNum={juanNum}
        visible={apparatusOpen}
        onClose={() => setApparatusOpen(false)}
      />

    </div>

    {/* 多语对读：右侧内联面板 + 拖拽分割条（在 AI 面板左侧） */}
    {parallelPanelOpen && (
      <>
        <div className="reader-ai-divider" onMouseDown={handleParallelDragStart} />
        <div className="reader-ai-sidebar" style={{ width: parallelPanelWidth }}>
          <div className="reader-ai-sidebar-header">
            <span className="reader-ai-sidebar-title"><GlobalOutlined /> 跨藏对照</span>
            <Button type="text" size="small" onClick={() => setParallelPanelOpen(false)}>✕</Button>
          </div>
          <ReaderParallelPanel textId={textId} juanNum={juanNum} />
        </div>
      </>
    )}

    {/* AI 解读：最右侧内联面板 + 拖拽分割条 */}
    {aiPanelOpen ? (
      <>
        <div className="reader-ai-divider" onMouseDown={handleDragStart} />
        <div className="reader-ai-sidebar" style={{ width: aiPanelWidth }}>
          <div className="reader-ai-sidebar-header">
            <span className="reader-ai-sidebar-title"><RobotOutlined /> AI 解读</span>
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
      <Tooltip title="AI 解读" placement="left">
        <Button
          className="reader-ai-fab"
          type="primary"
          shape="circle"
          size="large"
          icon={<RobotOutlined />}
          onClick={() => setAiPanelOpen(true)}
          aria-label="AI 解读"
        />
      </Tooltip>
    )}
    </div>
  );
}