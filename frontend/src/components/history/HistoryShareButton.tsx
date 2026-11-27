import { useState } from "react";
import { Button, Modal, message } from "antd";
import { ShareAltOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { renderShareCard } from "../../utils/shareCard";

/**
 * 佛教史长卷的分享：一张图（复用今日一段的 canvas 竖图，浏览器里画、不走服务器）+ 链接。
 * 微信里网页链接常不显示标题和图，图片最稳；链接另有服务端注入的分享卡片（app/api/seo_history.py）。
 */
export default function HistoryShareButton({
  heading,
  text,
  source,
  url,
  fileName,
  onShare,
}: {
  heading: string;
  text: string;
  source: string;
  /** 分享的深链（含 ?p= / ?e=） */
  url: string;
  fileName: string;
  onShare?: (step: string) => void;
}) {
  const { t } = useTranslation();
  const [card, setCard] = useState<{ url: string; file: File } | null>(null);
  const [making, setMaking] = useState(false);

  const make = async () => {
    setMaking(true);
    onShare?.("make");
    try {
      const blob = await renderShareCard({ text, source, heading, footer: t("history.card_footer") });
      const file = new File([blob], fileName, { type: "image/png" });
      // data: 地址：站点 CSP 的 img-src 不放行 blob:（见 DailyPage）
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result));
        r.onerror = () => reject(r.error);
        r.readAsDataURL(blob);
      });
      setCard({ url: dataUrl, file });
    } catch {
      message.error(t("history.share_failed"));
    } finally {
      setMaking(false);
    }
  };

  const canSystemShare = !!card && typeof navigator.canShare === "function" && navigator.canShare({ files: [card.file] });

  return (
    <>
      <Button size="small" icon={<ShareAltOutlined />} loading={making} onClick={make}>
        {t("history.share")}
      </Button>
      <Modal open={!!card} onCancel={() => setCard(null)} footer={null} title={t("history.share")} width={420} centered>
        {card && (
          <div className="history-share">
            <img src={card.url} alt={`${heading} ${text}`} />
            <p className="history-share-hint">{t("history.share_hint")}</p>
            <div className="history-share-actions">
              <Button
                onClick={() => {
                  onShare?.("download");
                  const a = document.createElement("a");
                  a.href = card.url;
                  a.download = card.file.name;
                  a.click();
                }}
              >
                {t("history.share_save")}
              </Button>
              <Button
                onClick={async () => {
                  onShare?.("copy");
                  try {
                    await navigator.clipboard.writeText(url);
                    message.success(t("history.share_copied"));
                  } catch {
                    message.error(t("history.share_failed"));
                  }
                }}
              >
                {t("history.share_copy")}
              </Button>
              {canSystemShare && (
                <Button
                  type="primary"
                  onClick={async () => {
                    onShare?.("system");
                    try {
                      await navigator.share({ files: [card.file], text: `${heading} ${url}` });
                    } catch {
                      /* 用户取消不算错 */
                    }
                  }}
                >
                  {t("history.share_system")}
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
