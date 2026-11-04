import { describe, expect, it, vi } from "vitest";
import type { ChatMessageItem, ChatSessionItem } from "../api/client";
import type { ChatSessionId } from "../types/branded";
import { findAnswerInMessages, findSavedAnswer, type RecoveryDeps } from "./chatRecovery";

const T0 = Date.parse("2026-11-04T00:53:53Z");
const iso = (ms: number) => new Date(ms).toISOString();

function msg(id: number, role: string, content: string, at: number): ChatMessageItem {
  return { id, role, content, sources: null, created_at: iso(at) };
}

/** 假时钟：sleep 推进时间，不真等。 */
function fakeDeps(over: Partial<RecoveryDeps>): RecoveryDeps & { clock: { t: number } } {
  const clock = { t: T0 };
  return {
    clock,
    getSessions: vi.fn(async () => []),
    getLatestMessages: vi.fn(async () => []),
    sleep: vi.fn(async (ms: number) => { clock.t += ms; }),
    now: () => clock.t,
    ...over,
  };
}

describe("findAnswerInMessages", () => {
  it("找到这个问题之后紧跟的回答", () => {
    const ms = [msg(1, "user", "四念处是哪四个？", T0 + 1000), msg(2, "assistant", "身、受、心、法", T0 + 30_000)];
    expect(findAnswerInMessages(ms, "四念处是哪四个？", T0 - 1000)).toBe(true);
  });

  it("只有更早问过的同一句（上一次的回答）不算", () => {
    const ms = [msg(1, "user", "四念处是哪四个？", T0 - 600_000), msg(2, "assistant", "旧回答", T0 - 590_000)];
    expect(findAnswerInMessages(ms, "四念处是哪四个？", T0 - 120_000)).toBe(false);
  });

  it("问题已存、回答还没存（后端仍在生成）时不算", () => {
    const ms = [msg(1, "user", "四念处是哪四个？", T0 + 1000)];
    expect(findAnswerInMessages(ms, "四念处是哪四个？", T0)).toBe(false);
  });
});

describe("findSavedAnswer", () => {
  it("已知会话：后端第三轮才存好，轮询到就返回会话 id", async () => {
    let calls = 0;
    const deps = fakeDeps({
      getLatestMessages: vi.fn(async () => {
        calls += 1;
        return calls < 3
          ? [msg(1, "user", "问", T0 + 1000)]
          : [msg(1, "user", "问", T0 + 1000), msg(2, "assistant", "答", T0 + 128_000)];
      }),
    });
    await expect(findSavedAnswer({ question: "问", sessionId: 3772, startedAt: T0 }, deps)).resolves.toBe(3772);
    expect(deps.getSessions).not.toHaveBeenCalled();
  });

  it("新对话：按标题（问题前 50 字）和创建时间找出刚建的会话", async () => {
    const q = "弘一法师如何从艺术家到律师？".repeat(5); // 超过 50 字
    const sessions: ChatSessionItem[] = [
      { id: 1 as ChatSessionId, title: q.slice(0, 50), created_at: iso(T0 - 86_400_000) }, // 昨天同题，不算
      { id: 9 as ChatSessionId, title: q.slice(0, 50), created_at: iso(T0 + 500) },
    ];
    const deps = fakeDeps({
      getSessions: vi.fn(async () => sessions),
      getLatestMessages: vi.fn(async (sid: number) =>
        sid === 9 ? [msg(5, "user", q, T0 + 600), msg(6, "assistant", "答", T0 + 20_000)] : [],
      ),
    });
    await expect(findSavedAnswer({ question: q, sessionId: null, startedAt: T0 }, deps)).resolves.toBe(9);
  });

  it("一直找不到就在截止时间后返回 null；请求出错也继续等", async () => {
    const deps = fakeDeps({ getLatestMessages: vi.fn(async () => { throw new Error("offline"); }) });
    await expect(
      findSavedAnswer({ question: "问", sessionId: 1, startedAt: T0 }, deps, { intervalMs: 5_000, timeoutMs: 30_000 }),
    ).resolves.toBeNull();
    expect(deps.getLatestMessages).toHaveBeenCalledTimes(7); // t=0,5,…,30s
  });
});
