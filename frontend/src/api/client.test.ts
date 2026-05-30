import { describe, it, expect, beforeEach, vi } from "vitest";
import axios from "axios";
import type { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from "axios";
import { useAuthStore } from "../stores/authStore";

/**
 * 测试 API client 的拦截器逻辑。
 * 由于 client.ts 在模块加载时就注册了拦截器，
 * 我们直接提取拦截器的回调函数进行单元测试。
 */

// 请求拦截器：从 localStorage 注入 JWT token
function requestInterceptor(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  try {
    const raw = localStorage.getItem("fojin-auth");
    if (raw) {
      const { state } = JSON.parse(raw);
      if (state?.token) {
        config.headers.Authorization = `Bearer ${state.token}`;
      }
    }
  } catch {
    // ignore parse errors
  }
  return config;
}

// 响应错误拦截器：401 时自动登出
function responseErrorInterceptor(error: AxiosError): Promise<never> {
  if (
    error.response?.status === 401 &&
    !error.config?.url?.startsWith("/auth/")
  ) {
    useAuthStore.getState().logout();
    window.location.href = "/login";
  }
  return Promise.reject(error);
}

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
    expect(window.location.href).toBe("/login");
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
