import { describe, expect, it, vi, beforeEach } from "vitest";

const getChatSessionMessages = vi.fn();
vi.mock("../api/client", () => ({ getChatSessionMessages: (...a: unknown[]) => getChatSessionMessages(...a) }));

import { fetchSessionMessagesWithRetry, sessionLoadFailureKind, SessionBodyError } from "./sessionLoad";

const ok = { total: 2, page: 1, size: 50, messages: [] };

describe("加载会话：数据不完整时重试", () => {
  beforeEach(() => getChatSessionMessages.mockReset());

  it("第一次拿到截断的字符串、第二次完整 → 返回完整数据", async () => {
    getChatSessionMessages.mockResolvedValueOnce('{"total":2,"messa').mockResolvedValueOnce(ok);
    await expect(fetchSessionMessagesWithRetry(1)).resolves.toEqual(ok);
    expect(getChatSessionMessages).toHaveBeenCalledTimes(2);
  });

  it("三次都不完整 → 抛 SessionBodyError，类别 bad_body", async () => {
    getChatSessionMessages.mockResolvedValue("<html>");
    const err = await fetchSessionMessagesWithRetry(1).catch((e) => e);
    expect(err).toBeInstanceOf(SessionBodyError);
    expect(sessionLoadFailureKind(err)).toBe("bad_body");
    expect(getChatSessionMessages).toHaveBeenCalledTimes(3);
  }, 8000);

  it("失败类别：HTTP 状态 / 超时 / 网络", () => {
    expect(sessionLoadFailureKind({ response: { status: 404 } })).toBe("http_404");
    expect(sessionLoadFailureKind({ code: "ECONNABORTED" })).toBe("timeout");
    expect(sessionLoadFailureKind(new Error("Network Error"))).toBe("network");
  });
});
