import { describe, expect, it, vi, afterEach } from "vitest";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { api, isRetryableGetError } from "./client";

const cfg = (method: string, extra: Record<string, unknown> = {}) =>
  ({ method, url: "/chat/sessions/1/messages", headers: {}, ...extra }) as unknown as InternalAxiosRequestConfig;

describe("读取请求的网络重试规则", () => {
  it("GET 没收到响应（网络断）→ 重试；502/503/504 → 重试", () => {
    expect(isRetryableGetError(new AxiosError("Network Error", "ERR_NETWORK", cfg("get")))).toBe(true);
    const e503 = new AxiosError("x", "ERR_BAD_RESPONSE", cfg("get"), null, { status: 503 } as never);
    expect(isRetryableGetError(e503)).toBe(true);
  });

  it("POST、超时、4xx、已重试两次 → 不重试", () => {
    expect(isRetryableGetError(new AxiosError("Network Error", "ERR_NETWORK", cfg("post")))).toBe(false);
    expect(isRetryableGetError(new AxiosError("timeout", "ECONNABORTED", cfg("get")))).toBe(false);
    const e404 = new AxiosError("x", "ERR_BAD_REQUEST", cfg("get"), null, { status: 404 } as never);
    expect(isRetryableGetError(e404)).toBe(false);
    expect(isRetryableGetError(new AxiosError("Network Error", "ERR_NETWORK", cfg("get", { __retryCount: 2 })))).toBe(false);
  });
});

describe("拦截器真的会重试", () => {
  const original = api.defaults.adapter;
  afterEach(() => {
    api.defaults.adapter = original;
  });

  it("前两次网络断、第三次成功 → 调用方拿到数据，看不到错误", async () => {
    let calls = 0;
    const adapter: AxiosAdapter = async (config) => {
      calls += 1;
      if (calls < 3) throw new AxiosError("Network Error", "ERR_NETWORK", config);
      return { data: { ok: true }, status: 200, statusText: "OK", headers: {}, config };
    };
    api.defaults.adapter = adapter;
    const res = await api.get("/chat/sessions/1/messages");
    expect(res.data).toEqual({ ok: true });
    expect(calls).toBe(3);
  }, 8000);

  it("POST 网络断不重试（不能重复提交）", async () => {
    let calls = 0;
    api.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      calls += 1;
      throw new AxiosError("Network Error", "ERR_NETWORK", config);
    }) as AxiosAdapter;
    await expect(api.post("/chat/stream", {})).rejects.toBeTruthy();
    expect(calls).toBe(1);
  });
});
