import { getChatSessionMessages } from "../api/client";

/** 收到的会话数据不完整（被截断、拿到的不是 JSON）时抛出，交给 fetchSessionMessagesWithRetry 重试。 */
export class SessionBodyError extends Error {}

/**
 * 读一个会话的消息。网络层的失败 api 客户端已自动重试（见 isRetryableGetError）；这里再兜住
 * 「200 但数据不完整」——大陆线路偶有响应体被截断，axios 解析不了 JSON 会把原文字符串当 data
 * 交回来，随后 data.messages.length 抛错，界面上同样是「加载会话失败」。
 */
export async function fetchSessionMessagesWithRetry(sid: number) {
  for (let attempt = 0; ; attempt++) {
    const data = await getChatSessionMessages(sid, 1, 50);
    if (data && Array.isArray(data.messages) && typeof data.total === "number") {
      if (attempt > 0 && typeof umami !== "undefined") umami.track("chat_session_load_body_retry_ok", { attempts: attempt });
      return data;
    }
    if (attempt >= 2) throw new SessionBodyError("incomplete session payload");
    await new Promise((r) => setTimeout(r, 600 * (attempt + 1)));
  }
}

/** 加载会话失败的类别，给埋点与提示文案用。 */
export function sessionLoadFailureKind(err: unknown): string {
  if (err instanceof SessionBodyError) return "bad_body";
  const e = err as { response?: { status?: number }; code?: string } | undefined;
  if (e?.response?.status) return `http_${e.response.status}`;
  if (e?.code === "ECONNABORTED" || e?.code === "ETIMEDOUT") return "timeout";
  return "network";
}
