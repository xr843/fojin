import { useTranslation } from "react-i18next";
import { Tag, Button, Progress } from "antd";
import { LinkOutlined, ReadOutlined } from "@ant-design/icons";
import { Link } from "react-router";
import { buildCbetaReadUrl, buildReaderUrl } from "../../utils/sourceUrls";
import type { SemanticSearchHit } from "../../api/client";

/** 语义搜索结果卡片：展示向量匹配的经文片段和相似度分数 */
export default function SemanticCard({ hit, rank }: { hit: SemanticSearchHit; rank: number }) {
  const { t } = useTranslation();
  const cbetaUrl = hit.cbeta_id ? buildCbetaReadUrl(hit.cbeta_id) : null;
  const scorePercent = Math.round(hit.similarity_score * 100);

  // 相似度颜色：>70% 绿色，>50% 蓝色，其余橙色。用语义 token 而非 antd 的填充色——
  // 后者是给色块调的，画成 40px 圆环压在浅色卡片上只有 2.27:1 / 2.2:1（图形元素需 3:1）。
  const scoreColor =
    scorePercent >= 70 ? "var(--fj-success)" : scorePercent >= 50 ? "var(--fj-info)" : "var(--fj-warning)";

  return (
    <div className="s-card">
      <div className="s-card-rank">#{rank}</div>
      <div className="s-card-body">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div className="s-card-title">{hit.title_zh}</div>
          <div style={{ minWidth: 90, textAlign: "right" }}>
            <Progress
              type="circle"
              percent={scorePercent}
              size={40}
              strokeColor={scoreColor}
              format={(p) => `${p}%`}
            />
          </div>
        </div>
        <div className="s-card-tags">
          {hit.cbeta_id && <Tag style={{ fontSize: 11 }}>{hit.cbeta_id}</Tag>}
          {hit.translator && (
            <Tag style={{ fontSize: 11 }}>
              {hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}
            </Tag>
          )}
          {hit.source_code && (
            <Tag color="geekblue" style={{ fontSize: 11 }}>{hit.source_code}</Tag>
          )}
          <Tag color="purple" style={{ fontSize: 11 }}>
            {t("search.juan_n", { num: hit.juan_num })}
          </Tag>
        </div>

        {/* 匹配文本片段。外框（底色/金边/内边距）和截断分两层：overflow:hidden 裁到的是
            padding 盒，line-clamp 只管内容盒——两者写在同一个元素上时，第 5 行会从下内边距
            里露出 8px 半截字（生产 390px 实测）。截断层不带纵向内边距，盒高正好等于 4 行。 */}
        <div className="s-semantic-snippet">
          <div className="s-semantic-snippet-text">{hit.snippet}</div>
        </div>

        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          {hit.has_content && (
            <Link to={buildReaderUrl(hit.text_id, hit.juan_num)}>
              <Button size="small" icon={<ReadOutlined />}>
                {t("search.read")}
              </Button>
            </Link>
          )}
          {cbetaUrl && (
            <Button
              size="small"
              icon={<LinkOutlined />}
              href={cbetaUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              CBETA
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
