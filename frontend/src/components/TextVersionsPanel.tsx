import { useQuery } from "@tanstack/react-query";
import { Spin, Tag, Tooltip } from "antd";
import {
  PictureOutlined,
  BookOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { getTextVersions } from "../api/client";

const LANG_COLORS: Record<string, string> = {
  lzh: "#d4a574",
  pi: "#8b9e6b",
  sa: "#b07d62",
  bo: "#7a8fb5",
  en: "#6b8e9e",
  ja: "#c4956a",
  ko: "#9b7cb5",
};

const LANG_LABELS: Record<string, string> = {
  lzh: "中文",
  pi: "巴利",
  sa: "梵文",
  bo: "藏文",
  en: "英文",
  ja: "日文",
  ko: "韩文",
};

interface Props {
  textId: number;
}

export default function TextVersionsPanel({ textId }: Props) {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["textVersions", textId],
    queryFn: () => getTextVersions(textId),
  });

  if (isLoading) return <Spin size="small" />;
  if (!data) return null;

  const { translations, iiif_manifests } = data;
  const hasContent = translations.length > 0 || iiif_manifests.length > 0;

  if (!hasContent) return null;

  return (
    <div className="versions-panel">
      {/* Translations / Parallel Texts */}
      {translations.length > 0 && (
        <div className="versions-section">
          <div className="versions-section-title">
            <BookOutlined /> 不同译本 ({translations.length})
          </div>
          <div className="versions-list">
            {translations.map((t) => (
              <div
                key={t.text_id}
                className="version-item version-item--clickable"
                onClick={() => navigate(`/texts/${t.text_id}/read`)}
              >
                <div className="version-item-main">
                  <span className="version-title">{t.title_zh || t.title_en}</span>
                  {t.lang && (
                    <Tag
                      color={LANG_COLORS[t.lang] || "#999"}
                      style={{ fontSize: 11, lineHeight: "18px", marginLeft: 6 }}
                    >
                      {LANG_LABELS[t.lang] || t.lang}
                    </Tag>
                  )}
                </div>
                <div className="version-item-meta">
                  {t.translator && <span>{t.translator}</span>}
                  {t.dynasty && <span className="version-dynasty">{t.dynasty}</span>}
                  {t.source_name && (
                    <span className="version-source">{t.source_name}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* IIIF Manuscripts */}
      {iiif_manifests.length > 0 && (
        <div className="versions-section">
          <div className="versions-section-title">
            <PictureOutlined /> 写本 / 刻本图像 ({iiif_manifests.length})
          </div>
          <div className="versions-iiif-grid">
            {iiif_manifests.map((m) => (
              <Tooltip key={m.id} title={m.label}>
                <a
                  href={m.manifest_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="version-iiif-card"
                >
                  {m.thumbnail_url ? (
                    <img
                      src={m.thumbnail_url}
                      alt={m.label || ""}
                      className="version-iiif-thumb"
                    />
                  ) : (
                    <div className="version-iiif-placeholder">
                      <PictureOutlined style={{ fontSize: 24, color: "#ccc" }} />
                    </div>
                  )}
                  <div className="version-iiif-label">
                    {m.provider || "IIIF"}
                  </div>
                </a>
              </Tooltip>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
