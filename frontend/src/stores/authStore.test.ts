import { describe, it, expect, beforeEach } from "vitest";
import { markSessionExpired, sessionExpired, useAuthStore, type UserProfile } from "./authStore";

const mockUser: UserProfile = {
  id: 1,
  username: "testuser",
  email: "test@example.com",
  display_name: "测试用户",
  role: "user",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
};

describe("authStore", () => {
  beforeEach(() => {
    // 每次测试前重置 store 状态
    useAuthStore.setState({ token: null, user: null });
    localStorage.clear();
  });

  it("初始状态为未登录", () => {
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it("setAuth 设置 token 和用户信息", () => {
    useAuthStore.getState().setAuth("test-token-123", mockUser);

    const state = useAuthStore.getState();
    expect(state.token).toBe("test-token-123");
    expect(state.user).toEqual(mockUser);
  });

  it("logout 清除认证信息", () => {
    useAuthStore.getState().setAuth("test-token-123", mockUser);
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it("persist 中间件将状态写入 localStorage", () => {
    useAuthStore.getState().setAuth("persist-token", mockUser);

    const raw = localStorage.getItem("fojin-auth");
    expect(raw).toBeTruthy();

    const parsed = JSON.parse(raw!);
    expect(parsed.state.token).toBe("persist-token");
    expect(parsed.state.user.username).toBe("testuser");
  });

  it("logout 后 localStorage 中 token 被清除", () => {
    useAuthStore.getState().setAuth("some-token", mockUser);
    useAuthStore.getState().logout();

    const raw = localStorage.getItem("fojin-auth");
    expect(raw).toBeTruthy();

    const parsed = JSON.parse(raw!);
    expect(parsed.state.token).toBeNull();
    expect(parsed.state.user).toBeNull();
  });

  it("可以区分不同角色", () => {
    const adminUser: UserProfile = { ...mockUser, role: "admin" };
    useAuthStore.getState().setAuth("admin-token", adminUser);

    expect(useAuthStore.getState().user?.role).toBe("admin");
  });
});

// ── 「登录态是自己死的」这个事实必须活过 logout ────────────────────────
//
// 401 拦截器的处理是 logout()，而 logout() 会把 user 清空 —— 此后
// user==null 与「从没登录过」完全一样。实测正是如此：手工把 token 改坏后
// 进 /chat，两条横幅一条都不出现，因为 user 已经被抹了。所以到期这件事得
// 单独留一个标记，否则页面没法告诉用户"你现在是游客身份在提问"。

describe("会话过期标记", () => {
  beforeEach(() => {
    sessionStorage.clear();
    useAuthStore.setState({ token: null, user: null });
  });

  it("置位后可读到", () => {
    expect(sessionExpired()).toBe(false);
    markSessionExpired();
    expect(sessionExpired()).toBe(true);
  });

  it("承重点: 重新登录会清掉标记——否则修好了提示还在", () => {
    markSessionExpired();
    useAuthStore.getState().setAuth("fresh-token", mockUser);
    expect(sessionExpired()).toBe(false);
  });

  it("承重点: 主动登出不算过期——它清标记，只有 401 那条路才置位", () => {
    useAuthStore.getState().setAuth("t", mockUser);
    markSessionExpired();
    useAuthStore.getState().logout();
    expect(sessionExpired()).toBe(false);
  });

  it("顺序敏感: 401 路径必须先 logout 再置位，反过来会被自己清掉", () => {
    // 复现 client.ts 拦截器里的真实调用顺序。
    useAuthStore.getState().setAuth("dead-token", mockUser);
    useAuthStore.getState().logout();
    markSessionExpired();
    expect(sessionExpired()).toBe(true);
    expect(useAuthStore.getState().user).toBeNull();
  });
});
