import collectionsEn from "../content/collectionLocales/en.json";
import collectionsZhHant from "../content/collectionLocales/zh-Hant.json";
import collectionsZh from "../content/collectionLocales/zh.json";

export interface CollectionText {
  key: string;
  title: string;
  cbeta_id?: string;
  author?: string;
  dynasty?: string;
  note?: string;
}

export interface CollectionLink {
  key: string;
  name: string;
  url: string;
  desc?: string;
}

export const RESOURCE_CATEGORY_KEYS = ["reading", "translation", "manuscript", "research", "temple"] as const;

export type ResourceCategory = (typeof RESOURCE_CATEGORY_KEYS)[number];

export type ResourceCategoryLabels = Record<ResourceCategory, string>;

export interface CollectionResources {
  reading?: CollectionLink[];
  translation?: CollectionLink[];
  manuscript?: CollectionLink[];
  research?: CollectionLink[];
  temple?: CollectionLink[];
}

export interface Collection {
  id: string;
  name: string;
  tradition: string;
  description: string;
  searchQuery: string;
  mainTexts: CollectionText[];
  commentaries: CollectionText[];
  resources: CollectionResources;
}

interface CollectionLocaleData {
  resourceCategories: ResourceCategoryLabels;
  collections: Collection[];
}

type CollectionLocaleKey = "en" | "zh" | "zh-Hant";

const COLLECTION_LOCALES: Record<CollectionLocaleKey, CollectionLocaleData> = {
  en: collectionsEn,
  zh: collectionsZh,
  "zh-Hant": collectionsZhHant,
};

function normalizeCollectionLocale(language: string): CollectionLocaleKey {
  if (language.startsWith("en")) return "en";
  if (
    language.startsWith("zh-Hant") ||
    language.startsWith("zh-TW") ||
    language.startsWith("zh-HK")
  ) {
    return "zh-Hant";
  }
  return "zh";
}

export function getLocalizedCollections(language = "zh"): Collection[] {
  const locale = normalizeCollectionLocale(language);
  return COLLECTION_LOCALES[locale].collections;
}

export function getLocalizedResourceCategories(language = "zh"): ResourceCategoryLabels {
  const locale = normalizeCollectionLocale(language);
  return COLLECTION_LOCALES[locale].resourceCategories;
}

export const RESOURCE_CATEGORIES: ResourceCategoryLabels = getLocalizedResourceCategories("zh");

const collections: Collection[] = getLocalizedCollections("zh");

export default collections;
