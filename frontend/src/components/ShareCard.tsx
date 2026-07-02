import { useEffect, useRef, useState } from "react";
import { Modal, Button, message, Spin } from "antd";
import { DownloadOutlined, CopyOutlined, PictureOutlined } from "@ant-design/icons";
import html2canvas from "html2canvas-pro";
import QRCode from "qrcode";
import { useTranslation } from "react-i18next";
import { createSharedQA, type ChatSource } from "../api/client";

interface ShareCardProps {
  open: boolean;
  onClose: () => void;
  question: string;
  answer: string;
  sources: ChatSource[] | null;
}

const CARD_WIDTH = 720;
const FALLBACK_SHARE_URL = "https://fojin.app/chat";

function sanitizeFilenameSegment(text: string): string {
  const blocked = new Set('"《》【】「」『』〈〉()（）<>:"/\\|?*');
  let out = "";
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    if (code < 0x20) continue;
    if (blocked.has(ch)) continue;
    out += ch;
  }
  return out.replace(/\s+/g, "").slice(0, 18);
}

function buildFilename(question: string, fallbackTitle: string): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const datePart = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const titlePart = sanitizeFilenameSegment(question || fallbackTitle) || fallbackTitle;
  return `fojin-${datePart}-${titlePart}.png`;
}

function stripMarkdown(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "• ")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/^\s*>\s+/gm, "")
    .replace(/^-{3,}$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function truncate(text: string, max: number): { text: string; truncated: boolean } {
  if (text.length <= max) return { text, truncated: false };
  const cut = text.slice(0, max);
  const lastNewline = cut.lastIndexOf("\n");
  const base = lastNewline > max * 0.6 ? cut.slice(0, lastNewline) : cut;
  return { text: base.trimEnd() + "……", truncated: true };
}

function dateLocale(language: string): string {
  if (language.startsWith("zh-Hant")) return "zh-Hant";
  if (language.startsWith("en")) return "en-US";
  return "zh-CN";
}

function formatDate(language: string): string {
  return new Intl.DateTimeFormat(dateLocale(language), {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date());
}

export default function ShareCard({ open, onClose, question, answer, sources }: ShareCardProps) {
  const { t, i18n } = useTranslation();
  const cardRef = useRef<HTMLDivElement>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [shareUrl, setShareUrl] = useState<string>(FALLBACK_SHARE_URL);
  const [creatingShare, setCreatingShare] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setCreatingShare(true);
    setShareUrl(FALLBACK_SHARE_URL);
    createSharedQA({ question, answer, sources })
      .then((res) => {
        if (!cancelled) setShareUrl(res.url);
      })
      .catch((e) => {
        console.error("create shared QA failed", e);
      })
      .finally(() => {
        if (!cancelled) setCreatingShare(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, question, answer, sources]);

  useEffect(() => {
    if (!open) return;
    QRCode.toDataURL(shareUrl, {
      width: 140,
      margin: 1,
      color: { dark: "#2b2318", light: "#f8f5ef" },
    })
      .then(setQrDataUrl)
      .catch(() => setQrDataUrl(""));
  }, [open, shareUrl]);

  const cleanAnswer = stripMarkdown(answer);
  const { text: answerText, truncated } = truncate(cleanAnswer, 420);

  const topSources: ChatSource[] = (sources ?? [])
    .filter((s) => s.title_zh)
    .slice(0, 3);

  const renderCardCanvas = async (): Promise<HTMLCanvasElement | null> => {
    if (!cardRef.current) return null;
    return html2canvas(cardRef.current, {
      backgroundColor: "#f8f5ef",
      scale: 2,
      useCORS: true,
      logging: false,
    });
  };

  const handleDownload = async () => {
    setGenerating(true);
    try {
      const canvas = await renderCardCanvas();
      if (!canvas) return;
      const dataUrl = canvas.toDataURL("image/png");
      const link = document.createElement("a");
      link.download = buildFilename(question, t("shareCard.filenameFallback"));
      link.href = dataUrl;
      link.click();
      message.success(t("shareCard.imageSaved"));
    } catch (e) {
      console.error("share card render failed", e);
      message.error(t("shareCard.imageFailed"));
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyImage = async () => {
    if (typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) {
      message.warning(t("shareCard.copyImageUnsupported"));
      return;
    }
    setGenerating(true);
    try {
      const canvas = await renderCardCanvas();
      if (!canvas) return;
      const blob: Blob | null = await new Promise((resolve) =>
        canvas.toBlob((b) => resolve(b), "image/png"),
      );
      if (!blob) {
        message.error(t("shareCard.imageFailed"));
        return;
      }
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      message.success(t("shareCard.imageCopied"));
    } catch (e) {
      console.error("copy image failed", e);
      message.error(t("shareCard.copyImageFailed"));
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(shareUrl).then(() => {
      message.success(t("shareCard.linkCopied"));
    });
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={Math.min(CARD_WIDTH + 60, 800)}
      centered
      destroyOnHidden
      title={t("shareCard.title")}
      styles={{ body: { background: "#e8e2d4", padding: 20 } }}
    >
      <div style={{ overflowX: "auto", display: "flex", justifyContent: "center" }}>
        <div
          ref={cardRef}
          style={{
            width: CARD_WIDTH,
            background: "#f8f5ef",
            padding: "40px 48px 32px",
            fontFamily: '"Noto Serif SC", "Source Han Serif", "Songti SC", STSong, serif',
            color: "#2b2318",
            boxSizing: "border-box",
            position: "relative",
            border: "1px solid #d9d0c1",
          }}
        >
          {/* Decorative top border */}
          <div
            style={{
              height: 4,
              background: "linear-gradient(90deg, #8b2500 0%, #b08d57 50%, #8b2500 100%)",
              marginBottom: 28,
            }}
          />

          {/* Header */}
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 28 }}>
            <div>
              <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: 4, color: "#8b2500" }}>
                {t("shareCard.brand")}
              </div>
              <div style={{ fontSize: 13, color: "#9a8e7a", marginTop: 4, letterSpacing: 1 }}>
                {t("shareCard.subtitle")}
              </div>
            </div>
            <div style={{ fontSize: 12, color: "#9a8e7a" }}>{formatDate(i18n.language)}</div>
          </div>

          {/* Question */}
          <div style={{ marginBottom: 24 }}>
            <div
              style={{
                display: "inline-block",
                fontSize: 12,
                color: "#fff",
                background: "#8b2500",
                padding: "3px 12px",
                marginBottom: 12,
                letterSpacing: 2,
              }}
            >
              {t("shareCard.questionLabel")}
            </div>
            <div
              style={{
                fontSize: 19,
                lineHeight: 1.7,
                color: "#2b2318",
                fontWeight: 600,
                borderLeft: "3px solid #8b2500",
                paddingLeft: 16,
              }}
            >
              {question}
            </div>
          </div>

          {/* Answer */}
          <div style={{ marginBottom: 24 }}>
            <div
              style={{
                display: "inline-block",
                fontSize: 12,
                color: "#fff",
                background: "#b08d57",
                padding: "3px 12px",
                marginBottom: 12,
                letterSpacing: 2,
              }}
            >
              {t("shareCard.answerLabel")}
            </div>
            <div
              style={{
                fontSize: 15,
                lineHeight: 1.9,
                color: "#5c4f3d",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {answerText}
            </div>
            {truncated && (
              <div style={{ fontSize: 12, color: "#9a8e7a", marginTop: 10, fontStyle: "italic" }}>
                {t("shareCard.fullAnswerHint")}
              </div>
            )}
          </div>

          {/* Citations */}
          {topSources.length > 0 && (
            <div
              style={{
                background: "#f0ebe2",
                border: "1px solid #d9d0c1",
                padding: "14px 18px",
                marginBottom: 20,
              }}
            >
              <div style={{ fontSize: 12, color: "#9a8e7a", marginBottom: 8, letterSpacing: 2 }}>
                {t("shareCard.sourcesTitle")}
              </div>
              {topSources.map((s, i) => (
                <div
                  key={i}
                  style={{
                    fontSize: 13,
                    color: "#5c4f3d",
                    lineHeight: 1.6,
                    marginBottom: i < topSources.length - 1 ? 4 : 0,
                  }}
                >
                  <span style={{ color: "#b08d57", marginRight: 6 }}>▸</span>
                  《{s.title_zh}》{s.juan_num > 0 ? t("shareCard.fascicle", { n: s.juan_num }) : ""}
                </div>
              ))}
            </div>
          )}

          {/* Footer */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderTop: "1px solid #d9d0c1",
              paddingTop: 18,
              marginTop: 8,
            }}
          >
            <div>
              <div style={{ fontSize: 14, color: "#2b2318", fontWeight: 600 }}>
                fojin.app
              </div>
              <div style={{ fontSize: 11, color: "#9a8e7a", marginTop: 3, lineHeight: 1.6 }}>
                {t("shareCard.platformLine1")}
                <br />
                {t("shareCard.platformLine2")}
              </div>
            </div>
            {qrDataUrl && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <img
                  src={qrDataUrl}
                  alt="fojin.app"
                  style={{ width: 70, height: 70, display: "block" }}
                />
                <div style={{ fontSize: 10, color: "#9a8e7a", marginTop: 4 }}>
                  {t("shareCard.scanToOpen")}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 20, flexWrap: "wrap" }}>
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          loading={generating}
          onClick={handleDownload}
          size="large"
          style={{ background: "#8b2500", borderColor: "#8b2500" }}
        >
          {t("shareCard.downloadImage")}
        </Button>
        <Button
          icon={<PictureOutlined />}
          onClick={handleCopyImage}
          size="large"
          loading={generating}
          style={{
            background: "#e1d3ee",
            borderColor: "#8e6fb8",
            color: "#4a2d6e",
          }}
        >
          {t("shareCard.copyImage")}
        </Button>
        <Button
          icon={<CopyOutlined />}
          onClick={handleCopyLink}
          size="large"
          loading={creatingShare}
          disabled={creatingShare}
          style={{
            background: "#d6d2c0",
            borderColor: "#6d6858",
            color: "#2d2920",
          }}
        >
          {creatingShare ? t("shareCard.creatingLink") : t("shareCard.copyLink")}
        </Button>
      </div>
      {generating && (
        <div style={{ textAlign: "center", marginTop: 10, color: "#9a8e7a", fontSize: 12 }}>
          <Spin size="small" /> {t("shareCard.generatingImage")}
        </div>
      )}
    </Modal>
  );
}
