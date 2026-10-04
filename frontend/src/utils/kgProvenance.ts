import type { TFunction } from "i18next";

/* 知识图谱关系的来源标签。关系的 source 记录这条断言从哪来——权威规范库、
   程序自动抽取，还是人工校订的种子数据。显示成人话，让读者判断一条边该
   信几分；内部代码（auto:cbeta_cf_note）原样给读者看等于没说。 */
const SOURCE_LABEL_KEYS: Record<string, string> = {
  dila_catalog: "entity.source_dila_catalog",
  dila: "entity.source_dila",
  "auto:cbeta_metadata": "entity.source_cbeta_metadata",
  "seed:lineage": "entity.source_seed_lineage",
  "seed:person_place": "entity.source_seed_person_place",
  "seed:school_affiliation": "entity.source_seed_school_affiliation",
};

const CBETA_CATALOG_PREFIX = "cbeta_xml:catalog:";

export function prettifySource(t: TFunction, source: string): string {
  if (SOURCE_LABEL_KEYS[source]) return t(SOURCE_LABEL_KEYS[source]);
  if (source.startsWith(CBETA_CATALOG_PREFIX)) {
    return t("entity.source_cbeta_catalog", { id: source.slice(CBETA_CATALOG_PREFIX.length) });
  }
  if (source.startsWith("seed:")) return t("entity.source_seed_generic");
  if (source.startsWith("auto:")) return t("entity.source_auto_generic");
  if (source.startsWith("dila")) return t("entity.source_dila");
  return source;
}
