/**
 * 搜索页「问小津」深链。遵守 /chat 深链契约（见 ChatPage 的 autoSent effect）：
 * 裸 ?q= 只填不发；这里是用户显式点了按钮，所以带 context 或 send=1 落地即发。
 *
 * 像一段经文的查询（≥ PASSAGE_MIN_HAN 个汉字）——用户多半是在别处读到一句、
 * 来查出处与意思（/chat 18% 的提问就是贴原文）——包成经文引用发；
 * 短查询当术语问。
 */
export const PASSAGE_MIN_HAN = 5;

const HAN = /\p{Script=Han}/gu;

export function hanCount(s: string): number {
  return (s.match(HAN) ?? []).length;
}

export type AskKind = "passage" | "term";

export function askAiKind(query: string): AskKind | null {
  const q = query.trim();
  if (!q || hanCount(q) === 0) return null;
  return hanCount(q) >= PASSAGE_MIN_HAN ? "passage" : "term";
}

export function buildAskAiUrl(query: string, kind: AskKind, question: string): string {
  const p = new URLSearchParams();
  p.set("q", question);
  if (kind === "passage") p.set("context", query.trim());
  else p.set("send", "1");
  return `/chat?${p.toString()}`;
}
