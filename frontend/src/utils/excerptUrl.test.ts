import { describe, it, expect } from "vitest";
import { excerptReaderUrl } from "./excerptUrl";

describe("excerptReaderUrl", () => {
  it("大正藏、卍续藏、嘉興藏等带到行，没收的藏只带到卷", () => {
    expect(excerptReaderUrl({ text_id: 15, juan_num: 8, line_ref: "0413a07", cbeta_id: "T0374" })).toBe(
      "/texts/15/read?juan=8&anchor=p0413a07",
    );
    expect(excerptReaderUrl({ text_id: 9, juan_num: 2, line_ref: "0101a01", cbeta_id: "X0001" })).toBe(
      "/texts/9/read?juan=2&anchor=p0101a01",
    );
    expect(excerptReaderUrl({ text_id: 7, juan_num: 1, line_ref: "0450a05", cbeta_id: "JB095" })).toBe(
      "/texts/7/read?juan=1&anchor=p0450a05",
    );
    expect(excerptReaderUrl({ text_id: 5, juan_num: 1, line_ref: "0001a01", cbeta_id: "SC-dn1" })).toBe(
      "/texts/5/read?juan=1",
    );
  });
});
