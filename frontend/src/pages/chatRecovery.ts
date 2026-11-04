import type { ChatMessageItem, ChatSessionItem } from "../api/client";

/**
 * 断流后找回已生成的回答。
 *
 * 2026-11-04 排查：/chat 的「网络断开」几乎全部发生在 Cloudflare → 浏览器这一段
 * （宿主机 nginx 10-25 起 1,283 次 /api/chat/stream 全是 200、零 499；断开的那几次，
 * 后端都已生成完并存库，nginx 也把整段字节发了出去），大陆用户尤甚（电脑 4.8%、手机 8.8%）。
 * 答案其实在库里，只是没送到浏览器——所以断流后先回库里找，找到就显示，而不是报「请求失败」。
 *
 * 只对登录用户有效：游客不建会话、回答不落库。
 */

export interface RecoveryDeps {
  getSessions: () => Promise<ChatSessionItem[]>;
  /** 会话最新一页消息（按时间正序） */
  getLatestMessages: (sessionId: number) => Promise<ChatMessageItem[]>;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
}

export interface RecoveryQuery {
  question: string;
  /** 发送时已知的会话 id；新对话发出时还没有 id，为 null */
  sessionId: number | null;
  /** 发送时刻（epoch ms） */
  startedAt: number;
}

export interface RecoveryOptions {
  intervalMs?: number;
  /** 后端可能还在生成（推理模型实测最长约 3 分钟），所以要等一阵 */
  timeoutMs?: number;
  /** 服务器时钟（UTC 存库）与浏览器时钟的容差 */
  skewMs?: number;
}

/** 新对话的会话标题 = 问题前 50 字（services/chat.py `_resolve_session`）。 */
const TITLE_LEN = 50;

function createdAtMs(s: string | undefined): number {
  if (!s) return NaN;
  // 后端时间带时区（ISO 8601）；没带时按 UTC 解释，与库里一致
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s}Z`);
}

/** 在一组按时间正序的消息里，找「这个问题」在 since 之后的那一轮回答。 */
export function findAnswerInMessages(messages: ChatMessageItem[], question: string, since: number): boolean {
  const q = question.trim();
  for (let i = messages.length - 2; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "user" || m.content.trim() !== q) continue;
    const t = createdAtMs(m.created_at);
    if (Number.isFinite(t) && t < since) return false; // 更早的同一句问题，不算
    const next = messages[i + 1];
    return next.role === "assistant" && next.content.trim().length > 0;
  }
  return false;
}

/** 找到就返回回答所在的会话 id；超时返回 null。 */
export async function findSavedAnswer(
  query: RecoveryQuery,
  deps: RecoveryDeps,
  { intervalMs = 5_000, timeoutMs = 180_000, skewMs = 120_000 }: RecoveryOptions = {},
): Promise<number | null> {
  const since = query.startedAt - skewMs;
  const deadline = deps.now() + timeoutMs;
  let sessionId = query.sessionId;
  for (;;) {
    try {
      if (sessionId == null) {
        const title = query.question.trim().slice(0, TITLE_LEN);
        const hit = (await deps.getSessions()).find(
          (s) => (s.title ?? "").trim() === title && createdAtMs(s.created_at) >= since,
        );
        if (hit) sessionId = hit.id;
      }
      if (sessionId != null) {
        const messages = await deps.getLatestMessages(sessionId);
        if (findAnswerInMessages(messages, query.question, since)) return sessionId;
      }
    } catch {
      // 网络还没恢复就继续等，直到截止
    }
    if (deps.now() + intervalMs > deadline) return null;
    await deps.sleep(intervalMs);
  }
}
