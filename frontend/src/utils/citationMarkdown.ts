import { defaultUrlTransform } from "react-markdown";
import { defaultSchema } from "rehype-sanitize";
import { CITATION_URL_SCHEME } from "./citationLinks";

/**
 * Sanitize schema + URL transform that let `fojin-citation://` links (emitted by
 * injectCitationLinks) survive react-markdown. Both layers drop unknown schemes:
 * urlTransform rewrites them to "" before rehype runs, and rehype-sanitize then
 * strips any href whose protocol is not allowlisted.
 */
export const CITATION_SANITIZE_SCHEMA = {
  ...defaultSchema,
  protocols: {
    ...(defaultSchema.protocols ?? {}),
    href: [...(defaultSchema.protocols?.href ?? []), CITATION_URL_SCHEME],
  },
};

export function citationUrlTransform(url: string): string {
  if (url.startsWith(`${CITATION_URL_SCHEME}:`)) return url;
  return defaultUrlTransform(url);
}
