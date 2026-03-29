import { useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Typography, Spin, Button, Select, Breadcrumb, Row, Col, message } from "antd";
import {
  HomeOutlined,
  LeftOutlined,
  RightOutlined,
  FontSizeOutlined,
  BookOutlined,
  EditOutlined,
  HeartOutlined,
  HeartFilled,
} from "@ant-design/icons";
import { getJuanList, getJuanContent, getJuanLanguages, getTextDetail, checkBookmark, addBookmark, removeBookmark } from "../api/client";
import { useAuthStore } from "../stores/authStore";
import CitationGenerator from "../components/CitationGenerator";
import AnnotationPanel from "../components/AnnotationPanel";
import AskXiaojinButton from "../components/AskXiaojinButton";
import ReaderSidebar from "../components/ReaderSidebar";
import "../styles/reader.css";

const LANG_LABELS: Record<string, string> = {
  lzh: "文言文",
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
type TextSegment = { type: "prose"; text: string } | { type: "verse"; text: string } | { type: "break" };

/**
 * Detect if a line is a verse/gatha (偈颂).
 * Verses are short lines with balanced comma/period patterns,
 * like "諸一切種諸冥滅，拔眾生出生死泥，"
 */
function isVerseLine(line: string): boolean {
  if (line.length > 30 || line.length < 4) return false;
  // Count punctuation marks typical of verse: ，。、；
  const puncts = (line.match(/[，。、；]/g) || []).length;
  // Verses typically have 1-3 punctuation marks in a short line
  if (puncts >= 1 && line.length <= 25) return true;
  // Lines with large whitespace gaps (CBETA verse formatting)
  if (/\s{2,}/.test(line) && puncts >= 1) return true;
  return false;
}

/**
 * Reflow raw text into segments matching CBETA Online layout.
 * - Blank lines → paragraph breaks
 * - Short balanced lines → verses (keep as individual lines)
 * - Consecutive long lines → merge into prose paragraphs
 * - "論曰：" / "頌曰：" at line start → new paragraph
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

  for (const line of lines) {
    const trimmed = line.trim();

    // Blank line → paragraph break
    if (trimmed === "") {
      flushProse();
      segments.push({ type: "break" });
      continue;
    }

    // Check if this line starts a new paragraph (論曰：、頌曰： etc.)
    const startsNewPara = /^(論曰|頌曰|述曰|疏曰|解曰|釋曰|問[：:]|答[：:])/.test(trimmed);

    if (isVerseLine(trimmed)) {
      flushProse();
      segments.push({ type: "verse", text: trimmed });
    } else if (startsNewPara && proseBuf) {
      flushProse();
      proseBuf = trimmed;
    } else {
      proseBuf += trimmed;
    }
  }
  flushProse();
  return segments;
}

function getInitialFontSize(): number {
  try {
    const v = localStorage.getItem(FONT_SIZE_KEY);
    if (v) return Math.min(Math.max(Number(v), FONT_SIZE_MIN), FONT_SIZE_MAX);
  } catch { /* noop */ }
  return 18;
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
                  {reflowText(content.content).map((para, i) =>
                    para.type === "break" ? <br key={i} /> : para.type === "verse" ? <p key={i} style={{ margin: "0 0 0.2em", paddingLeft: "4em", color: "var(--fj-ink)" }}>{para.text}</p> : <p key={i} style={{ margin: "0 0 1em" }}>{para.text}</p>
                  )}
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
                      ? reflowText(compareContent.content).map((para, i) =>
                          para.type === "break" ? <br key={i} /> : para.type === "verse" ? <p key={i} style={{ margin: "0 0 0.2em", paddingLeft: "4em", color: "var(--fj-ink)" }}>{para.text}</p> : <p key={i} style={{ margin: "0 0 1em" }}>{para.text}</p>
                        )
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
            {reflowText(content.content).map((para, i) =>
              para.type === "break" ? <br key={i} /> : para.type === "verse" ? <p key={i} style={{ margin: "0 0 0.2em", paddingLeft: "4em", color: "var(--fj-ink)" }}>{para.text}</p> : <p key={i} style={{ margin: "0 0 1em" }}>{para.text}</p>
            )}
          </div>
        )
      ) : (
        <Typography.Text type="secondary">暂无内容</Typography.Text>
      )}
      <AskXiaojinButton
        containerRef={readerContentRef}
        source={`${content?.title_zh || ""}第${juanNum}卷`}
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
    </div>
    <ReaderSidebar textId={textId} juanNum={juanNum} />
    </div>
  );
}