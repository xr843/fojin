import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Button, Modal, Spin, message } from "antd";
import { getVernacular } from "../api/client";
import { pickDaily, quotePassage } from "../utils/dailyPassage";
import { lunarLabel } from "../utils/lunar";
import { renderShareCard } from "../utils/shareCard";
import { localizeHan } from "../utils/hanScript";
import "../styles/daily.css";

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

function track(name: string, data?: Record<string, string | number>) {
  if (typeof umami !== "undefined") umami.track(name, data);
}

/**
 * 每日一段：一段逐字核过出处的经文（北京时间每天换），可直达原文那一行、看 AI 白话、
 * 带着原文去问小津、生成竖版分享图。修学讲「日课」，这是给读者每天回来的一个理由，
 * 也是佛津唯一能被转发出去的东西——分享图上印着出处与 fojin.app。
 */
export default function DailyPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const navigate = useNavigate();
  const [{ passage, dateKey }] = useState(() => pickDaily(new Date()));
  const [showVernacular, setShowVernacular] = useState(false);
  const [card, setCard] = useState<{ url: string; file: File } | null>(null);
  const [making, setMaking] = useState(false);

  // 农历只给中文界面；超出月表返回 null 就只显示公历
  const lunar = lang.startsWith("zh") ? lunarLabel(dateKey) : null;
  const dateLabel = lunar ? `${dateKey} · ${localizeHan(t("daily.lunar", { d: lunar }), lang)}` : dateKey;
  const title = localizeHan(passage.title_zh, lang);
  const sourceLine = `《${title}》${t("daily.juan", { n: passage.juan_num })}`;
  const text = quotePassage(localizeHan(passage.text, lang), lang);

  const vernacular = useQuery({
    queryKey: ["daily-vernacular", passage.text_id, passage.text],
    queryFn: () => getVernacular({ text_id: passage.text_id, sentence: passage.text, before: "", after: "" }),
    enabled: showVernacular,
    staleTime: Infinity,
    retry: false,
  });

  const askHref = useMemo(() => {
    const p = new URLSearchParams({ q: t("daily.ask_question"), context: passage.text, source: passage.title_zh });
    return `/chat?${p.toString()}`;
  }, [passage, t]);


  const makeCard = async () => {
    setMaking(true);
    track("daily_share", { step: "make" });
    try {
      const blob = await renderShareCard({
        text,
        source: sourceLine,
        heading: t("daily.card_heading", { date: dateLabel }),
        footer: t("daily.card_footer"),
      });
      const file = new File([blob], `fojin-${dateKey}.png`, { type: "image/png" });
      // 必须是 data: 地址：站点 CSP 的 img-src 只放行 'self' data: https:，blob: 会被拦成坏图
      // （2026-11-24 生产实测；本地 vite 没有 CSP，测不出来）。
      setCard({ url: await blobToDataUrl(blob), file });
    } catch {
      message.error(t("daily.card_failed"));
    } finally {
      setMaking(false);
    }
  };

  const canSystemShare = !!card && typeof navigator.canShare === "function" && navigator.canShare({ files: [card.file] });

  return (
    <div className="daily-page">
      <Helmet>
        <title>{`${t("daily.page_title")} - ${t("app.title")}`}</title>
        <meta name="description" content={`${text} —— ${sourceLine}`} />
      </Helmet>

      <div className="daily-date">{t("daily.heading", { date: dateLabel })}</div>
      <blockquote className="daily-text" lang="zh">
        {text}
      </blockquote>
      <div className="daily-source">
        —— <Link to={passage.reader_path} data-umami-event="daily_open_source">{sourceLine}</Link>
        <span className="daily-verified">{t("daily.verified")}</span>
      </div>

      <div className="daily-actions">
        <Button onClick={() => { setShowVernacular(true); track("daily_vernacular"); }} disabled={showVernacular}>
          {t("daily.vernacular")}
        </Button>
        <Button onClick={() => { track("daily_ask"); navigate(askHref); }}>{t("daily.ask")}</Button>
        <Button type="primary" loading={making} onClick={makeCard}>
          {t("daily.share")}
        </Button>
      </div>

      {showVernacular && (
        <div className="daily-vernacular" aria-live="polite">
          <div className="daily-vernacular-tag">{t("daily.vernacular_tag")}</div>
          {vernacular.isLoading ? (
            <Spin size="small" />
          ) : vernacular.error ? (
            <span className="daily-muted">{t("daily.vernacular_failed")}</span>
          ) : (
            <p>{vernacular.data?.translation}</p>
          )}
        </div>
      )}

      <p className="daily-muted daily-note">{t("daily.note")}</p>

      <Modal
        open={!!card}
        onCancel={() => setCard(null)}
        footer={null}
        title={t("daily.share")}
        width={420}
        destroyOnHidden
      >
        {card && (
          <div className="daily-card-preview">
            <img src={card.url} alt={`${text} —— ${sourceLine}`} />
            <p className="daily-muted">{t("daily.save_hint")}</p>
            <div className="daily-card-actions">
              <Button
                onClick={() => {
                  track("daily_share", { step: "download" });
                  const a = document.createElement("a");
                  a.href = card.url;
                  a.download = card.file.name;
                  a.click();
                }}
              >
                {t("daily.download")}
              </Button>
              {canSystemShare && (
                <Button
                  type="primary"
                  onClick={async () => {
                    track("daily_share", { step: "system" });
                    try {
                      await navigator.share({ files: [card.file], text: `${text} —— ${sourceLine} https://fojin.app/daily` });
                    } catch {
                      /* 用户取消分享不算错 */
                    }
                  }}
                >
                  {t("daily.system_share")}
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
