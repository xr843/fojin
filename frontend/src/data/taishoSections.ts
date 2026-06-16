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
];

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
