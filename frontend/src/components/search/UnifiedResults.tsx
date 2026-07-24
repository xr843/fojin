import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Empty } from "antd";
import type { UnifiedSearchResponse } from "../../api/client";
import ResultCard from "./ResultCard";
import ContentCard from "./ContentCard";
import SemanticCard from "./SemanticCard";

interface Props {
  data: UnifiedSearchResponse;
}

/**
 * Unified search results — sectioned overview combining dictionary entries,
 * catalog hits, and content/semantic snippets in a single view.
 *
 * Sections render in importance order; empty sections are hidden.
 * Used by SearchPage's "全部 / All" tab (default landing tab).
 */
export default function UnifiedResults({ data }: Props) {
  const { t } = useTranslation();
  const sections = data.sections;

  const dictionary = sections.dictionary ?? [];
  const catalogResults = sections.catalog?.results ?? [];
  const contentResults = sections.content?.results ?? [];
  const semanticResults = sections.semantic?.results ?? [];

  // Cross-display content + semantic, dedup by text_id
  const seenTextIds = new Set<number | string>();
  const mergedSnippets: Array<
    | { kind: "content"; hit: (typeof contentResults)[number]; key: string }
    | { kind: "semantic"; hit: (typeof semanticResults)[number]; key: string }
  > = [];
  for (const hit of contentResults.slice(0, 3)) {
    if (seenTextIds.has(hit.text_id)) continue;
    seenTextIds.add(hit.text_id);
    mergedSnippets.push({ kind: "content", hit, key: `c-${hit.text_id}` });
  }
  for (const hit of semanticResults.slice(0, 3)) {
    if (seenTextIds.has(hit.text_id)) continue;
    seenTextIds.add(hit.text_id);
    mergedSnippets.push({ kind: "semantic", hit, key: `s-${hit.text_id}-${hit.juan_num}` });
  }

  const hasAny =
    dictionary.length > 0 ||
    catalogResults.length > 0 ||
    mergedSnippets.length > 0;

  if (!hasAny) {
    return (
      <div style={{ marginTop: 32 }}>
        <Empty description={t("search.no_results_for_query", { query: data.query })} />
      </div>
    );
  }

  const sectionTitleStyle: React.CSSProperties = {
    margin: "24px 0 12px",
    fontSize: 15,
    fontWeight: 600,
    color: "#5b4a32",
    borderBottom: "1px solid #e8e0d4",
    paddingBottom: 6,
  };

  return (
    <div className="s-unified">
      {/* 辞典释义 — overview shows only the first 2 entries; the full set
          (often a dozen dictionaries for a common term) lives on the
          dedicated dictionary page so it doesn't push the text results down. */}
      {dictionary.length > 0 && (
        <section className="s-unified-section">
          <h3 style={sectionTitleStyle}>{"🔤"} {t("search.section_dictionary")}</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {dictionary.slice(0, 2).map((entry) => (
              <Link
                key={entry.id}
                to={`/dict/${encodeURIComponent(entry.headword)}`}
                style={{
                  display: "block",
                  padding: "10px 14px",
                  background: "var(--fj-sand-light, #faf7f2)",
                  border: "1px solid #e8e0d4",
                  borderRadius: 6,
                  color: "inherit",
                  textDecoration: "none",
                }}
              >
                <div style={{ fontSize: 15, fontWeight: 600, color: "#3d2f1a" }}>
                  {entry.headword}
                  {entry.reading && (
                    <span style={{ fontSize: 13, color: "var(--fj-ink-muted)", fontWeight: 400, marginLeft: 8 }}>
                      [{entry.reading}]
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 13, color: "#5b4a32", marginTop: 4, lineHeight: 1.6 }}>
                  {entry.definition.length > 140
                    ? entry.definition.slice(0, 140) + "…"
                    : entry.definition}
                </div>
                {entry.source && (
                  <div style={{ fontSize: 12, color: "var(--fj-ink-muted)", marginTop: 4 }}>
                    {t("search.dict_source_label", { source: entry.source })}
                  </div>
                )}
              </Link>
            ))}
          </div>
          {dictionary.length > 2 && (
            <Link
              to={`/dictionary?q=${encodeURIComponent(data.query)}`}
              style={{ display: "inline-block", marginTop: 8, fontSize: 13, color: "var(--fj-accent)" }}
            >
              {t("search.view_all_dict_count", { n: dictionary.length })}
            </Link>
          )}
        </section>
      )}

      {/* 经文标题 */}
      {catalogResults.length > 0 && (
        <section className="s-unified-section">
          <h3 style={sectionTitleStyle}>{"📖"} {t("search.section_titles")}</h3>
          {catalogResults.slice(0, 5).map((hit, i) => (
            <ResultCard key={hit.id} hit={hit} rank={i + 1} />
          ))}
        </section>
      )}

      {/* 经文内文片段 */}
      {mergedSnippets.length > 0 && (
        <section className="s-unified-section">
          <h3 style={sectionTitleStyle}>{"🔍"} {t("search.section_content")}</h3>
          {mergedSnippets.map((item, i) =>
            item.kind === "content" ? (
              <ContentCard key={item.key} hit={item.hit} rank={i + 1} />
            ) : (
              <SemanticCard key={item.key} hit={item.hit} rank={i + 1} />
            )
          )}
        </section>
      )}
    </div>
  );
}
