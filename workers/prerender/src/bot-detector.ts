/**
 * Known search engine and social media crawler User-Agent patterns.
 *
 * We match specific bot tokens first, then fall back to generic patterns
 * ("bot", "crawler", "spider") — but only when preceded by a word boundary
 * so that normal browser UAs like "Cubot" are not falsely matched.
 */

const BOT_TOKENS: string[] = [
  // Google
  "googlebot",
  "google-inspectiontool",
  "storebot-google",
  "googleother",
  "google-extended",
  // Bing / Microsoft
  "bingbot",
  "msnbot",
  "bingpreview",
  // Baidu
  "baiduspider",
  // Yandex
  "yandexbot",
  "yandexaccessibilitybot",
  // DuckDuckGo
  "duckduckbot",
  // Sogou
  "sogou",
  // Yahoo
  "slurp",
  // Social media
  "facebookexternalhit",
  "facebookcatalog",
  "twitterbot",
  "linkedinbot",
  // Apple
  "applebot",
  // Other notable crawlers
  "petalbot",
  "semrushbot",
  "ahrefsbot",
  "dotbot",
  "rogerbot",
];

/**
 * Generic patterns that indicate a crawler, anchored to word boundaries
 * to avoid false positives on normal browser UA strings.
 */
const GENERIC_RE = /(?:^|[\s/;(])(?:bot|crawler|spider)(?:[\s/;)]|$)/i;

export function isBot(userAgent: string): boolean {
  if (!userAgent) return false;
  const ua = userAgent.toLowerCase();

  for (const token of BOT_TOKENS) {
    if (ua.includes(token)) return true;
  }

  return GENERIC_RE.test(userAgent);
}
