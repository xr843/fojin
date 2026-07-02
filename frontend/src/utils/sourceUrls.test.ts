import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import { getSourceLabel } from "./sourceUrls";

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
