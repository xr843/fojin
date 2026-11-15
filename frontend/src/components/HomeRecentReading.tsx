import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { CloseOutlined } from "@ant-design/icons";
import { formatReadAgo, removeReading, type ReadingEntry } from "../utils/readingHistory";

export const HOME_RECENT_MAX = 5;

/**
 * 首页「最近阅读」栏：借鉴 CBETA Online 首页的「最近操作」。
 * 记录只存在本浏览器（localStorage），所以未登录也能用；每条可单独移除。
 * 列表在挂载时由父组件读一次传进来，移除后只改本地 state，不再回读存储。
 */
export default function HomeRecentReading({
  initial,
  onChange,
}: {
  initial: ReadingEntry[];
  onChange?: (entries: ReadingEntry[]) => void;
}) {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const [entries, setEntries] = useState(() => initial.slice(0, HOME_RECENT_MAX));
  // 渲染期间不能调 Date.now()（React Compiler 要求纯函数），挂载时取一次即可
  const [now] = useState(() => Date.now());

  if (entries.length === 0) return null;

  const remove = (textId: number) => {
    const rest = removeReading(textId);
    setEntries(rest.slice(0, HOME_RECENT_MAX));
    onChange?.(rest);
  };

  return (
    <section className="home-recent" aria-label={t("home.recent_reading")}>
      <span className="home-hot-label home-recent-label">{t("home.recent_reading")}</span>
      <ul className="home-recent-list">
        {entries.map((e) => (
          <li key={e.textId} className="home-recent-item">
            <button
              type="button"
              className="home-recent-open"
              data-umami-event="home_recent_read"
              onClick={() => navigate(`/texts/${e.textId}/read?juan=${e.juan}`)}
              title={e.title}
            >
              <span className="home-recent-title">《{e.title}》</span>
              <span className="home-recent-meta">
                {t("home.juan_n", { n: e.juan })} · {formatReadAgo(e.ts, now, i18n.language, t("home.read_just_now"))}
              </span>
            </button>
            <button
              type="button"
              className="home-recent-del"
              aria-label={t("home.recent_remove", { title: e.title })}
              title={t("home.recent_remove", { title: e.title })}
              onClick={() => remove(e.textId)}
            >
              <CloseOutlined />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
