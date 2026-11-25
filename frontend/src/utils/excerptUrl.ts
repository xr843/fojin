import type { ExcerptItem } from "../api/client";
import { lineLevelSupported } from "./cbetaCitation";

/** 回到原文：行号可靠的藏带到那一行（anchor=p行号），其余只带到卷。与阅读页「复制链接」同一规则。 */
export function excerptReaderUrl(e: Pick<ExcerptItem, "text_id" | "juan_num" | "line_ref" | "cbeta_id">): string {
  const params = new URLSearchParams({ juan: String(e.juan_num) });
  if (e.line_ref && lineLevelSupported(e.cbeta_id)) params.set("anchor", `p${e.line_ref}`);
  return `/texts/${e.text_id}/read?${params.toString()}`;
}
