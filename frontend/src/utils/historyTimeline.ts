/**
 * 佛教史长卷的排布逻辑（纯函数，便于测试）。数据见 public/history-people.json
 * （backend/scripts/build_history_timeline.py 由 DILA 人名规范库生成）。
 */
import { dynastySpan } from "../data/historyDynasties";

export interface HistoryLink {
  t: string;
  u: string;
  lh?: string;
  c?: string;
}

export interface HistoryPerson {
  id: string;
  n: string;
  dn: string;
  alt: string[];
  dy: string;
  b: [number, number] | null;
  d: [number, number] | null;
  monk: boolean;
  tr: boolean;
  bio: string;
  te: string[];
  st: string[];
  bios: HistoryLink[];
  men: HistoryLink[];
  works: HistoryLink[];
  wn: number;
}

export interface HistoryData {
  source: string;
  source_url: string;
  license: string;
  license_url: string;
  people: HistoryPerson[];
}

/** 在长卷上的位置。kind：生卒俱全 / 只知卒年 / 只知生年 / 据小传里的纪年 / 只知朝代。 */
export interface PersonSpan {
  start: number;
  end: number;
  kind: "full" | "death" | "birth" | "bio" | "dynasty";
  /** 生年或卒年是区间（DILA 记「+0602 ~ +0603」）或推算 → 显示「约」 */
  approx: boolean;
}

/** 只知卒年时往前推多少年画生卒条（虚线起头），只知生年同理。 */
export const ASSUMED_LIFE = 60;

export function personSpan(p: HistoryPerson): PersonSpan | null {
  const approx = !!((p.b && p.b[0] !== p.b[1]) || (p.d && p.d[0] !== p.d[1]));
  if (p.b && p.d) return { start: p.b[0], end: p.d[1], kind: "full", approx };
  if (p.d) return { start: p.d[0] - ASSUMED_LIFE, end: p.d[1], kind: "death", approx: true };
  if (p.b) return { start: p.b[0], end: p.b[1] + ASSUMED_LIFE, kind: "birth", approx: true };
  const dyn = dynastySpan(p.dy);
  // 小传里的纪年（「建和二年（148）」）落在本朝之内的，当作活动年代
  const years = [...p.bio.matchAll(/[（(](\d{2,4})[）)]/g)]
    .map((m) => Number(m[1]))
    .filter((y) => (dyn ? y >= dyn[0] && y <= dyn[1] : y > 0 && y < 2000));
  if (years.length) {
    const lo = Math.min(...years);
    const hi = Math.max(...years);
    return { start: lo - 10, end: Math.max(hi, lo) + 10, kind: "bio", approx: true };
  }
  if (dyn) return { start: dyn[0], end: dyn[1], kind: "dynasty", approx: true };
  return null;
}

/** 某年在世：生卒俱全或只缺一头的按条算；只有朝代的不算（不知道在不在）。 */
export function aliveAt(span: PersonSpan | null, year: number): boolean {
  if (!span || span.kind === "dynasty") return false;
  return year >= span.start && year <= span.end;
}

export interface PlacedPerson {
  person: HistoryPerson;
  span: PersonSpan;
  row: number;
}

/**
 * 贪心分行：按起始年排序，放进第一条「上一个人（连同名字）已经结束」的行。
 * 名字放不进条子、写在右侧时也要占地方：labelPx 返回右侧名字的宽度（放得进条子里就返回 0）。
 */
export function packRows(
  people: HistoryPerson[],
  pxPerYear: number,
  labelPx: (p: HistoryPerson) => number,
  gapPx = 6,
): { placed: PlacedPerson[]; rows: number } {
  const items = people
    .map((person) => ({ person, span: personSpan(person) }))
    .filter((x): x is { person: HistoryPerson; span: PersonSpan } => !!x.span)
    .sort((a, b) => a.span.start - b.span.start || a.span.end - b.span.end);
  const rowEnds: number[] = [];
  const placed: PlacedPerson[] = [];
  // 只知朝代的人条子横跨整个朝代、又不知道确切年代，排在有年份的人下面，免得把主体搅乱
  const dated = items.filter((x) => x.span.kind !== "dynasty");
  const undated = items.filter((x) => x.span.kind === "dynasty");
  let floor = 0;
  for (const it of [...dated, ...undated]) {
    if (it === undated[0]) {
      floor = rowEnds.length;
    }
    const barPx = (it.span.end - it.span.start) * pxPerYear;
    const label = labelPx(it.person);
    const needPx = barPx + (label > 0 ? label + 4 : 0);
    const startPx = it.span.start * pxPerYear;
    let row = rowEnds.findIndex((end, i) => i >= floor && end + gapPx <= startPx);
    if (row === -1) {
      row = rowEnds.length;
      rowEnds.push(0);
    }
    rowEnds[row] = startPx + needPx;
    placed.push({ ...it, row });
  }
  return { placed, rows: rowEnds.length };
}

/**
 * 译经长河：每位译经师在藏的著译部数（wn）平摊到他在世的年代里，按 binYears 一格累加。
 * 只是「哪个年代译得多」的估算——DILA 没有逐部的译出年份。
 */
export function translationRiver(people: HistoryPerson[], from: number, to: number, binYears = 10): number[] {
  const bins = new Array(Math.ceil((to - from) / binYears)).fill(0) as number[];
  for (const p of people) {
    if (!p.tr || p.wn <= 0) continue;
    const s = personSpan(p);
    if (!s) continue;
    // 译经多在中晚年：取生卒条的后 2/3（只有朝代的整段平摊）
    const start = s.kind === "dynasty" ? s.start : s.start + (s.end - s.start) / 3;
    const years = Math.max(1, s.end - start);
    for (let y = Math.floor(start); y < s.end; y++) {
      const i = Math.floor((y - from) / binYears);
      if (i >= 0 && i < bins.length) bins[i] += p.wn / years;
    }
  }
  return bins;
}

/** 「638–713」「约602–664」「?–535」；生卒都不详返回空串。DILA 的年份区间显示为「约 + 较早年」（approx 由界面语言给）。 */
export function formatYears(p: HistoryPerson, approx = "~"): string {
  const y = (v: [number, number] | null) => (v ? (v[0] === v[1] ? `${v[0]}` : `${approx}${v[0]}`) : "?");
  if (!p.b && !p.d) return "";
  return `${y(p.b)}–${y(p.d)}`;
}
