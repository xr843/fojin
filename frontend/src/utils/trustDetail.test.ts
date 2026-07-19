import { describe, it, expect } from "vitest";

import { quoteCheckDetail } from "./trustDetail";
import type { ChatTrustStatus } from "../api/client";

const status = (over: Partial<ChatTrustStatus>): ChatTrustStatus => ({
  state: "verified",
  citation_count: 1,
  source_count: 1,
  citation_mutation_count: 0,
  quote_mutation_count: 0,
  ...over,
});

describe("quoteCheckDetail", () => {
  it("returns null when there is no trust status", () => {
    expect(quoteCheckDetail(null)).toBeNull();
  });

  it("returns null for a historical answer with no stored count", () => {
    expect(quoteCheckDetail(status({ quote_checked_count: null }))).toBeNull();
    expect(quoteCheckDetail(status({}))).toBeNull();
  });

  it("reports how many quotes were verbatim-checked", () => {
    expect(quoteCheckDetail(status({ quote_checked_count: 2 }))).toEqual({
      key: "chat.trust.quotes_checked",
      count: 2,
    });
  });

  it("flags a green 'verified' answer that verbatim-checked no quote", () => {
    expect(
      quoteCheckDetail(status({ state: "verified", quote_checked_count: 0 })),
    ).toEqual({ key: "chat.trust.no_verbatim_quote" });
  });

  it("stays silent about zero checks when the badge is not the green verified one", () => {
    expect(
      quoteCheckDetail(status({ state: "sources_available", quote_checked_count: 0 })),
    ).toBeNull();
    expect(
      quoteCheckDetail(status({ state: "quote_relaxed", quote_checked_count: 0 })),
    ).toBeNull();
  });
});
