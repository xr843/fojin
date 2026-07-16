import { describe, it, expect } from "vitest";

import { hasDisplayConfidence } from "./parallelDisplay";

describe("hasDisplayConfidence", () => {
  it("is false for a MITRA inline parallel (its 1.0 confidence is a constant import flag, not a score)", () => {
    expect(hasDisplayConfidence({ source: "mitra-parallel" })).toBe(false);
  });

  it("is true for a fojin alignment_pairs parallel (carries a real LLM/reviewer score)", () => {
    expect(hasDisplayConfidence({ source: "fojin" })).toBe(true);
  });

  it("is true when source is absent (defaults to a deep-linkable fojin pair)", () => {
    expect(hasDisplayConfidence({})).toBe(true);
  });
});
