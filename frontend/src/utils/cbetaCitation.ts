/**
 * CBETA 学术引用格式（对标 CBETA Online「引用複製」，2026-10-17 实测其产出）：
 *
 *   《金剛般若波羅蜜經》卷1：「佛告須菩提…」(CBETA 2026.R2, T08, no. 235, p. 749a5-7)
 *
 * fojin 的经文导入自 CBETA，但库里没有记下导入的是哪个版本（R1/R2…），所以引用里**不写版本号**，
 * 只写 `CBETA, 册, 经号, 页栏行`——定位信息完整，又不冒称一个我们核对不了的版本。
 *
 * 行号只对大正藏（T）给到页栏行：库里卍续藏（X）的行号混着新文丰版（R）的页码（导入时没区分
 * `<lb ed>`；同一卷里 X、R 页码范围还会重叠，无法事后分开），给出来就会把 R 版页码当 X 版。
 * X 只给到册与经号。
 */

/** public/cbeta-refs/stems.json：经号 → 文件主名，跨册的经按起始卷分段。 */
export type CbetaStems = Record<string, string | Array<[number, string]>>;

export const CBETA_STEMS_URL = "/cbeta-refs/stems.json";

/** 只有这些藏的行号是单一版本、可以给到页栏行。 */
const LINE_LEVEL_COLLECTIONS = new Set(["T"]);

/** 某经某卷所在的 CBETA 文件主名，如 T08n0235。查不到返回 null。 */
export function stemFor(stems: CbetaStems | null | undefined, cbetaId: string, juan: number): string | null {
  const v = stems?.[cbetaId];
  if (!v) return null;
  if (typeof v === "string") return v;
  let hit: string | null = null;
  for (const [start, stem] of v) {
    if (juan >= start) hit = stem;
    else break;
  }
  return hit ?? v[0]?.[1] ?? null;
}

/** T08n0235 → { collection: "T", volume: "T08", no: "235" }；T02n0128a → no "128a"。 */
export function parseStem(stem: string): { collection: string; volume: string; no: string } | null {
  const m = /^([A-Z]+)(\d+)n([A-Z]?)(\d+)([a-z]?)$/.exec(stem);
  if (!m) return null;
  const [, coll, vol, prefix, num, suffix] = m;
  return { collection: coll, volume: `${coll}${vol}`, no: `${prefix}${String(Number(num))}${suffix}` };
}

export function lineLevelSupported(cbetaId: string): boolean {
  const coll = /^[A-Z]+/.exec(cbetaId)?.[0] ?? "";
  return LINE_LEVEL_COLLECTIONS.has(coll);
}

/** 行号 0749a05 → { page: 749, col: "a", line: 5 }。 */
function splitRef(ref: string): { page: number; col: string; line: number } | null {
  const m = /^(\d{4})([a-z])(\d{2})$/.exec(ref);
  if (!m) return null;
  return { page: Number(m[1]), col: m[2], line: Number(m[3]) };
}

/** 页栏行范围，照 CBETA 写法：同栏 p. 749a5-7；跨栏 p. 749a28-b2；跨页 pp. 749a28-750b3。 */
export function formatLineRange(startRef: string, endRef?: string | null): string | null {
  const a = splitRef(startRef);
  if (!a) return null;
  const b = endRef ? splitRef(endRef) : null;
  const head = `${a.page}${a.col}${a.line}`;
  if (!b || (b.page === a.page && b.col === a.col && b.line === a.line)) return `p. ${head}`;
  if (b.page !== a.page) return `pp. ${head}-${b.page}${b.col}${b.line}`;
  if (b.col !== a.col) return `p. ${head}-${b.col}${b.line}`;
  return `p. ${head}-${b.line}`;
}

/** CBETA 行首：T08n0235_p0749a05。 */
export function lineHead(stem: string, ref: string): string {
  return `${stem}_p${ref}`;
}

export interface CitationInput {
  title: string;
  juan: number;
  /** 全经卷数；单卷经照 CBETA 省略「卷1」。 */
  juanCount: number;
  quote: string;
  cbetaId: string;
  stem: string | null;
  startRef?: string | null;
  endRef?: string | null;
  /** 选区内的校勘注，如「[1] 來【大】，不來【明】」，按出现顺序。 */
  notes?: string[];
}

/** 引文里的空白（原书换行、段落间隔）一律去掉：汉文经文没有词间空格。 */
export function normalizeQuote(s: string): string {
  return s.replace(/\s+/g, "").trim();
}

export function formatCbetaCitation(c: CitationInput): string {
  const juanPart = c.juanCount > 1 ? `卷${c.juan}` : ""; // i18n-exempt: CBETA 引用格式的固定写法
  const parsed = c.stem ? parseStem(c.stem) : null;
  const loc: string[] = ["CBETA"];
  if (parsed) {
    loc.push(parsed.volume, `no. ${parsed.no}`);
    if (c.startRef && lineLevelSupported(c.cbetaId)) {
      const range = formatLineRange(c.startRef, c.endRef);
      if (range) loc.push(range);
    }
  } else {
    loc.push(c.cbetaId);
  }
  const quote = normalizeQuote(c.quote);
  const notes = c.notes?.length ? c.notes.join("") : "";
  return `《${c.title}》${juanPart}：「${quote}」(${loc.join(", ")})${notes}`;
}

/**
 * 从搜索框里认出一处 CBETA 定位，转成 { cbetaId, ref }：
 *   - 行首：T08n0235_p0749a05（CBETA Online 网址里的、引用複製「行首格式」的）
 *   - 书目格式：(CBETA 2026.R2, T08, no. 235, p. 749a5-7) / T29, no. 1558, pp. 13b11-14a2（取起点）
 * 认不出返回 null。
 */
export function parseCbetaLocator(input: string): { cbetaId: string; ref: string } | null {
  const s = input.trim();
  const lh = /^([A-Z]+)\d+n([A-Z]?)(\d+)([a-z]?)_?p(\d{4})([a-z])(\d{2})$/.exec(s);
  if (lh) {
    const [, coll, pre, num, suf, page, col, line] = lh;
    return { cbetaId: `${coll}${pre}${num.padStart(pre ? 3 : 4, "0")}${suf}`, ref: `${page}${col}${line}` };
  }
  const bib = /\b([A-Z]+)\d+,\s*no\.\s*([A-Z]?)(\d+)([a-z]?),\s*pp?\.\s*(\d{1,4})([a-z])(\d{1,2})/.exec(s);
  if (bib) {
    const [, coll, pre, num, suf, page, col, line] = bib;
    return {
      cbetaId: `${coll}${pre}${num.padStart(pre ? 3 : 4, "0")}${suf}`,
      ref: `${page.padStart(4, "0")}${col}${line.padStart(2, "0")}`,
    };
  }
  return null;
}
