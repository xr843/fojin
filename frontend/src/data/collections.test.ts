import { describe, expect, it } from "vitest";
import collections, {
  getLocalizedCollections,
  getLocalizedResourceCategories,
  RESOURCE_CATEGORY_KEYS,
} from "./collections";

describe("collections locale data", () => {
  const expectedIds = [
    "huayan",
    "prajna",
    "lotus",
    "shurangama",
    "pureland",
    "yogacara",
    "chan",
    "vinaya",
    "agama",
    "esoteric",
    "nirvana",
    "abhidharma",
    "pali-canon",
  ];

  const expectedCounts = {
    huayan: [8, 17, [5, 5, 5, 5, 3]],
    prajna: [10, 13, [5, 5, 5, 5, 3]],
    lotus: [3, 11, [4, 5, 4, 3, 3]],
    shurangama: [1, 7, [4, 3, 2, 2, 2]],
    pureland: [4, 10, [3, 4, 3, 3, 4]],
    yogacara: [10, 5, [4, 4, 4, 4, 2]],
    chan: [8, 5, [4, 3, 3, 3, 4]],
    vinaya: [8, 5, [4, 4, 2, 3, 2]],
    agama: [6, 4, [4, 4, 3, 4, 2]],
    esoteric: [6, 6, [3, 3, 3, 3, 3]],
    nirvana: [7, 6, [3, 3, 3, 3, 1]],
    abhidharma: [8, 4, [3, 3, 3, 3, 2]],
    "pali-canon": [6, 4, [5, 4, 3, 4, 3]],
  } as const;

  it("keeps the localized collection catalog structurally aligned", () => {
    const zhHant = getLocalizedCollections("zh-Hant");
    const en = getLocalizedCollections("en-US");

    expect(collections.map((collection) => collection.id)).toEqual(expectedIds);
    expect(zhHant).toHaveLength(collections.length);
    expect(en).toHaveLength(collections.length);
    expect(zhHant.map((collection) => collection.id)).toEqual(collections.map((collection) => collection.id));
    expect(en.map((collection) => collection.id)).toEqual(collections.map((collection) => collection.id));
  });

  it("preserves collection, text, and resource totals", () => {
    const totalTexts = collections.reduce((sum, collection) => sum + collection.mainTexts.length + collection.commentaries.length, 0);
    const totalResources = collections.reduce(
      (sum, collection) =>
        sum + RESOURCE_CATEGORY_KEYS.reduce((resourceSum, category) => resourceSum + (collection.resources[category]?.length ?? 0), 0),
      0,
    );

    expect(collections).toHaveLength(13);
    expect(collections.reduce((sum, collection) => sum + collection.mainTexts.length, 0)).toBe(85);
    expect(collections.reduce((sum, collection) => sum + collection.commentaries.length, 0)).toBe(97);
    expect(totalTexts).toBe(182);
    expect(totalResources).toBe(223);

    for (const collection of collections) {
      const [mainTexts, commentaries, resources] = expectedCounts[collection.id as keyof typeof expectedCounts];
      expect(collection.mainTexts).toHaveLength(mainTexts);
      expect(collection.commentaries).toHaveLength(commentaries);
      expect(RESOURCE_CATEGORY_KEYS.map((category) => collection.resources[category]?.length ?? 0)).toEqual(resources);
    }
  });

  it("localizes collection and category display labels", () => {
    expect(getLocalizedCollections("zh-Hant")[0].name).toBe("華嚴經系列");
    expect(getLocalizedResourceCategories("en").reading).toBe("Online Reading");
  });

  it("preserves search-critical ids and resource category keys", () => {
    const huayan = getLocalizedCollections("en").find((collection) => collection.id === "huayan");

    expect(RESOURCE_CATEGORY_KEYS).toEqual(["reading", "translation", "manuscript", "research", "temple"]);
    expect(huayan?.searchQuery).toBe("华严经");
    expect(huayan?.mainTexts[0].cbeta_id).toBe("T0278");
    expect(huayan?.resources.reading?.[0].url).toBe("https://cbetaonline.dila.edu.tw/zh/T0279");
  });

  it("keeps invariant keys, cbeta ids, and urls aligned across locales", () => {
    const signature = (language: string) =>
      getLocalizedCollections(language).map((collection) => ({
        id: collection.id,
        searchQuery: collection.searchQuery,
        mainTexts: collection.mainTexts.map((text) => ({ key: text.key, cbeta_id: text.cbeta_id })),
        commentaries: collection.commentaries.map((text) => ({ key: text.key, cbeta_id: text.cbeta_id })),
        resources: RESOURCE_CATEGORY_KEYS.map((category) => ({
          category,
          links: (collection.resources[category] ?? []).map((link) => ({ key: link.key, url: link.url })),
        })),
      }));

    expect(signature("en")).toEqual(signature("zh"));
    expect(signature("zh-Hant")).toEqual(signature("zh"));
  });

  it("keeps stable keys unique within each collection list", () => {
    for (const collection of getLocalizedCollections("en")) {
      const mainKeys = collection.mainTexts.map((text) => text.key);
      const commentaryKeys = collection.commentaries.map((text) => text.key);
      expect(new Set(mainKeys).size).toBe(mainKeys.length);
      expect(new Set(commentaryKeys).size).toBe(commentaryKeys.length);

      for (const category of RESOURCE_CATEGORY_KEYS) {
        const resourceKeys = (collection.resources[category] ?? []).map((link) => link.key);
        expect(new Set(resourceKeys).size).toBe(resourceKeys.length);
      }
    }
  });
});
