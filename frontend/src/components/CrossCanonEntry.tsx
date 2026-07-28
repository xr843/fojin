import { useMemo } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Tag } from "antd";
import { TranslationOutlined, RightOutlined } from "@ant-design/icons";
import { getAlignmentCatalog } from "../api/client";

const LANG_LABELS: Record<string, { labelKey: string; color: string }> = {
  pi: { labelKey: "lang.pi", color: "green" },
  bo: { labelKey: "lang.bo", color: "purple" },
  sa: { labelKey: "lang.sa", color: "orange" },
};

/** 段级跨藏对照入口卡：本经若有 mitra/fojin 平行段，在文本详情页给醒目入口直达阅读器对照。
    无覆盖（catalog 未加载 / 本经不在其中）时整块隐身，可与 backend 解耦部署。
    与 OtherVersions（作品级"其他版本"）互补：这是段级跨语对照。 */
export default function CrossCanonEntry({ textId }: { textId: number }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data } = useQuery({
    queryKey: ["alignmentCatalog"],
    queryFn: getAlignmentCatalog,
    staleTime: 3600_000,
    retry: 1,
  });
  const coverage = useMemo(() => {
    if (!data) return null;
    const rows = data.entries.filter((e) => e.text_id === textId);
    if (rows.length === 0) return null;
    const langs = rows
      .map((r) => ({ lang: r.other_lang, count: r.pair_count }))
      .sort((a, b) => b.count - a.count);
    // land on the first aligned juan (sample_juan = min juan with parallels) of
    // the highest-count language — the natural start of the comparison, not mid-text.
    const sampleJuan = rows.reduce((best, r) => (r.pair_count > best.pair_count ? r : best)).sample_juan;
    return { langs, sampleJuan };
  }, [data, textId]);

  if (!coverage) return null;
  return (
    <button
      className="source-btn"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        width: "100%",
        padding: "12px 16px",
        marginTop: 16,
      }}
      onClick={() => navigate(`/texts/${textId}/read?juan=${coverage.sampleJuan}`)}
    >
      <span style={{ display: "inline-flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <TranslationOutlined style={{ color: "var(--fj-accent)", fontSize: 16 }} />
        <span style={{ fontWeight: 600 }}>{t("crosscanon.entry_title")}</span>
        {coverage.langs.map((l) => {
          const lang = LANG_LABELS[l.lang];
          return (
            <Tag key={l.lang} color={lang?.color ?? "default"} style={{ margin: 0 }}>
              {lang ? t(lang.labelKey) : l.lang} {l.count}
            </Tag>
          );
        })}
        <span style={{ fontSize: 12, color: "var(--fj-ink-muted)" }}>{t("crosscanon.entry_hint")}</span>
      </span>
      <RightOutlined style={{ color: "var(--fj-ink-muted)" }} />
    </button>
  );
}
