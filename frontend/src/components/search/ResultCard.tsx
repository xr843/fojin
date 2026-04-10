import { useNavigate } from "react-router-dom";
import { Tag, Button } from "antd";
import { EyeOutlined, LinkOutlined, TranslationOutlined } from "@ant-design/icons";
import BookmarkButton from "../BookmarkButton";
import { sanitizeHighlight } from "../../utils/sanitize";
import { getSourceLabel, buildCbetaReadUrl } from "../../utils/sourceUrls";
import type { SearchHit } from "../../api/client";

const LANG_LABELS: Record<string, string> = {
  lzh: "汉文",
  zh: "汉文",
  pi: "巴利文",
  en: "English",
  bo: "藏文",
  sa: "梵文",
};

const LANG_COLORS: Record<string, string> = {
  lzh: "red",
  zh: "red",
  pi: "orange",
  en: "blue",
  bo: "purple",
  sa: "green",
};

export default function ResultCard({ hit, rank }: { hit: SearchHit; rank: number }) {
  const navigate = useNavigate();
  const titleHtml = hit.highlight?.title_zh?.[0] ?? hit.title_zh;
  const sourceName = hit.source_code ? getSourceLabel(hit.source_code) : null;
  const cbetaUrl = buildCbetaReadUrl(hit.cbeta_id);
  const relatedTranslations = hit.related_translations || [];

  return (
    <div className="s-card">
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title" dangerouslySetInnerHTML={{ __html: sanitizeHighlight(titleHtml) }} />
        <div className="s-card-tags">
          {sourceName && (
            <Tag color="volcano" style={{ fontSize: 11 }}>{sourceName}</Tag>
          )}
          <Tag style={{ fontSize: 11 }}>{hit.has_content ? "本地全文" : "目录数据"}</Tag>
          {hit.category && <Tag style={{ fontSize: 11 }}>{hit.category}</Tag>}
          {hit.lang && hit.lang !== "lzh" && (
            <Tag color="blue" style={{ fontSize: 11 }}>
              {{ pi: "巴利文", en: "英文", bo: "藏文", sa: "梵文" }[hit.lang] || hit.lang}
            </Tag>
          )}
        </div>
        <div className="s-card-meta">
          {hit.translator && (
            <span>主要责任者: {hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}</span>
          )}
        </div>
        <div className="s-card-meta">
          <span>编号: {hit.cbeta_id}</span>
        </div>
        {hit.highlight && Object.entries(hit.highlight).filter(([k]) => k !== "title_zh").map(([field, fragments]) => (
          <div key={field} className="s-card-preview" dangerouslySetInnerHTML={{
            __html: sanitizeHighlight(fragments[0]),
          }} />
        ))}
        {relatedTranslations.length > 0 && (
          <div className="s-card-translations">
            <TranslationOutlined style={{ fontSize: 12, color: "#9a8e7a", marginRight: 4 }} />
            <span style={{ fontSize: 12, color: "#9a8e7a", marginRight: 6 }}>其他语言版本:</span>
            {relatedTranslations.map((rt) => (
              <Tag
                key={rt.id}
                color={LANG_COLORS[rt.lang] || "default"}
                style={{ fontSize: 11, cursor: "pointer", marginBottom: 2 }}
                onClick={() => navigate(`/texts/${rt.id}`)}
              >
                {LANG_LABELS[rt.lang] || rt.lang}
                {rt.title ? ` - ${rt.title.length > 20 ? rt.title.slice(0, 20) + "..." : rt.title}` : ""}
              </Tag>
            ))}
          </div>
        )}
        <div className="s-card-actions">
          {cbetaUrl && (
            <Button type="primary" size="small" icon={<LinkOutlined />}
              style={{ background: "#8b2500", borderColor: "#8b2500" }}
              href={cbetaUrl} target="_blank" rel="noopener noreferrer">
              CBETA 阅读
            </Button>
          )}
          <Button type="primary" size="small" icon={<EyeOutlined />}
            onClick={() => navigate(`/texts/${hit.id}`)}>
            查看详情
          </Button>
          <BookmarkButton textId={hit.id} size="small" />
        </div>
      </div>
    </div>
  );
}
