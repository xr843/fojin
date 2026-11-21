import { describe, it, expect } from "vitest";
import { composerAutoSize } from "./chatComposer";

describe("composerAutoSize", () => {
  it("对话中默认一行，空态两行", () => {
    expect(composerAutoSize(true, false).minRows).toBe(1);
    expect(composerAutoSize(false, false).minRows).toBe(2);
  });
  it("矮屏最多长到 4 行，高屏 8 行", () => {
    expect(composerAutoSize(true, true).maxRows).toBe(4);
    expect(composerAutoSize(true, false).maxRows).toBe(8);
  });
});
