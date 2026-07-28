import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Tag, Input, Empty, Spin } from "antd";
import { TranslationOutlined, SearchOutlined } from "@ant-design/icons";
import { getAlignmentCatalog } from "../api/client";
import { localizeHan } from "../utils/hanScript";
import { taishoSection, SECTION_ORDER } from "../data/taishoSections";

const LANG_LABELS: Record<string, { labelKey: string; color: string }> = {
  pi: { labelKey: "lang.pi", color: "green" },
  bo: { labelKey: "lang.bo", color: "purple" },
  sa: { labelKey: "lang.sa", color: "orange" },
};

type Work = {
  text_id: number;
  title: string;
  section: string;
  sample_juan: number;
  total: number;
  langs: { lang: string; count: number }[];
  hasBo: boolean;
  hasSa: boolean;
};

/** B 方案：专属跨藏对照浏览页。/collections 卡片「查看全部」的目的地。
    完整 ~1000 部跨语对齐经典，按 Taishō 部类分组 + 语种/部类筛选 + 搜索。
    纯前端：复用 cached catalog，部类从 cbeta_id（T-number）推导。 */
export default function CrossCanonPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [langFilter, setLangFilter] = useState<"all" | "both" | "bo" | "sa">("all");
  const [section, setSection] = useState<string>("");
  const [q, setQ] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ["alignmentCatalog"],
    queryFn: getAlignmentCatalog,
    staleTime: 3600_000,
    retry: 1,
  });

  const works = useMemo<Work[]>(() => {
    if (!data) return [];
    const m = new Map<number, Work>();
    for (const e of data.entries) {
      let w = m.get(e.text_id);
      if (!w) {
        w = {
          text_id: e.text_id,
          // CBETA's title_zh is always traditional; render it in the reader's
          // script. Also makes the search box below match what's on screen.
          title: localizeHan(e.title_zh || e.cbeta_id, i18n.language),
          section: taishoSection(e.cbeta_id),
          sample_juan: e.sample_juan,
          total: 0,
          langs: [],
          hasBo: false,
          hasSa: false,
        };
        m.set(e.text_id, w);
      }
      w.langs.push({ lang: e.other_lang, count: e.pair_count });
      w.total += e.pair_count;
      if (e.other_lang === "bo") w.hasBo = true;
      if (e.other_lang === "sa") w.hasSa = true;
    }
    const arr = [...m.values()];
    arr.forEach((w) => w.langs.sort((a, b) => b.count - a.count));
    return arr.sort((a, b) => b.total - a.total);
  }, [data, i18n.language]);

  const sectionCounts = useMemo(() => {
    const c = new Map<string, number>();
    for (const w of works) c.set(w.section, (c.get(w.section) || 0) + 1);
    return c;
  }, [works]);

  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return works.filter((w) => {
      if (langFilter === "both" && !(w.hasBo && w.hasSa)) return false;
      if (langFilter === "bo" && !w.hasBo) return false;
      if (langFilter === "sa" && !w.hasSa) return false;
      if (section && w.section !== section) return false;
      if (ql && !w.title.toLowerCase().includes(ql)) return false;
      return true;
    });
  }, [works, langFilter, section, q]);

  const grouped = useMemo(() => {
    const g = new Map<string, Work[]>();
    for (const w of filtered) {
      if (!g.has(w.section)) g.set(w.section, []);
      g.get(w.section)!.push(w);
    }
    return SECTION_ORDER.filter((s) => g.has(s)).map((s) => ({ section: s, works: g.get(s)! }));
  }, [filtered]);

  const sectionsPresent = SECTION_ORDER.filter((s) => sectionCounts.has(s));

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px" }}>
      <h1 style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 24 }}>
        <TranslationOutlined style={{ color: "var(--fj-accent)" }} />
        {t("crosscanon.entry_title")}
      </h1>
      <p style={{ color: "var(--fj-ink-muted)", marginBottom: 16 }}>
        {t("crosscanon.page_desc", { texts: works.length, pairs: (data?.total_pairs ?? 0).toLocaleString() })}
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        {(["all", "both", "bo", "sa"] as const).map((lf) => (
          <Tag.CheckableTag key={lf} checked={langFilter === lf} onChange={() => setLangFilter(lf)}>
            {lf === "all"
              ? t("crosscanon.lang_all")
              : lf === "both"
                ? t("crosscanon.lang_both")
                : t(LANG_LABELS[lf].labelKey)}
          </Tag.CheckableTag>
        ))}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        <Tag.CheckableTag checked={section === ""} onChange={() => setSection("")}>
          {t("crosscanon.section_all")} ({works.length})
        </Tag.CheckableTag>
        {sectionsPresent.map((s) => (
          <Tag.CheckableTag key={s} checked={section === s} onChange={() => setSection(section === s ? "" : s)}>
            {s} ({sectionCounts.get(s)})
          </Tag.CheckableTag>
        ))}
      </div>

      <Input
        prefix={<SearchOutlined />}
        placeholder={t("crosscanon.search_ph")}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        allowClear
        style={{ maxWidth: 360, marginBottom: 20 }}
      />

      {isLoading ? (
        <Spin />
      ) : grouped.length === 0 ? (
        <Empty description={t("crosscanon.empty")} />
      ) : (
        grouped.map(({ section: s, works: ws }, idx) => {
          // accordion: collapsed by default (the page is a clean index of 部);
          // first group opens by default so it's not an empty wall of headers.
          // A specific 部 filter shows that one section already expanded.
          const open =
            section !== "" || expanded.has(s) || (section === "" && expanded.size === 0 && idx === 0);
          return (
            <div key={s} style={{ borderBottom: "1px solid #ece5d8" }}>
              <div
                onClick={() => {
                  if (section !== "") return;
                  setExpanded((prev) => {
                    const n = new Set(prev);
                    if (n.has(s)) n.delete(s);
                    else n.add(s);
                    return n;
                  });
                }}
                style={{
                  cursor: section !== "" ? "default" : "pointer",
                  fontWeight: 600,
                  fontSize: 15,
                  padding: "10px 4px",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  userSelect: "none",
                }}
              >
                {section === "" && (
                  <span style={{ fontSize: 11, color: "var(--fj-ink-muted)", width: 12, display: "inline-block" }}>
                    {open ? "▾" : "▸"}
                  </span>
                )}
                <span>{s}</span>
                <span style={{ fontWeight: 400, fontSize: 12, color: "var(--fj-ink-muted)" }}>· {ws.length}</span>
              </div>
              {open && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "0 4px 14px" }}>
                  {ws.map((w) => (
                    <button
                      key={w.text_id}
                      className="source-btn"
                      style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                      onClick={() => navigate(`/texts/${w.text_id}/read?juan=${w.sample_juan}`)}
                    >
                      <span>{w.title}</span>
                      {w.langs.map((l) => {
                        const lang = LANG_LABELS[l.lang];
                        return (
                          <span key={l.lang} style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                            <Tag color={lang?.color ?? "default"} style={{ margin: 0, fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
                              {lang ? t(lang.labelKey) : l.lang}
                            </Tag>
                            <span style={{ fontSize: 11, color: "var(--fj-ink-muted)" }}>{t("collections.pair_count", { n: l.count })}</span>
                          </span>
                        );
                      })}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
