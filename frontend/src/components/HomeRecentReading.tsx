import { useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { CloseOutlined } from "@ant-design/icons";
import { removeReading, type ReadingEntry } from "../utils/readingHistory";

export const HOME_RECENT_MAX = 3;

/**
 * 首页「接着读」：一行文字链接，最多 3 部（《经名》第 N 卷），借鉴 CBETA Online 首页的「最近操作」。
 * 2026-11-25 由五张卡片改成一行：卡片是搜索框下最占地方的一块，而 30 天里只有约 1.5% 的首页访客点它。
 * 记录只存在本浏览器（localStorage），未登录也能用；每条有个小 ×（共用电脑时清掉），桌面悬停才显示。
 * 列表在挂载时由父组件读一次传进来，移除后只改本地 state，不再回读存储。
 */
export default function HomeRecentReading({
  initial,
  onChange,
}: {
  initial: ReadingEntry[];
  onChange?: (entries: ReadingEntry[]) => void;
}) {
  const { t } = useTranslation();
  const [entries, setEntries] = useState(() => initial.slice(0, HOME_RECENT_MAX));

  if (entries.length === 0) return null;

  const remove = (textId: number) => {
    const rest = removeReading(textId);
    setEntries(rest.slice(0, HOME_RECENT_MAX));
    onChange?.(rest);
  };

  return (
    <section className="home-recent" aria-label={t("home.recent_reading")}>
      <span className="home-recent-label">{t("home.continue_reading")}</span>
      <ul className="home-recent-list">
        {entries.map((e) => (
          <li key={e.textId} className="home-recent-item">
            <Link
              to={`/texts/${e.textId}/read?juan=${e.juan}`}
              className="home-recent-open"
              data-umami-event="home_recent_read"
              title={`《${e.title}》${t("home.juan_n", { n: e.juan })}`}
            >
              <span className="home-recent-title">《{e.title}》</span>
              <span className="home-recent-meta">{t("home.juan_n", { n: e.juan })}</span>
            </Link>
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
