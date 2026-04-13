import { useEffect, useRef, useState } from "react";
import { Modal, Button, message, Spin } from "antd";
import { DownloadOutlined, CopyOutlined } from "@ant-design/icons";
import html2canvas from "html2canvas-pro";
import QRCode from "qrcode";
import type { ChatSource } from "../api/client";

interface ShareCardProps {
  open: boolean;
  onClose: () => void;
  question: string;
  answer: string;
  sources: ChatSource[] | null;
}

const CARD_WIDTH = 720;
const SHARE_URL = "https://fojin.app/chat";

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

function formatDate(): string {
  const d = new Date();
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

export default function ShareCard({ open, onClose, question, answer, sources }: ShareCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (!open) return;
    QRCode.toDataURL(SHARE_URL, {
      width: 140,
      margin: 1,
      color: { dark: "#2b2318", light: "#f8f5ef" },
    })
      .then(setQrDataUrl)
      .catch(() => setQrDataUrl(""));
  }, [open]);

  const cleanAnswer = stripMarkdown(answer);
  const { text: answerText, truncated } = truncate(cleanAnswer, 420);

  const topSources: ChatSource[] = (sources ?? [])
    .filter((s) => s.title_zh)
    .slice(0, 3);

  const handleDownload = async () => {
    if (!cardRef.current) return;
    setGenerating(true);
    try {
      const canvas = await html2canvas(cardRef.current, {
        backgroundColor: "#f8f5ef",
        scale: 2,
        useCORS: true,
        logging: false,
      });
      const dataUrl = canvas.toDataURL("image/png");
      const link = document.createElement("a");
      link.download = `fojin-qa-${Date.now()}.png`;
      link.href = dataUrl;
      link.click();
      message.success("图片已保存");
    } catch (e) {
      console.error("share card render failed", e);
      message.error("生成图片失败，请重试");
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyLink = () => {
    navigator.clipboard.writeText(SHARE_URL).then(() => {
      message.success("链接已复制");
    });
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={Math.min(CARD_WIDTH + 60, 800)}
      centered
      destroyOnClose
      title="分享这段佛典问答"
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
                佛津 · FoJin
              </div>
              <div style={{ fontSize: 13, color: "#9a8e7a", marginTop: 4, letterSpacing: 1 }}>
                AI 佛典问答 · 引据原典
              </div>
            </div>
            <div style={{ fontSize: 12, color: "#9a8e7a" }}>{formatDate()}</div>
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
              问
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
              答
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
                — 完整回答请访问 fojin.app/chat
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
                引据原典
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
                  《{s.title_zh}》{s.juan_num > 0 ? `第${s.juan_num}卷` : ""}
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
                全球佛典数字资源平台
                <br />
                汇聚 CBETA · SuttaCentral 等 600+ 数据源
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
                  扫码体验
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 20 }}>
        <Button
          type="primary"
          icon={<DownloadOutlined />}
          loading={generating}
          onClick={handleDownload}
          size="large"
          style={{ background: "#8b2500", borderColor: "#8b2500" }}
        >
          下载图片
        </Button>
        <Button icon={<CopyOutlined />} onClick={handleCopyLink} size="large">
          复制链接
        </Button>
      </div>
      {generating && (
        <div style={{ textAlign: "center", marginTop: 10, color: "#9a8e7a", fontSize: 12 }}>
          <Spin size="small" /> 正在生成图片…
        </div>
      )}
    </Modal>
  );
}
