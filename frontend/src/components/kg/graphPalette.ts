// 知识图谱的配色与 i18n 标签表。单独成文件：ForceGraph.tsx 是组件模块，
// 同时导出常量会让 React Fast Refresh 失效（eslint react-refresh/only-export-components）。

/* ── 古典配色 ── */
export const TYPE_COLORS: Record<string, string> = {
  person:    "#c75450",  // 朱砂
  text:      "#4a7c9b",  // 靛青
  monastery: "#6b8e5b",  // 松绿
  school:    "#7b5ea7",  // 紫藤
  place:     "#c08b3e",  // 赭石
  concept:   "#3d8a8a",  // 青碧
  dynasty:   "#b35c8a",  // 洋紫
};

/* i18n key maps — translated at render time via t(); shared by the KG
   surfaces (graph legend, stats panel, mentions panel, entity cards). */
export const TYPE_LABEL_KEYS: Record<string, string> = {
  person: "geo.type_person",
  text: "geo.type_text",
  monastery: "geo.type_temple",
  school: "geo.type_school",
  place: "geo.type_place",
  concept: "geo.type_concept",
  dynasty: "geo.type_dynasty",
};

export const PREDICATE_LABEL_KEYS: Record<string, string> = {
  translated: "kg.pred_translated",
  active_in: "kg.pred_active_in",
  alt_translation: "kg.pred_alt_translation",
  parallel_text: "kg.pred_parallel_text",
  member_of_school: "kg.pred_member_of_school",
  teacher_of: "geo.lineage",
  cites: "kg.pred_cites",
  commentary_on: "kg.pred_commentary_on",
  associated_with: "kg.pred_associated_with",
};

export const PREDICATE_COLORS: Record<string, string> = {
  translated:       "#4a7c9b",
  active_in:        "#b35c8a",
  alt_translation:  "#3d8a8a",
  parallel_text:    "#6b8e5b",
  member_of_school: "#7b5ea7",
  teacher_of:       "#c08b3e",
  cites:            "#bbb5a6",
  commentary_on:    "#c75450",
  associated_with:  "#5b8c6b",  // 翡翠
};
