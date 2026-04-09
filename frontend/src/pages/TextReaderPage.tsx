import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Typography, Spin, Button, Select, Breadcrumb, Row, Col, Drawer, message } from "antd";
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
} from "@ant-design/icons";
import { getJuanList, getJuanContent, getJuanLanguages, getTextDetail, checkBookmark, addBookmark, removeBookmark, searchDictionaryGrouped } from "../api/client";
import type { DictGroupedSearchResponse } from "../api/client";
import { useAuthStore } from "../stores/authStore";
import CitationGenerator from "../components/CitationGenerator";
import AnnotationPanel from "../components/AnnotationPanel";
import AskXiaojinButton from "../components/AskXiaojinButton";
import ReaderAIPanel from "../components/ReaderAIPanel";
import TextVersionsPanel from "../components/TextVersionsPanel";
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

/** 划词查辞典浮层状态 */
interface DictPopoverState {
  visible: boolean;
  text: string;
  x: number;
  y: number;
  loading: boolean;
  result: DictGroupedSearchResponse | null;
}

const DICT_POPOVER_INIT: DictPopoverState = {
  visible: false,
  text: "",
  x: 0,
  y: 0,
  loading: false,
  result: null,
};

/** 划词查辞典浮层组件 */
function DictPopover({
  state,
  onClose,
}: {
  state: DictPopoverState;
  onClose: () => void;
}) {
  if (!state.visible) return null;

  // 选最佳释义：优先中文释义类辞典（definition 最长的），排除多语对照类短释义
  const HIGH_QUALITY_SOURCES = [
    "dila-dfb", "foguang", "nti-reader", "bs-faxiang", "bs-changjianci",
    "zhonghua-baike", "bs-yiqiejing-yinyi", "bs-agama", "weishi",
    "abhidharma", "tiantai", "sanzang-fashu",
  ];
  let bestEntry = state.result?.groups?.[0]?.entries?.[0];
  if (state.result?.groups) {
    for (const g of state.result.groups) {
      if (HIGH_QUALITY_SOURCES.includes(g.source_code) && g.entries[0]) {
        bestEntry = g.entries[0];
        break;
      }
    }
  }

  // 计算浮层位置
  const popW = 220;
  let left = state.x - popW / 2;
  let top = state.y + 8;

  if (left < 8) left = 8;
  if (left + popW > window.innerWidth - 8) left = window.innerWidth - popW - 8;
  if (top + 120 > window.innerHeight - 8) {
    top = state.y - 120;
    if (top < 8) top = 8;
  }

  return (
    <div
      className="reader-dict-popover"
      style={{ left, top }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="reader-dict-popover-header">
        <span className="reader-dict-popover-keyword">{state.text}</span>
        <button className="reader-dict-popover-close" onClick={onClose}>✕</button>
      </div>
      <div className="reader-dict-popover-body">
        {state.loading ? (
          <div style={{ textAlign: "center", padding: 12 }}>
            <Spin size="small" />
          </div>
        ) : bestEntry ? (
          <div className="reader-dict-popover-entry">
            <div className="reader-dict-popover-def">
              {bestEntry.definition.length > 30
                ? bestEntry.definition.slice(0, 30) + "…"
                : bestEntry.definition}
            </div>
          </div>
        ) : (
          <div className="reader-dict-popover-empty">未找到释义</div>
        )}
      </div>
      <div className="reader-dict-popover-footer">
        <Link to={`/dictionary?q=${encodeURIComponent(state.text)}`} onClick={onClose}>
          查看全部释义 →
        </Link>
      </div>
    </div>
  );
}

export default function TextReaderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const textId = Number(id);
  const [juanNum, setJuanNum] = useState(1);
  const [fontSize, setFontSize] = useState(getInitialFontSize);
  const [citationOpen, setCitationOpen] = useState(false);
  const [annotationOpen, setAnnotationOpen] = useState(false);
  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  const [compareLang, setCompareLang] = useState<string | null>(null);
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const readerContentRef = useRef<HTMLDivElement>(null);

  // AI Drawer state
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [aiDrawerWidth, setAiDrawerWidth] = useState(480);
  const [aiSelectedText, setAiSelectedText] = useState<string | undefined>();

  const openAiDrawer = useCallback(() => {
    // Align drawer left edge: with versions-panel if present, otherwise with reader-container right edge
    const vp = document.querySelector(".versions-panel");
    if (vp) {
      const w = window.innerWidth - vp.getBoundingClientRect().left;
      setAiDrawerWidth(Math.max(w, 360));
    } else {
      const rc = document.querySelector(".reader-container");
      if (rc) {
        const w = window.innerWidth - rc.getBoundingClientRect().right - 8;
        setAiDrawerWidth(Math.max(w, 360));
      } else {
        setAiDrawerWidth(400);
      }
    }
    setAiDrawerOpen(true);
  }, []);

  const handleAskXiaojin = useCallback((text: string) => {
    setAiSelectedText(text);
    openAiDrawer();
  }, [openAiDrawer]);
  const handleSelectedTextConsumed = useCallback(() => {
    setAiSelectedText(undefined);
  }, []);

  // 划词查辞典
  const [dictPopover, setDictPopover] = useState<DictPopoverState>(DICT_POPOVER_INIT);
  const closeDictPopover = useCallback(() => setDictPopover(DICT_POPOVER_INIT), []);

  const handleTextSelect = useCallback(async () => {
    const sel = window.getSelection();
    const text = sel?.toString().trim() || "";
    if (text.length < 1 || text.length > 20) return;

    // 获取选中文字的位置
    const range = sel?.getRangeAt(0);
    if (!range) return;
    const rect = range.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.bottom;

    setDictPopover({ visible: true, text, x, y, loading: true, result: null });

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

  const { data: compareContent, isLoading: compareLoading } = useQuery({
    queryKey: ["juanContent", textId, juanNum, compareLang],
    queryFn: () => getJuanContent(Number(textId), juanNum, compareLang!),
    enabled: !!compareLang,
    staleTime: 3600000,
  });

  const changeFontSize = (delta: number) => {
    setFontSize((prev) => {
      const next = Math.min(Math.max(prev + delta, FONT_SIZE_MIN), FONT_SIZE_MAX);
      try { localStorage.setItem(FONT_SIZE_KEY, String(next)); } catch { /* noop */ }
      return next;
    });
  };

  return (
    <div className="reader-with-sidebar">
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
        <Typography.Title level={3}>
          {content?.title_zh || juanList?.title_zh || "加载中..."}
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
                  {reflowText(content.content).map(renderSegment)}
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
                      ? reflowText(compareContent.content).map(renderSegment)
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
            {reflowText(content.content).map(renderSegment)}
          </div>
        )
      ) : (
        <Typography.Text type="secondary">暂无内容</Typography.Text>
      )}
      <AskXiaojinButton
        containerRef={readerContentRef}
        onAsk={handleAskXiaojin}
      />
      <DictPopover state={dictPopover} onClose={closeDictPopover} />
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
    </div>
    <TextVersionsPanel textId={textId} />

    {/* AI 解读浮动按钮 */}
    <Button
      className="reader-ai-fab"
      type="primary"
      shape="circle"
      size="large"
      icon={<RobotOutlined />}
      onClick={openAiDrawer}
    />

    {/* AI 解读抽屉面板 */}
    <Drawer
      title="AI 解读"
      placement="right"
      width={aiDrawerWidth}
      mask={false}
      open={aiDrawerOpen}
      onClose={() => setAiDrawerOpen(false)}
      className="reader-ai-drawer"
      styles={{ body: { padding: 0 } }}
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
    </div>
  );
}