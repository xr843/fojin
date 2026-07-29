/**
 * CBETA hard-wrap reflow — shared by the reader page and the chat citation
 * drawer.
 *
 * Lived inside TextReaderPage until 2026-07-29, when a user reported the
 * citation drawer showing 「又經中言有三清 淨」 — stray spaces mid-word, because
 * the drawer dropped raw chunk_text into the DOM and HTML collapsed CBETA's
 * every-~18-chars hard newlines into spaces. The reader had always reflowed;
 * the drawer never did. One copy, one behaviour.
 */
/** Segment type for rendering. For text-bearing segments, `offsets[k]` is the
 * raw-content char offset of `text[k]` — used to place inline critical-apparatus
 * (校勘异文) markers at the right characters even though reflow re-segments the body. */
export type TextSegment =
  | { type: "prose"; text: string; offsets: number[] }
  | { type: "verse"; text: string; offsets: number[] }
  | { type: "break" }
  | { type: "head"; text: string; offsets: number[] }
  | { type: "juan"; text: string; offsets: number[] }
  | { type: "byline"; text: string; offsets: number[] }
  | { type: "section"; text: string; offsets: number[] };

/**
 * Reflow raw text into segments matching CBETA Online layout.
 *
 * CBETA source data has hard line breaks every ~18 chars. We need to:
 * 1. Merge consecutive prose lines into flowing paragraphs
 * 2. Keep verse/gatha (偈颂) lines as separate indented lines
 * 3. Break paragraphs at blank lines and markers like 論曰/頌曰
 *
 * Verse detection: a line is a verse if it ends with ，or 。and the
 * text before the final punctuation contains no other ，。(i.e. it's
 * a single clause per line, typical of Buddhist verse structure).
 * Prose lines have multiple clauses (multiple ，。) within one line.
 */
export function reflowText(raw: string): TextSegment[] {
  const lines = raw.split("\n");
  // Raw-content offset where each line starts (chars + the dropped "\n").
  const lineStart: number[] = [];
  for (let i = 0, off = 0; i < lines.length; i++) {
    lineStart[i] = off;
    off += lines[i].length + 1;
  }
  // Trim a line and return the raw offset of each surviving char. Stored CBETA
  // content is already per-line stripped, so leading whitespace is usually 0,
  // but we account for it so offsets stay exact.
  const trimmedOf = (i: number): { text: string; offsets: number[] } => {
    const lead = lines[i].length - lines[i].trimStart().length;
    const text = lines[i].trim();
    const offsets: number[] = new Array(text.length);
    for (let k = 0; k < text.length; k++) offsets[k] = lineStart[i] + lead + k;
    return { text, offsets };
  };

  const segments: TextSegment[] = [];
  let proseBuf = "";
  let proseOffsets: number[] = [];

  const flushProse = () => {
    if (proseBuf) {
      segments.push({ type: "prose", text: proseBuf, offsets: proseOffsets });
      proseBuf = "";
      proseOffsets = [];
    }
  };

  // Verse detection: Buddhist verse lines are typically 5-char or 7-char
  // clauses joined by ，。 at the end, with at most one ，in the middle
  // connecting two equal-length half-lines.
  // e.g. "諸一切種諸冥滅，拔眾生出生死泥，" (7+7 = ~16 chars with punct)
  // vs prose: "聖眾，故先讚德方申敬禮。諸言所表謂佛" (multiple clauses, ~18 chars)
  const isVerse = (line: string): boolean => {
    if (line.length < 4 || line.length > 22) return false;
    // Must end with Chinese punctuation
    if (!/[，。；]$/.test(line)) return false;
    // Count ALL Chinese punctuation in the line
    const allPuncts = (line.match(/[，。、；：！？]/g) || []).length;
    // Strict verse: at most 2 punctuation total (e.g. "五言，五言，" or "七言，")
    // Prose lines typically have 3+ punctuation marks
    if (allPuncts > 2) return false;
    // Lines with whitespace gaps are CBETA verse formatting
    if (/\s{2,}/.test(line)) return true;
    // For lines with exactly 1-2 punctuation, check symmetry
    // Verse halves should be roughly equal length (e.g. 5+5, 7+7)
    if (allPuncts === 2) {
      const parts = line.split(/[，。、；]/);
      if (parts.length >= 2 && parts[0].length > 0 && parts[1].length > 0) {
        const ratio = Math.min(parts[0].length, parts[1].length) / Math.max(parts[0].length, parts[1].length);
        return ratio >= 0.5; // halves within 2:1 ratio
      }
    }
    // Single punctuation at end: likely a verse half-line
    return allPuncts === 1 && line.length <= 12;
  };

  // Structural detection helpers
  const isHead = (line: string, idx: number): boolean => {
    // First non-empty line, short (经名标题), e.g. "長阿含經序"
    if (idx > 2) return false;
    if (line.length > 15 || line.length < 2) return false;
    // Must contain 經/論/律/品/序/疏 etc.
    return /[經论論律品序疏記集傳]/.test(line) && !/[，。；：！？、]/.test(line);
  };

  const isJuan = (line: string): boolean => {
    // 卷标题: e.g. "佛說長阿含經卷第一", "大般若波羅蜜多經卷第二"
    return /卷第?[一二三四五六七八九十百千\d]+/.test(line) && line.length <= 25 && !/[，。]/.test(line);
  };

  const isByline = (line: string): boolean => {
    // 译者署名: e.g. "後秦弘始年佛陀耶舍共竺佛念譯", "長安釋僧肇述"
    return /[譯译述撰注疏記造]$/.test(line) && line.length <= 25 && !/[，。；]/.test(line);
  };

  const isSection = (line: string): boolean => {
    // 品名/章节: e.g. "（一）第一分初大本經第一", "大緣方便經第二"
    // Starts with （number） or contains 品第/分第/經第
    if (/^[（(][一二三四五六七八九十\d]+[）)]/.test(line)) return true;
    if (/[品分經]第[一二三四五六七八九十百\d]+/.test(line) && line.length <= 20 && !/[，。]/.test(line)) return true;
    return false;
  };

  let inVerseBlock = false;
  // Before the first 論曰, verse-like lines are opening verses
  let beforeFirstProse = true;
  let firstNonEmptyIdx = -1;
  let lastNonEmptyLine = "";

  for (let i = 0; i < lines.length; i++) {
    const { text: trimmed, offsets: tOffsets } = trimmedOf(i);

    // Blank line → paragraph break, but ONLY if the previous non-empty line
    // ends with sentence-final punctuation. CBETA XML <p> boundaries sometimes
    // fall mid-word (e.g. 淨\n\n色), so we must not break there.
    if (trimmed === "") {
      if (/[。！？」』]$/.test(lastNonEmptyLine)) {
        flushProse();
        segments.push({ type: "break" });
      }
      continue;
    }

    // Track non-empty lines
    lastNonEmptyLine = trimmed;
    if (firstNonEmptyIdx < 0) firstNonEmptyIdx = i;
    const relIdx = i - firstNonEmptyIdx;

    // Structural elements: head, juan, byline, section
    if (isJuan(trimmed)) {
      flushProse();
      segments.push({ type: "juan", text: trimmed, offsets: tOffsets });
      continue;
    }

    if (isByline(trimmed)) {
      flushProse();
      segments.push({ type: "byline", text: trimmed, offsets: tOffsets });
      continue;
    }

    if (isSection(trimmed)) {
      flushProse();
      segments.push({ type: "section", text: trimmed, offsets: tOffsets });
      continue;
    }

    if (isHead(trimmed, relIdx)) {
      flushProse();
      segments.push({ type: "head", text: trimmed, offsets: tOffsets });
      continue;
    }

    // Check paragraph markers
    const hasVerseMarker = /頌曰[：:]?|偈曰[：:]?/.test(trimmed);
    const isProseMarker = /^(論曰|述曰|疏曰|解曰|釋曰)/.test(trimmed);

    if (isProseMarker) {
      beforeFirstProse = false;
      inVerseBlock = false;
      if (proseBuf) flushProse();
      proseBuf = trimmed;
      proseOffsets = tOffsets.slice();
      continue;
    }

    // "頌曰" anywhere in line triggers verse mode
    if (hasVerseMarker) {
      beforeFirstProse = false;
      proseBuf += trimmed;
      proseOffsets.push(...tOffsets);
      flushProse();
      inVerseBlock = true;
      continue;
    }

    // Verse mode (after 頌曰 or at opening before first 論曰)
    if ((inVerseBlock || beforeFirstProse) && isVerse(trimmed)) {
      flushProse();
      segments.push({ type: "verse", text: trimmed, offsets: tOffsets });
      continue;
    }

    // If we were in verse block but line doesn't look like verse, exit
    if (inVerseBlock && !isVerse(trimmed)) {
      inVerseBlock = false;
    }
    if (beforeFirstProse && !isVerse(trimmed)) {
      beforeFirstProse = false;
    }

    // Default: merge into prose paragraph
    proseBuf += trimmed;
    proseOffsets.push(...tOffsets);
  }
  flushProse();
  return segments;
}
