/**
 * MapTiler 底图的地名改成中文，台湾统一标「台灣省」（/map 与佛教史长卷共用）。
 * 抽自 DeckGLMap（2026-11-27）：MapTiler 的 style.json 不认 language 参数里的中文，要改每个文字层的 text-field。
 */
type StyleLike = { layers?: Array<{ id: string; type: string; layout?: Record<string, unknown> }> };

export function zhLabelExpression(traditional = false): unknown[] {
  const order = traditional
    ? ["name:zh-Hant", "name:zh", "name:zh-Hans"]
    : ["name:zh-Hans", "name:zh", "name:zh-Hant"];
  return [
    "case",
    ["==", ["get", "iso_a2"], "TW"], "台灣省", // i18n-exempt
    ["==", ["get", "ISO_A2"], "TW"], "台灣省", // i18n-exempt
    ["==", ["get", "iso_3166_1"], "TW"], "台灣省", // i18n-exempt
    ["==", ["get", "iso_3166_1_alpha_2"], "TW"], "台灣省", // i18n-exempt
    ["==", ["get", "name"], "中華民國"], "台灣省", // i18n-exempt
    ["==", ["get", "name"], "中华民国"], "台灣省", // i18n-exempt
    ["==", ["get", "name"], "Taiwan"], "台灣省", // i18n-exempt
    ["==", ["get", "name"], "Republic of China"], "台灣省", // i18n-exempt
    ["==", ["get", "name:zh"], "中華民國"], "台灣省", // i18n-exempt
    ["==", ["get", "name:zh"], "中华民国"], "台灣省", // i18n-exempt
    ["==", ["get", "name:zh-Hant"], "中華民國"], "台灣省", // i18n-exempt
    ["==", ["get", "name:zh-Hant"], "臺灣"], "台灣省", // i18n-exempt
    ["==", ["get", "name:zh-Hant"], "台灣"], "台灣省", // i18n-exempt
    ["==", ["get", "name:zh-Hans"], "中华民国"], "台灣省", // i18n-exempt
    ["==", ["get", "name:zh-Hans"], "台湾"], "台灣省", // i18n-exempt
    ["==", ["get", "name:en"], "Taiwan"], "台灣省", // i18n-exempt
    ["==", ["get", "name:en"], "Republic of China"], "台灣省", // i18n-exempt
    [
      "coalesce",
      ...order.map((k) => ["get", k]),
      ["get", "name:ja"],
      ["get", "name_int"],
      ["get", "name:latin"],
      ["get", "name:en"],
      ["get", "name"],
    ],
  ];
}

/** 就地改写样式里所有显示地名的文字层，返回同一个对象。 */
export function patchZhLabels<T extends StyleLike>(style: T, traditional = false): T {
  if (!style.layers) return style;
  const expr = zhLabelExpression(traditional);
  for (const layer of style.layers) {
    if (layer.type !== "symbol" || !layer.layout) continue;
    if (!("text-field" in layer.layout)) continue;
    const orig = JSON.stringify(layer.layout["text-field"] ?? "");
    if (!orig.includes("name")) continue;
    layer.layout["text-field"] = expr;
  }
  return style;
}
