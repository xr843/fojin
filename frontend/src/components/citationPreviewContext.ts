import { createContext } from "react";
import type { ChatCheckedQuote, ChatSource } from "../api/client";

/**
 * What the inline-citation hover preview needs to know about the answer it sits
 * in. Provided per message by ChatPage's MessageBubble — the markdown `a`
 * renderer is shared by every answer, so the message must come from context, not
 * from the renderer's closure. Carrying the message's own fields (not its id)
 * also makes the mid-stream id swap (message_id event) irrelevant.
 */
export interface CitationPreviewData {
  sources: ChatSource[] | null | undefined;
  /** trust_status.checked_quotes — absent while streaming / for old answers. */
  checkedQuotes: ChatCheckedQuote[] | null | undefined;
}

export const CitationPreviewContext = createContext<CitationPreviewData | null>(null);
