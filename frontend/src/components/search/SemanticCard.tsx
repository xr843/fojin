import { useTranslation } from "react-i18next";
import { Tag } from "antd";
import { LinkOutlined, ReadOutlined } from "@ant-design/icons";
import { Link } from "react-router";
import { buildCbetaReadUrl, buildReaderUrl } from "../../utils/sourceUrls";
import type { SemanticSearchHit } from "../../api/client";

/** 语义搜索结果卡片：展示向量匹配的经文片段和相似度分数 */
export default function SemanticCard({ hit }: { hit: SemanticSearchHit }) {
  const { t } = useTranslation();
  const cbetaUrl = hit.cbeta_id ? buildCbetaReadUrl(hit.cbeta_id) : null;
  const scorePercent = Math.round(hit.similarity_score * 100);

  return (
    <div className="s-card">
      <div className="s-card-body">
        <div className="s-card-title">
          <Link to={`/texts/${hit.text_id}`} className="s-card-title-link">{hit.title_zh}</Link>
        </div>
        <div className="s-card-tags">
          {hit.cbeta_id && <Tag style={{ fontSize: 11 }}>{hit.cbeta_id}</Tag>}
          {hit.translator && (
            <Tag style={{ fontSize: 11 }}>
              {hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}
            </Tag>
          )}
          {hit.source_code && (
            <Tag style={{ fontSize: 11 }}>{hit.source_code}</Tag>
          )}
          <Tag color="purple" style={{ fontSize: 11 }}>
            {t("search.juan_n", { num: hit.juan_num })}
          </Tag>
          {/* 相似度只作一行小字：原先是 40px 红绿蓝圆环，一页 6~20 个，把视觉重心从经名上抢走；
              70%/50% 分档是任意切点，配「绿=好」的颜色等于暗示一个并不存在的判断。 */}
          <span className="s-card-score">
            {t("search.similarity_label")} <span className="s-card-score-num">{scorePercent}%</span>
          </span>
        </div>

        {/* 匹配文本片段。外框（底色/金边/内边距）和截断分两层：overflow:hidden 裁到的是
            padding 盒，line-clamp 只管内容盒——两者写在同一个元素上时，第 5 行会从下内边距
            里露出 8px 半截字（生产 390px 实测）。截断层不带纵向内边距，盒高正好等于 4 行。 */}
        <div className="s-semantic-snippet">
          <div className="s-semantic-snippet-text">{hit.snippet}</div>
        </div>

        <div className="s-card-links">
          {hit.has_content && (
            <Link className="s-card-action" to={buildReaderUrl(hit.text_id, hit.juan_num)}>
              <ReadOutlined aria-hidden="true" />
              {t("search.read")}
            </Link>
          )}
          {cbetaUrl && (
            <a className="s-card-action" href={cbetaUrl} target="_blank" rel="noopener noreferrer">
              <LinkOutlined aria-hidden="true" />
              CBETA
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
