import { describe, expect, it } from "vitest";
import { localizeHan } from "../utils/hanScript";
import { TAISHO_SECTIONS } from "./taishoSections";

describe("TAISHO_SECTIONS", () => {
  it("每个部的简体名都与 OpenCC 转换一致（漏一个就会在简体界面繁简混排）", () => {
    for (const s of TAISHO_SECTIONS) {
      expect(s.nameHans, s.name).toBe(localizeHan(s.name, "zh"));
    }
  });
});
