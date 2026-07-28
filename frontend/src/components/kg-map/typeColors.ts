/** Marker palette for the geo map, one set per basemap.
 *
 *  The -600 shades are tuned for the light basemap and go muddy on the dark one
 *  (red 2.42:1, violet 2.05:1, blue 2.26:1 against its hsl(216,37%,24%) land) —
 *  below the 3:1 floor for graphics even with the white halo the dots carry. The
 *  dark set lifts each hue one Tailwind step to -400, keeping the same hue
 *  mapping so the legend still reads as the same colour language.
 *
 *  Lives in its own module so the map dots (DeckGLMap) and the legend swatches
 *  (KGMapPage) share one source — they used to keep two hardcoded copies.
 */
const TYPE_COLORS_LIGHT: Record<string, [number, number, number]> = {
  person: [220, 38, 38], // 鲜红 (red-600)
  monastery: [34, 197, 94], // 鲜绿 (green-500)
  place: [124, 58, 237], // 鲜紫 (violet-600)
  school: [37, 99, 235], // 蓝 (blue-600)
  text: [6, 182, 212], // 青 (cyan-500)
  concept: [8, 145, 178], // 深青
  dynasty: [219, 39, 119], // 洋红 (pink-600)
};

const TYPE_COLORS_DARK: Record<string, [number, number, number]> = {
  person: [248, 113, 113], // red-400     2.42 -> 4.22
  monastery: [74, 222, 128], // green-400   5.12 -> 6.71
  place: [167, 139, 250], // violet-400  2.05 -> 4.29
  school: [96, 165, 250], // blue-400    2.26 -> 4.59
  text: [34, 211, 238], // cyan-400    4.81 -> 6.46
  concept: [103, 232, 249], // cyan-300    3.17 -> 8.03
  dynasty: [244, 114, 182], // pink-400    2.54 -> 4.41
};

export function typeColors(isDark: boolean) {
  return isDark ? TYPE_COLORS_DARK : TYPE_COLORS_LIGHT;
}

export function typeColorCss(isDark: boolean): Record<string, string> {
  return Object.fromEntries(
    Object.entries(typeColors(isDark)).map(([k, [r, g, b]]) => [k, `rgb(${r}, ${g}, ${b})`]),
  );
}
