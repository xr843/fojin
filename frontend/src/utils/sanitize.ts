/**
 * Sanitize HTML highlights from Elasticsearch to prevent XSS.
 * Uses DOMPurify for robust sanitization instead of regex-based stripping.
 */

import DOMPurify from "dompurify";

const ALLOWED_TAGS = ["em", "b", "strong", "mark"];

/**
 * Strip all HTML tags except the allowed highlight tags.
 * Attributes are stripped from all tags to prevent event-handler injection.
 */
export function sanitizeHighlight(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: [],
  });
}

/**
 * Escape a plain-text string for safe insertion into innerHTML.
 * Use this when the input should never contain HTML (e.g., API data fields).
 */
export function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
