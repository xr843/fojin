import { describe, expect, it } from "vitest";
import { dropServerCanonical } from "./dropServerCanonical";

describe("dropServerCanonical", () => {
  it("removes the shell's canonical but leaves Helmet-managed ones and hreflang alone", () => {
    document.head.innerHTML = [
      '<link rel="canonical" href="https://fojin.app/" />',
      '<link rel="canonical" href="https://fojin.app/texts/9?lang=en" data-rh="true" />',
      '<link rel="alternate" hreflang="en" href="https://fojin.app/?lang=en" />',
    ].join("");
    dropServerCanonical(document);
    const canonicals = [...document.head.querySelectorAll('link[rel="canonical"]')].map((l) => l.getAttribute("href"));
    expect(canonicals).toEqual(["https://fojin.app/texts/9?lang=en"]);
    expect(document.head.querySelectorAll('link[rel="alternate"]')).toHaveLength(1);
  });
});
