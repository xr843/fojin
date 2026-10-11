import { describe, expect, it } from "vitest";
import { dropServerCanonical } from "./dropServerCanonical";

function head(...tags: string[]) {
  document.head.innerHTML = tags.join("");
}
const canonicals = () =>
  [...document.head.querySelectorAll('link[rel="canonical"]')].map((l) => l.getAttribute("href"));

describe("dropServerCanonical", () => {
  it("drops a shell canonical that names another page (SPA fallback routes)", () => {
    head('<link rel="canonical" href="https://fojin.app/" />');
    dropServerCanonical("/map", "zh-Hant", document);
    expect(canonicals()).toEqual([]);
  });

  it("keeps a shell canonical that already names this page in this language", () => {
    // /chat sets no canonical in <Helmet>; the shell's is the only one and it is right.
    head('<link rel="canonical" href="https://fojin.app/chat?lang=en" />');
    dropServerCanonical("/chat", "en", document);
    expect(canonicals()).toEqual(["https://fojin.app/chat?lang=en"]);
  });

  it("never touches Helmet-managed tags or hreflang", () => {
    head(
      '<link rel="canonical" href="https://fojin.app/x" data-rh="true" />',
      '<link rel="alternate" hreflang="en" href="https://fojin.app/?lang=en" />',
    );
    dropServerCanonical("/map", "zh", document);
    expect(canonicals()).toEqual(["https://fojin.app/x"]);
    expect(document.head.querySelectorAll('link[rel="alternate"]')).toHaveLength(1);
  });
});
