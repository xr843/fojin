/**
 * Sanitize HTML highlights from Elasticsearch to prevent XSS.
 * Only allows safe formatting tags used for search highlight display.
 */

const ALLOWED_TAGS = ["em", "b", "strong", "mark"];
const TAG_RE = /<\/?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>/g;

/**
 * Strip all HTML tags except the allowed highlight tags.
 * This is a whitelist approach — anything not explicitly allowed is removed.
 */
export function sanitizeHighlight(html: string): string {
  return html.replace(TAG_RE, (match, tagName) => {
    if (ALLOWED_TAGS.includes(tagName.toLowerCase())) {
      return match;
    }
    return "";
  });
}
