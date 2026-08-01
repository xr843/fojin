import type { ChatSource } from "../api/client";
import {
  toSimplified,
  extractPrecedingQuote,
  pickSourceForQuote,
} from "./citationMatch";
import { localizeHan } from "./hanScript";

/**
 * Custom URL scheme for citation links. Lives here rather than in ChatPage so
 * that both the link builder and the page's rehype-sanitize allowlist /
 * urlTransform can read it without ChatPage having to export a non-component
 * (which trips react-refresh/only-export-components — a CI error, the frontend
 * lint gate runs `--max-warnings 0`).
 */
export const CITATION_URL_SCHEME = "fojin-citation";

/**
 * Turn sutra references inside an AI answer into citation-drawer buttons.
 *
 * The LLM is wildly inconsistent about citation style — sometimes it emits the
 * explicit 【《心经》第1卷】 marker, sometimes it just drops 《佛说无量寿经》
 * inline as prose. We handle both:
 *
 *  1. First pass rewrites 【《title》第N卷】 into a markdown link pointing at
 *     our custom `fojin-citation://{text_id}/{juan_num}/{chunk_index}` URL.
 *  2. Second pass scans the remaining plaintext for bare 《title》 occurrences
 *     and wraps them when `title` is in the RAG source map. Existing markdown
 *     links from pass 1 are skipped so we never double-wrap.
 *
 * When a matched source lacks chunk_index (legacy chat history from before
 * the chunk_index field was wired through) we emit chunk_index=-1; the click
 * handler in the renderer falls back to reader-page navigation in that case.
 *
 * `language` decides the script of the **visible** sutra name only. CBETA's
 * title_zh is always traditional, so a simplified reader would otherwise read
 * 「色不异空」 and see 【《般若波羅蜜多心經》…】 in the same sentence. Everything
 * else is left byte-for-byte alone — above all the quoted passage, which has
 * been verbatim-checked against the canon; re-scripting it would make the
 * 「已逐字核验」 badge a lie. Defaults to simplified, matching
 * scriptForLanguage's own fallback for any non-Hant locale.
 */
export function injectCitationLinks(
  content: string,
  sources: ChatSource[] | null,
  language: string = "zh",
): string {
  if (!sources || sources.length === 0) return content;

  // Two indexes over the RAG sources, both keyed on the simplified title so
  // traditional CBETA titles match simplified answer text:
  //   titleMap     — the single highest-scored chunk per title (fallback)
  //   titleSources — every retrieved chunk per title, for quote-aware pick
  const titleMap = new Map<string, ChatSource>();
  const titleSources = new Map<string, ChatSource[]>();
  for (const s of sources) {
    if (!s.title_zh || s.text_id <= 0) continue;
    const key = toSimplified(s.title_zh);
    const existing = titleMap.get(key);
    if (!existing || s.score > existing.score) titleMap.set(key, s);
    const list = titleSources.get(key);
    if (list) list.push(s);
    else titleSources.set(key, [s]);
  }
  if (titleMap.size === 0) return content;

  // Resolve a citation to its URL and the fascicle (juan) it points at.
  // When a quote is known and a retrieved chunk actually contains it, anchor
  // the citation to THAT chunk — otherwise the drawer opens whichever chunk
  // merely scored highest, which usually does not hold the quoted sentence.
  // The quote rides along in the URL so the drawer can highlight it.
  const buildCitation = (
    fallback: ChatSource,
    simplifiedTitle: string,
    juanHint: number | null,
    quote: string | null,
  ): { url: string; juan: number } => {
    const candidates = titleSources.get(simplifiedTitle) ?? [];
    const picked = pickSourceForQuote(candidates, quote);
    const source = picked ?? fallback;
    const juan = picked ? picked.juan_num : (juanHint ?? source.juan_num);
    // chunk_index 只在它确实属于 `juan` 那一卷时才成立。
    //
    // 没有 quote 命中时，卷号来自 LLM 写的「第 N 卷」（juanHint），段号却来自
    // 检索结果——而检索命中的很可能是**另一卷**。把两者拼成一对，就会生成
    // 「第 2 卷第 25 段」这种组合，可第 2 卷只有 0–22 段。生产日志实测：近 7 天
    // 119 个去重的引文上下文请求里 33 个落空（27.7%），且同一个段号 25 横跨
    // 卷 2/4/5/6/7/9/10/11 反复出现——正是同一个检索段号被安到了不同的卷上。
    //
    // 与其把读者送去一个不存在的位置（抽屉打开却空白），不如承认这条引文没有
    // 段级锚点：发 -1，点击处会退回该卷的阅读器页面，那是真实存在的东西。
    const chunkIdx =
      source.juan_num === juan ? (source.chunk_index ?? -1) : -1;
    const tail = quote ? `/${encodeURIComponent(quote)}` : "";
    const url = `${CITATION_URL_SCHEME}://${source.text_id}/${juan}/${chunkIdx}/${encodeURIComponent(simplifiedTitle)}${tail}`;
    return { url, juan };
  };

  // Pass 1 — explicit 【《title》…】 markers. The replace callback receives the
  // marker's offset in the original string; the text just before it carries
  // the passage the LLM is attributing.
  let withExplicit = content.replace(
    /【《([^》]+)》([^】]*)】/g,
    (_match, rawTitle: string, tail: string, offset: number, full: string) => {
      const title = rawTitle.trim();
      const simplifiedTitle = toSimplified(title);
      const source = titleMap.get(simplifiedTitle);
      if (!source) return _match;
      const juanMatch = tail.match(/第(\d+)卷/);
      const juanHint = juanMatch ? parseInt(juanMatch[1], 10) : null;
      const quote = extractPrecedingQuote(full.slice(0, offset));
      const { url, juan } = buildCitation(source, simplifiedTitle, juanHint, quote);
      // Rewrite the fascicle slot in the visible label to the resolved juan
      // so the label matches the link target — this also turns a literal
      // 第N卷 placeholder the LLM left unsubstituted into a real number.
      // Non-卷 qualifiers (卷上, 第十八愿) carry no 第…卷 slot and are kept.
      const label = tail.replace(/第[^】卷]*卷/, `第${juan}卷`); // i18n-exempt — rewrites the LLM's Chinese citation marker, must match answer text
      return `[【《${localizeHan(title, language)}》${label}】](${url})`;
    },
  );

  // Pass 2 — bare 《title》 in prose. Split on any markdown links already in
  // the content (the ones pass 1 just produced, plus any pre-existing links)
  // so we only process plaintext segments. No quote is bound to a bare
  // mention, so the chunk stays the top-scored one.
  const parts = withExplicit.split(/(\[[^\]]*\]\([^)]*\))/g);
  withExplicit = parts
    .map((part, i) => {
      if (i % 2 === 1) return part; // preserved markdown link
      return part.replace(/《([^》]+)》/g, (bareMatch, rawTitle: string) => {
        const title = rawTitle.trim();
        const simplifiedTitle = toSimplified(title);
        const source = titleMap.get(simplifiedTitle);
        if (!source) return bareMatch;
        const { url } = buildCitation(source, simplifiedTitle, null, null);
        return `[《${localizeHan(title, language)}》](${url})`;
      });
    })
    .join("");

  return withExplicit;
}
