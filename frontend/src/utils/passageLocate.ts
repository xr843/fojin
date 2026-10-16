import type { ChatRetrieval, ChatSource } from "../api/client";

/** 贴原文定位卡片的数据：sources 里 located=true 的那条，或流式中 retrieved.located。 */
export interface LocateInfo {
  textId: number;
  juanNum: number;
  chunkIndex: number | null;
  title: string;
  window: string;
  /** 全藏含这段文字的典籍数（含本书）；0 = 未知。 */
  texts: number;
}

/** 两处字段同义；sources 优先（它是入库、刷新后读回的那份）。 */
export function locateInfoFrom(
  sources: ChatSource[] | null | undefined,
  retrieval: ChatRetrieval | null | undefined,
): LocateInfo | null {
  const s = sources?.find((x) => x.located);
  if (s) {
    return {
      textId: s.text_id,
      juanNum: s.juan_num,
      chunkIndex: s.chunk_index ?? null,
      title: s.title_zh ?? "",
      window: s.located_window ?? "",
      texts: s.located_texts ?? 0,
    };
  }
  const r = retrieval?.located;
  if (r) {
    return {
      textId: r.text_id,
      juanNum: r.juan_num,
      chunkIndex: r.chunk_index ?? null,
      title: r.title_zh ?? "",
      window: r.window ?? "",
      texts: r.texts ?? 0,
    };
  }
  return null;
}

/** 卡片上原文片段的展示上限（字）。完整窗口（≤200 字）仍交给抽屉做高亮。 */
export const LOCATE_SNIPPET_MAX = 40;

/** 按字符（不是 UTF-16 单元）截断，CJK 扩展区的字不会被劈成半个。 */
export function snippetOf(window: string, max = LOCATE_SNIPPET_MAX): string {
  const chars = Array.from(window);
  return chars.length > max ? `${chars.slice(0, max).join("")}…` : window;
}
