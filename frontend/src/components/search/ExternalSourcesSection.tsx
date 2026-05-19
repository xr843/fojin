import { useState, useMemo } from "react";
import ExternalCard from "./ExternalCard";
import type { DataSource } from "../../api/client";

/** How many language-relevant sources to show before the "展开" toggle. */
const INITIAL_VISIBLE = 12;

/**
 * Map the query's script to the language codes a source should carry to
 * count as relevant. `data_sources.languages` is a comma-separated list of
 * codes (zh, lzh, sa, pi, bo, en, de, km, …).
 *
 * - Han script  → 中文 sources (zh / lzh)
 * - Tibetan     → bo
 * - Devanagari  → sa
 * - Latin/other → romanized Pali/Sanskrit + Western-language sources
 */
function preferredLangs(query: string): Set<string> {
  if (/[㐀-䶿一-鿿豈-﫿]/.test(query)) return new Set(["zh", "lzh"]);
  if (/[ༀ-࿿]/.test(query)) return new Set(["bo"]);
  if (/[ऀ-ॿ]/.test(query)) return new Set(["sa"]);
  return new Set(["pi", "sa", "en", "de"]);
}

function sourceLangs(s: DataSource): string[] {
  return (s.languages ?? "").split(",").map((x) => x.trim()).filter(Boolean);
}

/**
 * External-source launchers for the search page.
 *
 * These are not search results — the same fixed catalogue applies to every
 * query. To keep the section from burying the real results we:
 *  1. split sources by whether their language matches the query's script,
 *  2. show the language-relevant group first (capped, with a 展开 toggle),
 *  3. collapse the off-script group behind "其他语种来源".
 */
export default function ExternalSourcesSection({
  sources,
  query,
}: {
  sources: DataSource[];
  query: string;
}) {
  const [expandedPrimary, setExpandedPrimary] = useState(false);
  const [showOther, setShowOther] = useState(false);

  const { primary, other } = useMemo(() => {
    const pref = preferredLangs(query);
    const primary: DataSource[] = [];
    const other: DataSource[] = [];
    for (const s of sources) {
      const langs = sourceLangs(s);
      // Sources with no declared language stay in the primary group — we
      // demote known mismatches, not unknowns.
      const relevant = langs.length === 0 || langs.some((l) => pref.has(l));
      (relevant ? primary : other).push(s);
    }
    return { primary, other };
  }, [sources, query]);

  if (sources.length === 0) return null;

  const visiblePrimary = expandedPrimary ? primary : primary.slice(0, INITIAL_VISIBLE);

  return (
    <>
      <div className="s-ext-divider">
        可在以下 {sources.length} 个外部数据源继续搜索「{query}」
      </div>

      {visiblePrimary.map((s) => (
        <ExternalCard key={s.code} source={s} query={query} />
      ))}

      {primary.length > INITIAL_VISIBLE && (
        <button
          type="button"
          className="s-ext-toggle"
          onClick={() => setExpandedPrimary((v) => !v)}
        >
          {expandedPrimary ? "收起" : `展开剩余 ${primary.length - INITIAL_VISIBLE} 个来源`}
        </button>
      )}

      {other.length > 0 && (
        <>
          <button
            type="button"
            className="s-ext-toggle"
            onClick={() => setShowOther((v) => !v)}
          >
            {showOther ? "收起其他语种来源" : `其他语种来源（${other.length}）`}
          </button>
          {showOther &&
            other.map((s) => <ExternalCard key={s.code} source={s} query={query} />)}
        </>
      )}
    </>
  );
}
