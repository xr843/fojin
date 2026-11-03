// Standard Taishō Tripiṭaka section (部) by serial number. The Chinese section
// names are scholarly proper nouns shown as-is in every locale (i18n-exempt).
// Used by the cross-canon browse page to group the 1000+ aligned texts.

const RANGES: Array<[number, number, string]> = [
  [1, 151, "阿含部"], // i18n-exempt
  [152, 219, "本緣部"], // i18n-exempt
  [220, 261, "般若部"], // i18n-exempt
  [262, 277, "法華部"], // i18n-exempt
  [278, 309, "華嚴部"], // i18n-exempt
  [310, 373, "寶積部"], // i18n-exempt
  [374, 396, "涅槃部"], // i18n-exempt
  [397, 424, "大集部"], // i18n-exempt
  [425, 847, "經集部"], // i18n-exempt
  [848, 1420, "密教部"], // i18n-exempt
  [1421, 1504, "律部"], // i18n-exempt
  [1505, 1535, "釋經論部"], // i18n-exempt
  [1536, 1563, "毗曇部"], // i18n-exempt
  [1564, 1578, "中觀部"], // i18n-exempt
  [1579, 1627, "瑜伽部"], // i18n-exempt
  [1628, 1692, "論集部"], // i18n-exempt
  [1693, 1803, "經疏部"], // i18n-exempt
  [1804, 1815, "律疏部"], // i18n-exempt
  [1816, 1850, "論疏部"], // i18n-exempt
  [1851, 2025, "諸宗部"], // i18n-exempt
  [2026, 2120, "史傳部"], // i18n-exempt
  [2121, 2136, "事彙部"], // i18n-exempt
  [2137, 2144, "外教部"], // i18n-exempt
  [2145, 2184, "目錄部"], // i18n-exempt
  // 第 56–85 册（日本撰述与敦煌古逸、疑伪经）。读经页的部类浏览要覆盖生产里全部 T 号
  //（最大 T2920），跨藏对照页原本只到 2184。
  [2185, 2245, "續經疏部"], // i18n-exempt
  [2246, 2248, "續律疏部"], // i18n-exempt
  [2249, 2295, "續論疏部"], // i18n-exempt
  [2296, 2700, "續諸宗部"], // i18n-exempt
  [2701, 2731, "悉曇部"], // i18n-exempt
  [2732, 2864, "古逸部"], // i18n-exempt
  [2865, 2920, "疑似部"], // i18n-exempt
];

// 简体界面用的部名（只有与繁体不同的才列）。部名是学术专名，英文界面也显示汉字。
const SIMPLIFIED: Record<string, string> = {
  本緣部: "本缘部", // i18n-exempt
  法華部: "法华部", // i18n-exempt
  華嚴部: "华严部", // i18n-exempt
  寶積部: "宝积部", // i18n-exempt
  經集部: "经集部", // i18n-exempt
  釋經論部: "释经论部", // i18n-exempt
  毗曇部: "毗昙部", // i18n-exempt
  中觀部: "中观部", // i18n-exempt
  論集部: "论集部", // i18n-exempt
  經疏部: "经疏部", // i18n-exempt
  論疏部: "论疏部", // i18n-exempt
  諸宗部: "诸宗部", // i18n-exempt
  史傳部: "史传部", // i18n-exempt
  事彙部: "事汇部", // i18n-exempt
  目錄部: "目录部", // i18n-exempt
  續經疏部: "续经疏部", // i18n-exempt
  續律疏部: "续律疏部", // i18n-exempt
  續論疏部: "续论疏部", // i18n-exempt
  續諸宗部: "续诸宗部", // i18n-exempt
  悉曇部: "悉昙部", // i18n-exempt
};

export interface TaishoSectionRange {
  /** 繁体部名（与 taishoSection() 返回值一致，可作 key） */
  name: string;
  /** 简体部名 */
  nameHans: string;
  from: number;
  to: number;
}

/** 大正藏各部的编号区间，按册序。读经页「按部类浏览」用。 */
export const TAISHO_SECTIONS: TaishoSectionRange[] = RANGES.map(([from, to, name]) => ({
  name,
  nameHans: SIMPLIFIED[name] ?? name,
  from,
  to,
}));

const OTHER = "其他"; // i18n-exempt

/** Taishō section (部) name for a `T####` id, e.g. "T0220" -> "般若部". */
export function taishoSection(taishoId: string | null | undefined): string {
  if (!taishoId) return OTHER;
  const m = /^[A-Za-z]*0*(\d+)/.exec(taishoId);
  if (!m) return OTHER;
  const n = parseInt(m[1], 10);
  for (const [lo, hi, name] of RANGES) {
    if (n >= lo && n <= hi) return name;
  }
  return OTHER;
}

/** Canonical display order of sections (for grouping). */
export const SECTION_ORDER: string[] = [...RANGES.map((r) => r[2]), OTHER];
