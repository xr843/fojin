/**
 * 藏译汉稿 Markdown 的预处理：切块（供按需渲染）、目录、校注互跳。
 *
 * 为什么要切块：最大一部 T-2978 约 2.5 MB、一万多行，一次性交给 react-markdown
 * 会把页面卡死好几秒；而它只有 8 个「## 」章节，最大一节就有七百多 KB，只按「## 」
 * 切也不够。所以「## 」必切（目录以它为单位），节内再在标题、空行或校注条目处
 * 按体积切细，每块约 8–16K 字，只渲染视口附近的块。
 *
 * 校注：正文里写作「〔校注 N〕」，校注本身是某个以「校注」结尾的标题下的有序列表。
 * 大多数译稿全书只有一个「## 校注」；T-2970 / T-2978 每「段」各有一节、编号各自
 * 从 1 起。所以一个标记先在**它所在的「## 」块**里找校注节（后面的优先，段末表格
 * 引用的是前面那节），块里没有就指向全书后面最近的一节，再没有就指向最后一节；
 * 在校注节里的互引指向本节。源文件里没有锚点，这里把它们改写成站内锚点链接：
 *   正文标记 → [〔校注 N〕](#tzref-<节>-<N>-<序>)
 *   校注条目 → 行首插入 [↩](#tzback-<节>-<N>)（渲染时它带着校注的 id，并负责跳回）
 * 只改写确有对应校注条目的标记；对不上的保持原文。
 */

export interface TzChunk {
  index: number;
  text: string;
  /** 未渲染时的占位高度估计（px），渲染后用实测值替换 */
  estHeight: number;
  /** 只看汉文时（藏文引用块隐藏）的估计高度 */
  estHeightZhOnly: number;
}

export interface TzTocEntry {
  title: string;
  chunk: number;
}

export interface TzDoc {
  chunks: TzChunk[];
  toc: TzTocEntry[];
  /** 元素 id → 所在块，跳转前用来确保目标块已渲染 */
  anchorChunk: Map<string, number>;
  /** 校注 id（tz-note-s-n）→ 第一个指向它的正文标记 id，用于没点过标记时的「跳回」 */
  firstRefOf: Map<string, string>;
}

export const noteId = (section: number, n: number) => `tz-note-${section}-${n}`;
export const refId = (section: number, n: number, k: number) => `tz-ref-${section}-${n}-${k}`;
export const chunkId = (i: number) => `tz-chunk-${i}`;

const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const FENCE = /^\s*(```|~~~)/;
const NOTE_HEADING = /校注\s*$/;
const NOTE_ITEM = /^(\d+)\.\s/;
const NOTE_REF = /〔校注\s*(\d+)〕/g;
const TIBETAN = /[ༀ-࿿]/;

/** 节内超过这个体积，遇到下一个标题就切 */
const SOFT_CHARS = 8_000;
/** 超过这个体积，空行或校注条目处也切。块越小，每次渲染占主线程越短（藏文排版是大头） */
const HARD_CHARS = 16_000;

interface NoteSection {
  start: number; // 标题行号
  end: number; // 不含
  notes: Set<number>;
}

function findNoteSections(lines: string[], inFence: boolean[]): NoteSection[] {
  const sections: NoteSection[] = [];
  let cur: NoteSection | null = null;
  for (let i = 0; i < lines.length; i++) {
    if (inFence[i]) continue;
    const h = HEADING.exec(lines[i]);
    if (h) {
      if (cur) {
        cur.end = i;
        cur = null;
      }
      if (NOTE_HEADING.test(h[2])) {
        cur = { start: i, end: lines.length, notes: new Set() };
        sections.push(cur);
      }
      continue;
    }
    if (cur) {
      const m = NOTE_ITEM.exec(lines[i]);
      if (m) cur.notes.add(Number(m[1]));
    }
  }
  return sections;
}

function estimateHeight(lines: string[], zhOnly: boolean): number {
  let h = 0;
  for (const line of lines) {
    if (!line.trim()) {
      h += 6;
      continue;
    }
    if (line.startsWith(">")) {
      if (zhOnly) continue;
      // 藏文行高 2.1、字形宽：按每行约 45 字符估
      h += Math.max(1, Math.ceil(line.length / 45)) * 34;
      continue;
    }
    if (/^#{1,6}\s/.test(line)) {
      h += 48;
      continue;
    }
    h += Math.max(1, Math.ceil(line.length / 38)) * 30;
  }
  return Math.max(h, 24);
}

export function prepareDocument(md: string): TzDoc {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");

  const inFence: boolean[] = new Array(lines.length).fill(false);
  {
    let fence = false;
    for (let i = 0; i < lines.length; i++) {
      if (FENCE.test(lines[i])) {
        inFence[i] = true;
        fence = !fence;
        continue;
      }
      inFence[i] = fence;
    }
  }

  // ---- 校注改写
  const sections = findNoteSections(lines, inFence);
  // 每行所在的「## 」块（块号 = 该块之前出现过的一、二级标题数）
  const blockOfLine: number[] = new Array(lines.length);
  {
    let b = 0;
    for (let i = 0; i < lines.length; i++) {
      if (!inFence[i] && /^#{1,2}\s/.test(lines[i])) b++;
      blockOfLine[i] = b;
    }
  }
  const sectionOfLine = (i: number): number => {
    for (let s = 0; s < sections.length; s++) {
      if (i > sections[s].start && i < sections[s].end) return s; // 在校注节内：互引本节
    }
    // 同一「## 」块里有校注节（T-2970/T-2978 的分段校注）：优先它后面的，其次它前面的
    // （段末的异文表、自查表也引用本段校注）
    const sameBlock = sections.map((sec, s) => ({ sec, s })).filter(({ sec }) => blockOfLine[sec.start] === blockOfLine[i]);
    const after = sameBlock.find(({ sec }) => sec.start > i);
    if (after) return after.s;
    if (sameBlock.length) return sameBlock[sameBlock.length - 1].s;
    for (let s = 0; s < sections.length; s++) {
      if (sections[s].start > i) return s; // 后面最近的一节
    }
    return sections.length - 1;
  };
  const firstRefOf = new Map<string, string>();
  const anchorsOfLine: string[][] = lines.map(() => []);
  let refSeq = 0;
  const seenNotes = new Set<string>();
  const out = lines.slice();
  if (sections.length > 0) {
    for (let i = 0; i < lines.length; i++) {
      if (inFence[i]) continue;
      let line = lines[i];
      const s = sectionOfLine(i);
      const sec = sections[s];
      const isNoteItem = i > sec.start && i < sec.end && NOTE_ITEM.exec(line);
      if (line.includes("〔校注")) { // i18n-exempt（源文件里的标记，不是界面文案）
        line = line.replace(NOTE_REF, (whole, num: string) => {
          const n = Number(num);
          if (!sec.notes.has(n)) return whole;
          const k = refSeq++;
          const id = refId(s, n, k);
          anchorsOfLine[i].push(id);
          if (!firstRefOf.has(noteId(s, n))) firstRefOf.set(noteId(s, n), id);
          return `[〔校注 ${n}〕](#tzref-${s}-${n}-${k})`; // i18n-exempt（改写源文件标记）
        });
      }
      if (isNoteItem) {
        const n = Number(isNoteItem[1]);
        const id = noteId(s, n);
        // 同一节里重复的编号只给第一条锚点
        if (!seenNotes.has(id)) {
          seenNotes.add(id);
          line = line.replace(NOTE_ITEM, (m) => `${m}[↩](#tzback-${s}-${n}) `);
          anchorsOfLine[i].push(id);
        }
      }
      out[i] = line;
    }
  }

  // ---- 切块
  const chunks: TzChunk[] = [];
  const toc: TzTocEntry[] = [];
  const anchorChunk = new Map<string, number>();
  let buf: string[] = [];
  let bufChars = 0;
  let bufAnchors: string[] = [];

  const flush = () => {
    if (buf.length === 0) return;
    const index = chunks.length;
    chunks.push({
      index,
      text: buf.join("\n"),
      estHeight: estimateHeight(buf, false),
      estHeightZhOnly: estimateHeight(buf, true),
    });
    for (const a of bufAnchors) anchorChunk.set(a, index);
    buf = [];
    bufChars = 0;
    bufAnchors = [];
  };

  const inNoteSection = (i: number) => sections.some((s) => i > s.start && i < s.end);

  for (let i = 0; i < out.length; i++) {
    const line = out[i];
    if (!inFence[i]) {
      const h = HEADING.exec(line);
      if (h) {
        const level = h[1].length;
        if (level <= 2 || bufChars >= SOFT_CHARS) flush();
        if (level === 2) toc.push({ title: h[2].replace(/〔校注[^〕]*〕/g, ""), chunk: chunks.length });
      } else if (bufChars >= HARD_CHARS) {
        const prevBlank = i > 0 && out[i - 1].trim() === "";
        const noteBoundary = NOTE_ITEM.test(line) && inNoteSection(i);
        // 缩进行可能是上一列表项的续行，不能从这里切
        if ((prevBlank && line.trim() !== "" && !/^\s/.test(line)) || noteBoundary) flush();
      }
    }
    buf.push(line);
    bufChars += line.length + 1;
    if (anchorsOfLine[i].length) bufAnchors.push(...anchorsOfLine[i]);
  }
  flush();

  return { chunks, toc, anchorChunk, firstRefOf };
}

export function hasTibetan(s: string): boolean {
  return TIBETAN.test(s);
}

/** 解析改写后的站内锚点 href。 */
export function parseTzHref(
  href: string | undefined,
): { kind: "ref"; section: number; n: number; k: number } | { kind: "back"; section: number; n: number } | null {
  if (!href) return null;
  let m = /^#tzref-(\d+)-(\d+)-(\d+)$/.exec(href);
  if (m) return { kind: "ref", section: Number(m[1]), n: Number(m[2]), k: Number(m[3]) };
  m = /^#tzback-(\d+)-(\d+)$/.exec(href);
  if (m) return { kind: "back", section: Number(m[1]), n: Number(m[2]) };
  return null;
}
