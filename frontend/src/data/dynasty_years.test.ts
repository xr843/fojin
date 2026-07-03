import { describe, expect, it } from "vitest";
import { getDynastyLabel, getLocalizedDynasties, resolveDynasty } from "./dynasty_years";

describe("dynasty year locale data", () => {
  it("resolves aliases before localizing dynasty labels", () => {
    expect(resolveDynasty("姚秦")?.key).toBe("sixteen_kingdoms");
    expect(getDynastyLabel("姚秦", "en")).toBe("Sixteen Kingdoms");
  });

  it("returns localized dynasty period names while keeping canonical lookup names stable", () => {
    const westernHan = getLocalizedDynasties("zh-Hant").find((dynasty) => dynasty.key === "western_han");

    expect(westernHan?.name_zh).toBe("西汉");
    expect(westernHan?.name).toBe("西漢");
    expect(getDynastyLabel("唐", "en-US")).toBe("Tang Dynasty");
  });

  it("falls back to the original label for unknown dynasty names", () => {
    expect(getDynastyLabel("未知朝代", "en")).toBe("未知朝代");
  });
});
