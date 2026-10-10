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
      {/* 两个按钮包成一组：窄屏时整组另起一行左对齐，不再随站名长短时而同行时而拆行 */}
      <span className="s-ext-row-actions">
        {/* 与结果卡的「阅读 / CBETA」同一套次级文字链接（.s-card-action）：外部源是「去别处继续找」
            的出口，不是本页的主操作——原先每行一颗实心朱砂主按钮，12 行就是全页最抢眼的 12 处。
            触屏上 .s-card-action 撑到 40px 高作触控目标。 */}
        <a
          className="s-card-action"
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={t("search.search_at_source_aria", { name: localizedSourceName(source), query })}
        >
          <LinkOutlined aria-hidden="true" />
          {t("search.search_at_source")}
        </a>
        {source.base_url && (
          <a
            className="s-card-action"
            href={source.base_url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={t("search.visit_homepage_aria", { name: localizedSourceName(source) })}
          >
            <EyeOutlined aria-hidden="true" />
            {t("search.visit_homepage")}
          </a>
        )}
      </span>
    </div>
  );
}
