import { useTranslation } from "react-i18next";
import { Tag, Button } from "antd";
import { ReadOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { buildReaderUrl } from "../../utils/sourceUrls";
import type { ParallelSentenceHit } from "../../api/client";

// Mirror CrossLangCard's language tag palette so lang badges stay consistent
// across the search surface. lzh/zh both render as Classical Chinese.
const LANG_KEYS: Record<string, string> = {
  lzh: "lang.lzh",
  zh: "lang.lzh",
  pi: "lang.pi",
  en: "lang.en",
  bo: "lang.bo",
  sa: "lang.sa",
};

const LANG_COLORS: Record<string, string> = {
  lzh: "red",
  zh: "red",
  pi: "orange",
  en: "blue",
  bo: "purple",
  sa: "green",
};

/**
 * 跨语对照结果卡片：并排展示对齐的汉文句与梵/藏语句，标注语种、出处与来源。
 * MITRA 平行语料的外语侧为内联原文，无独立引文页，故仅汉文侧提供阅读跳转。
 */
export default function ParallelSentenceCard({
  hit,
  rank,
}: {
  hit: ParallelSentenceHit;
  rank: number;
}) {
  const { t } = useTranslation();
  const langLabel = (lang: string) => (LANG_KEYS[lang] ? t(LANG_KEYS[lang]) : lang);
  const foreignColor = LANG_COLORS[hit.foreign_lang] || "default";
  const canRead = hit.text_id > 0 && hit.juan_num != null;

  const sentenceBox = (accent: string): React.CSSProperties => ({
    flex: 1,
    minWidth: 0,
    padding: "8px 12px",
    background: "var(--fj-sand-light, #faf7f2)",
    borderLeft: `3px solid ${accent}`,
    borderRadius: 4,
    fontSize: 14,
    lineHeight: 1.9,
    color: "#5a4a3a",
    wordBreak: "break-word",
  });

  return (
    <div className="s-card">
      <div className="s-card-rank">#{rank}</div>
      <div className="s-card-body">
        {/* 并排对照：汉文 ↔ 外语 */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <div style={sentenceBox("#c0392b")}>
            <Tag color={LANG_COLORS.lzh} style={{ fontSize: 10, marginBottom: 4 }}>
              {langLabel("lzh")}
            </Tag>
            <div>{hit.zh_text}</div>
          </div>
          <div style={sentenceBox("#7cb342")}>
            <Tag color={foreignColor} style={{ fontSize: 10, marginBottom: 4 }}>
              {langLabel(hit.foreign_lang)}
            </Tag>
            <div style={{ fontStyle: "italic" }}>{hit.foreign_text}</div>
          </div>
        </div>

        {/* 出处 + 质量分 */}
        <div className="s-card-tags" style={{ marginTop: 8 }}>
          {hit.taisho_id && (
            <Tag style={{ fontSize: 11 }}>{hit.taisho_id}</Tag>
          )}
          {hit.title && (
            <Tag color="volcano" style={{ fontSize: 11 }}>
              {hit.title}
            </Tag>
          )}
          {hit.juan_num != null && (
            <Tag color="purple" style={{ fontSize: 11 }}>
              {t("search.juan_n", { num: hit.juan_num })}
            </Tag>
          )}
          {hit.mitra_e_score != null && (
            <Tag style={{ fontSize: 11 }}>
              {t("search.parallel_score", { score: hit.mitra_e_score.toFixed(2) })}
            </Tag>
          )}
        </div>

        <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
          {canRead && (
            <Link to={buildReaderUrl(hit.text_id, hit.juan_num)}>
              <Button size="small" icon={<ReadOutlined />}>
                {t("search.read")}
              </Button>
            </Link>
          )}
          {/* 来源与授权：低调标注，保持 CC BY-SA 4.0 可追溯 */}
          <span style={{ fontSize: 11, color: "#9a8e7a" }}>
            {t("search.parallel_provenance")}
          </span>
        </div>
      </div>
    </div>
  );
}
