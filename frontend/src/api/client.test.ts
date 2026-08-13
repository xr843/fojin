import { afterEach, describe, it, expect, beforeEach, vi } from "vitest";
import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from "axios";
import { useAuthStore } from "../stores/authStore";
import { api } from "./client";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";

/**
 * 测试 API client 的拦截器逻辑。
 *
 * 这两个拦截器过去是在本文件里**照抄一份**再测的。那等于在测复制品：改
 * client.ts 的真实现，这里一条都不会红 —— 2026-08-05 把 401 的硬跳转拿掉时，
 * 抄来的副本还在断言 `window.location.href === "/login"`，测试全绿。
 * 现在从 axios 实例上取真回调，测的才是线上跑的那份。
 */
type Handler<T> = { fulfilled?: T; rejected?: T };
function realInterceptor<T>(mgr: unknown, kind: "fulfilled" | "rejected"): T {
  const handlers = (mgr as { handlers: Handler<T>[] }).handlers;
  const fn = handlers.find((h) => h[kind])?.[kind];
  if (!fn) throw new Error(`client.ts 没有注册 ${kind} 拦截器`);
  return fn;
}

const requestInterceptor = realInterceptor<
  (c: InternalAxiosRequestConfig) => InternalAxiosRequestConfig
>(api.interceptors.request, "fulfilled");

const responseErrorInterceptor = realInterceptor<(e: AxiosError) => Promise<never>>(
  api.interceptors.response,
  "rejected",
);

function makeConfig(url: string = "/test"): InternalAxiosRequestConfig {
  return {
    url,
    headers: new axios.AxiosHeaders(),
  } as InternalAxiosRequestConfig;
}

function makeAxiosError(status: number, url: string = "/test"): AxiosError {
  const config = makeConfig(url);
  return {
    isAxiosError: true,
    name: "AxiosError",
    message: "Request failed",
    config,
    response: {
      status,
      statusText: status === 401 ? "Unauthorized" : "Error",
      data: {},
      headers: {},
      config,
    } as AxiosResponse,
    toJSON: () => ({}),
  } as AxiosError;
}

describe("请求拦截器 - Token 注入", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("localStorage 中有 token 时注入 Authorization header", () => {
    localStorage.setItem(
      "fojin-auth",
      JSON.stringify({ state: { token: "my-jwt-token", user: null } }),
    );

    const config = makeConfig();
    const result = requestInterceptor(config);
    expect(result.headers.Authorization).toBe("Bearer my-jwt-token");
  });

  it("localStorage 为空时不注入 header", () => {
    const config = makeConfig();
    const result = requestInterceptor(config);
    expect(result.headers.Authorization).toBeUndefined();
  });

  it("localStorage 中 token 为 null 时不注入 header", () => {
    localStorage.setItem(
      "fojin-auth",
      JSON.stringify({ state: { token: null, user: null } }),
    );

    const config = makeConfig();
    const result = requestInterceptor(config);
    expect(result.headers.Authorization).toBeUndefined();
  });

  it("localStorage 内容格式错误时不抛异常", () => {
    localStorage.setItem("fojin-auth", "invalid json {{{");

    const config = makeConfig();
    const result = requestInterceptor(config);
    expect(result.headers.Authorization).toBeUndefined();
  });
});

describe("响应拦截器 - 401 自动登出", () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: "existing-token",
      user: {
        id: 1,
        username: "test",
        email: "t@t.com",
        display_name: null,
        role: "user",
        is_active: true,
        created_at: "",
      },
    });
    // mock window.location.href
    Object.defineProperty(window, "location", {
      value: { href: "/" },
      writable: true,
    });
  });

  it("非 /auth/ 路径收到 401 时触发登出", async () => {
    const error = makeAxiosError(401, "/search");

    await expect(responseErrorInterceptor(error)).rejects.toBeTruthy();

    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("401 只清身份，不把用户从当前页面踢走", async () => {
    // 承重条。这里曾经跟着一句 window.location.href = "/login"，而 JWT 只活
    // 8 小时、没有 refresh token，NotificationBell 又在每次路由变化都打一次
    // /notifications/unread-count —— 隔夜回访的用户于是在首屏还没画出来时就被
    // 一个后台轮询打出的 401 硬跳走，目的地当场丢失（这条路径不写 returnTo）。
    // Umami 30 天实测：282 个会话的第一个 pageview 就是 /login。
    //
    // 需要登录的路由由 ProtectedRoute 自己跳（它会写 returnTo），公开页应当
    // 原地降级成游客继续看，所以这里必须一动不动。
    const error = makeAxiosError(401, "/notifications/unread-count");

    await expect(responseErrorInterceptor(error)).rejects.toBeTruthy();

    expect(useAuthStore.getState().user).toBeNull();     // 身份该清还是要清
    expect(window.location.href).toBe("/");              // 但页面不许动
  });

  it("/auth/ 路径收到 401 时不触发登出", async () => {
    const error = makeAxiosError(401, "/auth/login");

    await expect(responseErrorInterceptor(error)).rejects.toBeTruthy();

    // 不应该登出
    expect(useAuthStore.getState().token).toBe("existing-token");
  });

  it("403 错误不触发登出", async () => {
    const error = makeAxiosError(403, "/admin/users");

    await expect(responseErrorInterceptor(error)).rejects.toBeTruthy();

    expect(useAuthStore.getState().token).toBe("existing-token");
  });

  it("500 错误不触发登出", async () => {
    const error = makeAxiosError(500, "/search");

    await expect(responseErrorInterceptor(error)).rejects.toBeTruthy();

    expect(useAuthStore.getState().token).toBe("existing-token");
  });

  it("错误始终被 reject 传递", async () => {
    const error = makeAxiosError(401, "/search");

    await expect(responseErrorInterceptor(error)).rejects.toEqual(error);
  });
});

describe("axios 实例配置", () => {
  it("默认导出是 axios 实例", async () => {
    // 动态导入以验证模块导出
    const clientModule = await import("./client");
    expect(clientModule.default).toBeDefined();
    expect(clientModule.default.defaults.baseURL).toBe("/api");
  });

  it("超时设置为 15 秒", async () => {
    const clientModule = await import("./client");
    expect(clientModule.default.defaults.timeout).toBe(15000);
  });
});

describe("getWorkByText", () => {
  it("文本未挂作品时后端 404 → 吞掉返回 null", async () => {
    const { api, getWorkByText } = await import("./client");
    const spy = vi
      .spyOn(api, "get")
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 404 } });
    await expect(getWorkByText(123)).resolves.toBeNull();
    spy.mockRestore();
  });

  it("非 404 错误照常抛出", async () => {
    const { api, getWorkByText } = await import("./client");
    const err = { isAxiosError: true, response: { status: 500 } };
    const spy = vi.spyOn(api, "get").mockRejectedValueOnce(err);
    await expect(getWorkByText(123)).rejects.toBe(err);
    spy.mockRestore();
  });
});

class MockStreamXHR {
  static instances: MockStreamXHR[] = [];

  onprogress: (() => void) | null = null;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  responseText = "";
  status = 0;
  timeout = 0;

  open = vi.fn();
  setRequestHeader = vi.fn();
  send = vi.fn();
  abort = vi.fn();

  constructor() {
    MockStreamXHR.instances.push(this);
  }
}

describe("sendChatMessageStream", () => {
  beforeEach(async () => {
    MockStreamXHR.instances = [];
    vi.stubGlobal("XMLHttpRequest", MockStreamXHR);
    i18n.addResourceBundle("en", "translation", enTranslation, true, true);
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    vi.unstubAllGlobals();
    await i18n.changeLanguage("zh");
  });

  it("uses the active UI language for client-side network errors", async () => {
    const { sendChatMessageStream } = await import("./client");
    const callbacks = {
      onToken: vi.fn(),
      onSources: vi.fn(),
      onSessionId: vi.fn(),
      onError: vi.fn(),
      onDone: vi.fn(),
    };

    const promise = sendChatMessageStream("hello", undefined, null, callbacks);
    expect(MockStreamXHR.instances).toHaveLength(1);

    MockStreamXHR.instances[0].onerror?.();
    await promise;

    expect(callbacks.onError).toHaveBeenCalledWith("Network error. Please try again later.", "network");
    expect(callbacks.onDone).toHaveBeenCalledTimes(1);
  });

  it("reasoning 帧的 text 要透传给 onReasoning —— 等待区「思考过程片段」的原料", async () => {
    // ⚠️ 这是全站唯一走真实 processChunk 的 reasoning 用例：页面级测试全部
    // mock 掉 sendChatMessageStream，测不到这一层。此前这里重建对象只取
    // chars，text 在此处被静默丢弃的话，上层测试照样全绿。
    const { sendChatMessageStream } = await import("./client");
    const onReasoning = vi.fn();
    const callbacks = {
      onToken: vi.fn(), onSources: vi.fn(), onSessionId: vi.fn(),
      onError: vi.fn(), onDone: vi.fn(), onReasoning,
    };

    const promise = sendChatMessageStream("hello", undefined, null, callbacks);
    const xhr = MockStreamXHR.instances[0];
    xhr.responseText =
      'data: {"type": "reasoning", "chars": 12, "text": "先看《心經》這一段"}\n\n' +
      'data: {"type": "done"}\n\n';
    xhr.onprogress?.();
    await promise;

    expect(onReasoning).toHaveBeenCalledWith({ chars: 12, text: "先看《心經》這一段" });
  });

  it("流上收到 401：清身份 + 报出原因，但不硬跳登录页丢掉整段对话", async () => {
    // 承重条。这里曾经是 window.location.href = "/login" 且 return（连 onDone
    // 都不调，Promise 永不 settle —— 因为反正整页要重载）。代价是用户刚打完的
    // 那个问题和整段对话一起消失，而 /chat 本来就是公开页、游客也能问。
    Object.defineProperty(window, "location", { value: { href: "/chat" }, writable: true });
    useAuthStore.setState({ token: "expired", user: null });

    const { sendChatMessageStream } = await import("./client");
    const callbacks = {
      onToken: vi.fn(), onSources: vi.fn(), onSessionId: vi.fn(),
      onError: vi.fn(), onDone: vi.fn(),
    };

    const promise = sendChatMessageStream("hello", undefined, null, callbacks);
    MockStreamXHR.instances[0].status = 401;
    MockStreamXHR.instances[0].onload?.();
    await promise;   // 必须能 settle —— 旧实现在这里永远挂着

    expect(useAuthStore.getState().token).toBeNull();
    expect(window.location.href).toBe("/chat");
    expect(callbacks.onError).toHaveBeenCalledWith(expect.any(String), "unauthorized");
    expect(callbacks.onDone).toHaveBeenCalledTimes(1);
  });
});
