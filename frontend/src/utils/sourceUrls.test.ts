import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import { buildReaderUrl, getSourceLabel } from "./sourceUrls";

i18n.addResourceBundle("en", "translation", enTranslation, true, true);

describe("source URL labels", () => {
  it("uses the active translator for source labels", () => {
    expect(getSourceLabel("ctext", i18n.getFixedT("en"))).toBe("Chinese Text Project");
    expect(getSourceLabel("sat", i18n.getFixedT("en"))).toBe("SAT Taisho Tripitaka");
  });

  it("falls back to the source code for unknown labels", () => {
    expect(getSourceLabel("unknown-source", i18n.getFixedT("en"))).toBe("UNKNOWN-SOURCE");
  });
});

describe("buildReaderUrl", () => {
  // 站内阅读器的真实路由是 /texts/:id/read，卷号走 ?juan= 查询参数
  // （TextReaderPage 读 searchParams.get("juan")）。搜索卡片一律经此构建，
  // 避免再出现拼错的 /read/:id/:juan 这类不存在的路径。
  it("builds the in-app reader URL with the juan query param", () => {
    expect(buildReaderUrl(12326, 10)).toBe("/texts/12326/read?juan=10");
  });

  it("omits the juan param when no juan is given", () => {
    expect(buildReaderUrl(12326)).toBe("/texts/12326/read");
  });

  // ParallelSentenceHit.juan_num 可以是 null；旧的模板字符串会把它拼成
  // 字面量 "null"（/read/12326/null），必须退化成不带卷号的阅读器 URL。
  it("treats a null juan as no juan rather than stringifying it", () => {
    expect(buildReaderUrl(12326, null)).toBe("/texts/12326/read");
  });
});
