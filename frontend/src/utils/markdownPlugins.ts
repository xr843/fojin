import type { Options } from "react-markdown";
import remarkCjkFriendly from "remark-cjk-friendly";
import remarkGfm from "remark-gfm";

/**
 * Remark plugins for every place that renders model-written Markdown.
 *
 * CommonMark's emphasis rules treat CJK punctuation like ASCII punctuation, so a
 * closing `**` preceded by 。」 and followed by a Han character (「…本具的清净。**如来藏…」)
 * is not "right-flanking" and never closes — the reader sees raw asterisks. In
 * prod that hit ~40% of /chat answers over 30 days (506/1258, 2026-10-16).
 * remark-cjk-friendly relaxes exactly that rule for CJK and changes nothing else,
 * so citation markers 【《经名》第N卷】 and links parse as before.
 */
export const MARKDOWN_REMARK_PLUGINS: NonNullable<Options["remarkPlugins"]> = [remarkGfm, remarkCjkFriendly];
