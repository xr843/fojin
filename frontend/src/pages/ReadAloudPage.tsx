import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Empty, Spin, Tag, Alert } from "antd";
import { SoundOutlined } from "@ant-design/icons";

import { getAvailableAudio, type AudioCatalogItem } from "../api/client";
import { formatDuration } from "../audio/format";
import { localizeHan } from "../utils/hanScript";
import "../styles/sources.css";

/**
 * 读诵索引页。
 *
 * 这个功能此前**只有一个入口** —— 阅读页工具栏那个按钮，且只在该卷恰好
 * 有音频时才出现。也就是说：你得先打开心經的阅读页，才可能发现它存在。
 * 没有这一页，再加十部经触达仍然接近零。
 *
 * 刻意**不做自动播放**：从这里跳过去会中断用户手势链，iOS 会静默拦下
 * `play()`，用户只会以为坏了。落到阅读页、按那个高亮的按钮，一次点击而已。
 */
export default function ReadAloudPage() {
  const { t, i18n } = useTranslation();
  const { data, isLoading } = useQuery({
    queryKey: ["audioCatalog"],
    queryFn: getAvailableAudio,
    staleTime: 5 * 60 * 1000,
  });

  const items: AudioCatalogItem[] = data?.items ?? [];

  return (
    <div className="sources-page">
      <Helmet>
        <title>{t("readaloud.seo_title")}</title>
        <meta name="description" content={t("readaloud.seo_desc")} />
      </Helmet>

      <header className="sources-header">
        <h1>
          <SoundOutlined /> {t("readaloud.title")}
        </h1>
        <p>{t("readaloud.subtitle")}</p>
      </header>

      {/* 诚信标注放在页首，而不是只藏在播放条里 —— 用户在点进去之前就该知道。 */}
      <Alert type="info" showIcon message={t("readaloud.synthetic_notice")} style={{ marginBottom: 20 }} />

      {isLoading && <Spin />}

      {!isLoading && items.length === 0 && (
        <Empty description={t("readaloud.empty")} />
      )}

      <ul className="readaloud-list">
        {items.map((it) => (
          <li key={it.text_id} className="readaloud-item">
            <div className="readaloud-item-main">
              <Link to={`/texts/${it.text_id}/read?juan=${it.juans[0]?.juan_num ?? 1}`}>
                {localizeHan(it.title_zh, i18n.language)}
              </Link>
              <span className="readaloud-meta">
                {[it.dynasty, it.translator]
                  .filter(Boolean)
                  .map((s) => localizeHan(String(s), i18n.language))
                  .join(" ")}
                {it.taisho_id ? ` · ${it.taisho_id}` : ""}
              </span>
            </div>
            <div className="readaloud-item-side">
              <Tag>{t("readaloud.juan_count", { n: it.juan_count })}</Tag>
              <Tag color="blue">{formatDuration(it.total_duration_ms)}</Tag>
            </div>
            {it.juan_count > 1 && (
              <div className="readaloud-juans">
                {it.juans.map((j) => (
                  <Link key={j.juan_num} to={`/texts/${it.text_id}/read?juan=${j.juan_num}`}>
                    {t("readaloud.juan", { n: j.juan_num })}
                    <span className="readaloud-juan-dur"> {formatDuration(j.duration_ms)}</span>
                  </Link>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
