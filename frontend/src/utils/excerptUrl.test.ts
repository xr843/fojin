import { describe, it, expect } from "vitest";
import { excerptReaderUrl } from "./excerptUrl";

describe("excerptReaderUrl", () => {
  it("大正藏带到行，卍续藏只带到卷", () => {
    expect(excerptReaderUrl({ text_id: 15, juan_num: 8, line_ref: "0413a07", cbeta_id: "T0374" })).toBe(
      "/texts/15/read?juan=8&anchor=p0413a07",
    );
    expect(excerptReaderUrl({ text_id: 9, juan_num: 2, line_ref: "0101a01", cbeta_id: "X0001" })).toBe(
      "/texts/9/read?juan=2",
    );
  });
});
