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

  // CBETA 把长署名硬折成两三行：「姚秦罽賓三藏佛陀耶舍 / 共竺佛念等譯」「後秦北印度三藏 /
  // 弗若多羅共羅什譯」「西天譯經三藏朝奉大夫試光祿卿 / 傳法大師賜紫沙門臣施護等 / 奉詔譯」。
  // isByline 只认得以「譯」等结尾的末行，前半截会落进正文段（缩进、墨色、左对齐），与右侧的
  // 后半截拆成两处（2026-10-10 生产，四分律卷二十一；抽样前 80 部里五分律、僧祇律、十誦律、
  // 遺教經、大日經、大智度論、八十楞伽同病）。规则刻意收窄：起首行含「三藏」、整段无标点、
  // 至多三行且相邻（中间无空行）、末行本身是署名，且只在段落边界上触发 —— 正文行几乎都带标点。
  // 返回并入的末行下标，不成立返回 -1。
  const splitBylineEnd = (i: number): number => {
    const first = lines[i].trim();
    if (!first.includes("三藏") || first.length > 25 || /[，。；：！？、]/.test(first)) return -1; // i18n-exempt: CBETA 署名里的字面匹配，不是界面文案
    for (let j = i + 1; j <= i + 2 && j < lines.length; j++) {
      const t = lines[j].trim();
      if (!t || t.length > 25 || /[，。；：！？、]/.test(t)) return -1;
      if (isByline(t)) return j;
    }
    return -1;
  };

  const isSection = (line: string): boolean => {
    // 品名/章节: e.g. "（一）第一分初大本經第一", "大緣方便經第二"
    // Starts with （number） or contains 品第/分第/經第
    if (/^[（(][一二三四五六七八九十\d]+[）)]/.test(line)) return true;
    if (/[品分經]第[一二三四五六七八九十百\d]+/.test(line) && line.length <= 20 && !/[，。]/.test(line)) return true;
    return false;
  };

  // ── 经题折行 / 品题识别（2026-10-10，#1300 生产抽样遗留的三类）────────────────────
  // 宁可漏判不可误判：每条规则都要「标题形状」+「结构锚点」两头成立才触发。回放 459 卷生产原文
  // （含 203 卷未参与调规则的留出样本）与 10.4 万个模拟引文抽屉窗口，误伤为 0；回放脚本与逐条命中
  // 见 PR 描述。合并一律逐字携带 offsets，与 splitBylineEnd 同一手法。
  const ORD = "一二三四五六七八九十百千〇廿卅"; // i18n-exempt: CBETA 结构字面匹配
  const reOrdEnd = new RegExp(`[${ORD}第]$`); // i18n-exempt: CBETA 结构字面匹配
  // 标题行：无句读、无括注、无空白（全角空格分隔的多半是署名或目录）
  const isTitleLike = (t: string): boolean =>
    t.length >= 2 && t.length <= 25 && !/[，。；：！？、「」『』【】〔〕（）()]/.test(t) && !/\s/.test(t);
  // 署名里才有的字眼 —— 出现即不当标题/品题
  const hasBylineWord = (t: string): boolean => /譯|沙門|三藏|比丘|法師|居士|弟子|撰|述|著|造|編|錄/.test(t); // i18n-exempt: CBETA 署名字面匹配
  // 目录页：「俱舍論頌疏記目次 / 卷第一 / 釋序文 …」里的「卷第一」是目录条目，不是经题后半截
  const isTocTitle = (t: string): boolean => /目次|目錄|條箇/.test(t); // i18n-exempt: CBETA 目录页字面匹配
  const nextIsBlank = (j: number): boolean => j >= lines.length || lines[j].trim() === "";
  // 结构锚点：经题之后（至多隔一个空行）紧跟署名起首行。没有这个锚点，引文抽屉里从卷中段切出的
  // chunk 也会把目录、碑铭里的无标点行当经题并起来（模拟窗口实测过）。「開府儀同三司…」「西天北印度…」
  // 是不空、施护一系多行署名的起首，本身不带「譯」。
  const bylineFollows = (j: number): boolean => {
    let k = j;
    if (k < lines.length && lines[k].trim() === "") k++;
    if (k >= lines.length) return false;
    const t = lines[k].trim();
    // 署名行不会带「N卷」——经录（貞元錄、開元錄）里「…三藏續古今翻譯經圖紀二卷」那种书目行不算锚点
    if (!t || t.includes("卷")) return false; // i18n-exempt: CBETA 结构字面匹配
    return isByline(t) || hasBylineWord(t) || /^(開府|西天)/.test(t); // i18n-exempt: CBETA 署名字面匹配
  };

  // 经题后半截：「…釋論 / 第一」「…經卷 / 第一」「…經卷第 / 五」「…經 / 卷上」「…修行法 / 一卷」
  // 「…見一切佛 / 世界義第五十一之餘」。只认卷首第一行 + 紧邻下一行，且其后是署名。
  const reTailOrd = new RegExp(`^第[${ORD}]+(?:之[${ORD}]+|之餘)?$`); // i18n-exempt: CBETA 结构字面匹配
  const reTailJuan = new RegExp(`^(?:卷第?[${ORD}]+|卷[上中下]|[${ORD}]+卷)$`); // i18n-exempt: CBETA 结构字面匹配
  const reTailBare = new RegExp(`^[${ORD}]{1,4}$`);
  const reTailPrefixed = new RegExp(`^[^${ORD}第卷]{1,4}第[${ORD}]+(?:之[${ORD}]+|之餘)?$`); // i18n-exempt: CBETA 结构字面匹配
  const titleTailEnd = (i: number): boolean => {
    if (i + 1 >= lines.length || !bylineFollows(i + 2)) return false;
    const a = lines[i].trim();
    const b = lines[i + 1].trim();
    if (!isTitleLike(a) || !(reTailBare.test(b) || isTitleLike(b))) return false;
    if (isJuan(a) || isByline(a) || isSection(a) || hasBylineWord(a) || isTocTitle(a)) return false;
    if (isByline(b) || isSection(b)) return false;
    if (reTailBare.test(b)) return /第$/.test(a); // i18n-exempt: 卷第 / 五
    if (/第$/.test(a)) return false; // i18n-exempt: CBETA 结构字面匹配
    if (reTailOrd.test(b)) return !reOrdEnd.test(a);
    // 「…經 / 卷上」「…論頌 / 一卷」：首行须是被折断的长行（≥10 字）
    if (reTailJuan.test(b)) return a.length >= 10 && !a.includes("卷"); // i18n-exempt: CBETA 结构字面匹配
    // 带前缀的后半截：首行须是被折断的长行（≥10 字），以免把「XX經 / 序第一」之类误并
    if (reTailPrefixed.test(b)) return a.length >= 10 && !reOrdEnd.test(a);
    return false;
  };
  // 经题前半截：「佛說一切如來真實攝大乘現證 / 三昧大教王經卷第一」「根本說一切有部毘奈耶藥事 / 卷第一」
  // （下一行是卷题），「聖八千頌般若波羅蜜多一百八 / 名真實圓義陀羅尼經」（下一行是经题而首行自己不是）。
  // 首行须 ≥10 字（被折断的长行），短首行多是目录页「旅泊菴稿目錄 / 卷第一」，不并；其后须是署名。
  const titleHeadType = (i: number): "juan" | "head" | null => {
    if (i + 1 >= lines.length || !bylineFollows(i + 2)) return null;
    const a = lines[i].trim();
    const b = lines[i + 1].trim();
    if (!isTitleLike(a) || !b || !isTitleLike(b) || a.length < 10 || a.includes("卷")) return null; // i18n-exempt: CBETA 结构字面匹配
    if (isJuan(a) || isByline(a) || isSection(a) || hasBylineWord(a) || hasBylineWord(b) || isTocTitle(a)) return null;
    if (isJuan(b)) return "juan";
    if (a.length >= 12 && !isHead(a, 0) && isHead(b, 1) && !isByline(b)) return "head";
    return null;
  };
  // 品题折行：「…教理分第二 / 十六之三」「…供養洗浴品 / 第五」「…鬼神成就品第 / 六」——
  // 两行拼起来以「品/分第N」收尾、下一行纯是序数，且其后是空行（品题自成一段）。卷中也认。
  const reSectionTail = new RegExp(`^[${ORD}]{1,4}(?:之[${ORD}]+|之餘)?$`); // i18n-exempt: CBETA 结构字面匹配
  const reSectionEnd = new RegExp(`[品分]第[${ORD}]+(?:之[${ORD}]+|之餘)?$`); // i18n-exempt: CBETA 结构字面匹配
  const sectionFoldEnd = (i: number): boolean => {
    if (i + 1 >= lines.length || !nextIsBlank(i + 2)) return false;
    const a = lines[i].trim();
    const b = lines[i + 1].trim();
    if (!isTitleLike(a) || hasBylineWord(a) || a.length < 4) return false;
    const tailOk = (reSectionTail.test(b) && reOrdEnd.test(a)) || (reTailOrd.test(b) && /[品分]$/.test(a)); // i18n-exempt: CBETA 结构字面匹配
    return tailOk && (a + b).length <= 30 && reSectionEnd.test(a + b);
  };

  const joinLines = (i: number, end: number): { text: string; offsets: number[] } => {
    const first = trimmedOf(i);
    let text = first.text;
    const offsets = first.offsets.slice();
    for (let j = i + 1; j <= end; j++) {
      const part = trimmedOf(j);
      text += part.text;
      offsets.push(...part.offsets);
    }
    return { text, offsets };
  };

  // 正文尚未开始、卷首已出过经题或卷题，且上一段是署名或卷题。要求先有题：引文抽屉的 chunk
  // 若恰好从署名末行切起（「…塞部撰 / 萬治二歲九月吉日」），没有题就不算卷首。
  const atHeaderTail = (): boolean => {
    let last: TextSegment["type"] | null = null;
    let sawTitle = false;
    for (const s of segments) {
      if (s.type === "prose" || s.type === "verse") return false;
      if (s.type === "head" || s.type === "juan") sawTitle = true;
      if (s.type !== "break") last = s.type;
    }
    return sawTitle && (last === "byline" || last === "juan");
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

    // 品题被折成两行：并成一个 section 段
    if (sectionFoldEnd(i)) {
      flushProse();
      const merged = joinLines(i, i + 1);
      segments.push({ type: "section", text: merged.text, offsets: merged.offsets });
      lastNonEmptyLine = lines[i + 1].trim();
      i += 1;
      continue;
    }

    // 卷首经题被折成两行：并成一个 juan/head 段（只在卷首第一行触发）
    if (relIdx === 0) {
      const headType = titleHeadType(i);
      const tail = !headType && titleTailEnd(i);
      if (headType || tail) {
        const merged = joinLines(i, i + 1);
        const type = headType ?? (isJuan(merged.text) ? "juan" : "head");
        segments.push({ type, text: merged.text, offsets: merged.offsets });
        lastNonEmptyLine = lines[i + 1].trim();
        i += 1;
        continue;
      }
    }

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

    if (!proseBuf) {
      const end = splitBylineEnd(i);
      if (end > 0) {
        const { text, offsets } = joinLines(i, end);
        segments.push({ type: "byline", text, offsets });
        lastNonEmptyLine = lines[end].trim();
        i = end;
        continue;
      }
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

    // 卷首品题：署名/卷题之后、正文开始之前，一行无句读的短题自成一段（其后是空行）——
    // 四分律「百眾學法之三」「八波羅夷法」「衣揵度之二」、八揵度論「智揵度之四修智跋渠之餘」。
    // 没有「品第」字样，isSection 认不出，原先被并进正文首段。前一段必须是署名或卷题、
    // 正文尚未开始，且该行不含署名字眼（「菩薩沙彌古吳智旭際明＋全角空格＋釋」之类第二署名人不算）。
    if (
      !proseBuf &&
      atHeaderTail() &&
      trimmed.length <= 20 &&
      isTitleLike(trimmed) &&
      !hasBylineWord(trimmed) &&
      !/[釋解]$/.test(trimmed) &&
      nextIsBlank(i + 1)
    ) {
      segments.push({ type: "section", text: trimmed, offsets: tOffsets });
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

/**
 * Collapse CBETA hard wraps for excerpt / card contexts.
 *
 * `reflowText` is the right tool when a passage is displayed in full — it
 * produces prose and verse segments matching the reader. Excerpts (similar-
 * passage cards, the parallel panel's clamped previews) only need the wraps
 * gone: rendering raw text lets HTML collapse every ~18-char newline into a
 * space, which is what put 「三清 淨」 in the citation drawer before 2026-07-29.
 * The same defect is present anywhere chunk_text reaches the DOM untreated.
 *
 * Lines inside a paragraph are joined with NO separator — Chinese sets no
 * inter-word space, so any separator IS the bug. Blank lines are real
 * paragraph boundaries and survive as "\n\n", which callers render with
 * `white-space: pre-line`.
 */
export function unwrapCbetaLines(raw: string): string {
  return raw
    .split(/\n\s*\n/)
    .map((para) =>
      para
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .join(""),
    )
    .filter(Boolean)
    .join("\n\n");
}
