import { useTranslation } from "react-i18next";
import { Tag } from "antd";
import { LinkOutlined, EyeOutlined } from "@ant-design/icons";
import { buildSearchUrl } from "../../utils/sourceUrls";
import { localizedSourceName } from "../../utils/sourceName";
import type { DataSource } from "../../api/client";

/**
 * Compact single-row launcher for an external data source.
 *
 * Not a search result — it carries the current query into the source's
 * own search page. Deliberately low-chrome: source name + region + two
 * actions. The fake "排序 #N" rank, duplicate name tag, blanket "外链跳转"
 * tag and the "馆藏: {name}" line were dropped — they added no information.
 */
export default function ExternalCard({ source, query }: { source: DataSource; query: string }) {
  const { t } = useTranslation();
  const url = buildSearchUrl(source.code, query) || "#";
  return (
    <div className="s-ext-row">
      <span className="s-ext-row-name">{localizedSourceName(source)}</span>
      {source.region && <Tag style={{ fontSize: 11, margin: 0 }}>{t(`region.${source.region}`, source.region)}</Tag>}
      <span className="s-ext-row-spacer" />
      <a
        className="s-card-btn-primary"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={t("search.search_at_source_aria", { name: localizedSourceName(source), query })}
      >
        <LinkOutlined /> {t("search.search_at_source")}
      </a>
      {source.base_url && (
        <a
          className="s-card-btn"
          href={source.base_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={t("search.visit_homepage_aria", { name: localizedSourceName(source) })}
        >
          <EyeOutlined /> {t("search.visit_homepage")}
        </a>
      )}
    </div>
  );
}
