/**
 * SAT 大正藏数据库（東京大学）链接。
 *
 * 只做外链，不嵌入影像：SAT 利用条件覆盖「各頁画像」，且当前禁止经互联网等媒体
 * 再分发（https://21dzk.l.u-tokyo.ac.jp/SAT/termsofuse.html，2026-10-05 核）。
 * 读者点过去，在 SAT 自己的页面里切「版面画像」看原页。
 *
 * URL 格式均为浏览器实测（SAT 对任何路径都回同一个 JS 外壳，curl 200 证明不了什么）：
 *   经：  SAT2018/T0235.html
 *   行：  SAT2018/T0235_.08.0748c24.html   ← 需要册号，翻到该页并定位到该行
 * 旧格式 master30.php?no=0235 只打开 SAT 首页、不打开经文。
 */

const SAT_BASE = "https://21dzk.l.u-tokyo.ac.jp/SAT2018";

/**
 * 大正藏各册的起始经号（由 CBETA xml-p5 的 T{册}n{经号}.xml 文件名导出，2,390 个文件）。
 * 经号随册单调递增，所以「起始号 ≤ 经号」的最后一册就是所在册。
 * 第 56–84 册（日本撰述等）不在 CBETA 里：第 55 册末号 2184 与第 85 册首号 2732
 * 之间一律视为未知，不猜。T0220《大般若经》跨第 5–7 册，单独处理。
 */
const VOLUME_STARTS: [number, number][] = [
  [1, 1], [2, 99], [3, 152], [4, 192], [5, 220], [8, 221], [9, 262], [10, 279],
  [11, 310], [12, 321], [13, 397], [14, 425], [15, 585], [16, 656], [17, 721],
  [18, 848], [19, 918], [20, 1030], [21, 1199], [22, 1421], [23, 1435], [24, 1448],
  [25, 1505], [26, 1519], [27, 1545], [28, 1546], [29, 1558], [30, 1564], [31, 1585],
  [32, 1628], [33, 1693], [34, 1718], [35, 1731], [36, 1736], [37, 1744], [38, 1765],
  [39, 1783], [40, 1804], [41, 1821], [42, 1824], [43, 1829], [44, 1835], [45, 1852],
  [46, 1911], [47, 1957], [48, 2001], [49, 2026], [50, 2040], [51, 2066], [52, 2102],
  [53, 2121], [54, 2123], [55, 2145], [85, 2732],
];
const LAST_IN_VOL_55 = 2184;
const LAST_IN_VOL_85 = 2920;

const TAISHO_ID = /^T(\d{4})([a-z]?)$/;

/** 大般若经 600 卷：第 5 册 1–200 卷、第 6 册 201–400、第 7 册 401–600；
 *  fojin 把它拆成 T0220a/b/c 三部，每部卷号从 1 起。 */
function daihannyaVolume(suffix: string, juan: number | null | undefined): number | null {
  if (suffix === "a") return 5;
  if (suffix === "b") return 6;
  if (suffix === "c") return 7;
  if (juan == null) return null;
  return juan <= 200 ? 5 : juan <= 400 ? 6 : 7;
}

/** 大正藏经号所在的册；非大正藏或 CBETA 未收的号段返回 null。 */
export function taishoVolume(cbetaId: string, juan?: number | null): number | null {
  const m = TAISHO_ID.exec(cbetaId);
  if (!m) return null;
  const no = Number(m[1]);
  if (no === 220) return daihannyaVolume(m[2], juan);
  if ((no > LAST_IN_VOL_55 && no < 2732) || no > LAST_IN_VOL_85 || no < 1) return null;
  let vol: number | null = null;
  for (const [v, start] of VOLUME_STARTS) {
    if (start > no) break;
    vol = v;
  }
  return vol;
}

/** SAT 上该经的页面；非大正藏返回 null。 */
export function satTextUrl(cbetaId: string): string | null {
  const m = TAISHO_ID.exec(cbetaId);
  return m ? `${SAT_BASE}/T${m[1]}.html` : null;
}

/** SAT 上该行所在页（定位到该行，可切「版面画像」看原页）；拿不到册号时退回经页面。 */
export function satLineUrl(cbetaId: string, lineRef: string, juan?: number | null): string | null {
  const m = TAISHO_ID.exec(cbetaId);
  if (!m) return null;
  const vol = taishoVolume(cbetaId, juan);
  if (vol == null || !/^\d{4}[abc]\d{2}$/.test(lineRef)) return satTextUrl(cbetaId);
  return `${SAT_BASE}/T${m[1]}_.${String(vol).padStart(2, "0")}.${lineRef}.html`;
}
