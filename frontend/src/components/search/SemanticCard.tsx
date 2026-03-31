import { Tag, Button, Progress } from "antd";
import { LinkOutlined, ReadOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { buildCbetaReadUrl } from "../../utils/sourceUrls";
import type { SemanticSearchHit } from "../../api/client";

/** 语义搜索结果卡片：展示向量匹配的经文片段和相似度分数 */
export default function SemanticCard({ hit, rank }: { hit: SemanticSearchHit; rank: number }) {
  const cbetaUrl = hit.cbeta_id ? buildCbetaReadUrl(hit.cbeta_id) : null;
  const scorePercent = Math.round(hit.similarity_score * 100);

  // 相似度颜色：>70% 绿色，>50% 蓝色，其余橙色
  const scoreColor = scorePercent >= 70 ? "#52c41a" : scorePercent >= 50 ? "#1890ff" : "#fa8c16";

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
            第{hit.juan_num}卷
          </Tag>
        </div>

        {/* 匹配文本片段 */}
        <div
          style={{
            padding: "8px 12px",
            background: "var(--fj-sand-light, #faf7f2)",
            borderLeft: "3px solid #d4a574",
            borderRadius: 4,
            marginTop: 8,
            fontSize: 13,
            lineHeight: 1.8,
            color: "#5a4a3a",
            display: "-webkit-box",
            WebkitLineClamp: 4,
            WebkitBoxOrient: "vertical" as const,
            overflow: "hidden",
          }}
        >
          {hit.snippet}
        </div>

        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          {hit.has_content && (
            <Link to={`/read/${hit.text_id}/${hit.juan_num}`}>
              <Button size="small" icon={<ReadOutlined />}>
                阅读
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
