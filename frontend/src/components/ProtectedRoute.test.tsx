import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { useAuthStore } from "../stores/authStore";
import ProtectedRoute from "./ProtectedRoute";

function renderWithRouter(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div data-testid="login-page">登录页</div>} />
        <Route path="/" element={<div data-testid="home-page">首页</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/profile" element={<div data-testid="profile-page">个人中心</div>} />
        </Route>
        <Route element={<ProtectedRoute requiredRole="admin" />}>
          <Route path="/admin" element={<div data-testid="admin-page">管理后台</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, user: null });
    sessionStorage.clear();
  });

  it("未登录时重定向到 /login", () => {
    renderWithRouter("/profile");

    expect(screen.getByTestId("login-page")).toBeInTheDocument();
    expect(screen.queryByTestId("profile-page")).not.toBeInTheDocument();
  });

  it("被弹去登录时把原目的地（含查询串）记进 returnTo", () => {
    // 承重条。LoginPage 的 consumeReturnTo() 一直在读这个键，但过去只有
    // ChatPage 那条 CTA 会写 —— 从这里被弹走的人登录完一律落回首页，得自己
    // 找回原来那一页。查询串必须带上：/profile?tab=api-key 少了参数就是另一页。
    renderWithRouter("/profile?tab=api-key");

    expect(screen.getByTestId("login-page")).toBeInTheDocument();
    expect(sessionStorage.getItem("fojin.login.returnTo")).toBe("/profile?tab=api-key");
  });

  it("已登录时渲染受保护页面", () => {
    useAuthStore.setState({
      token: "valid-token",
      user: {
        id: 1,
        username: "user1",
        email: "u@e.com",
        display_name: null,
        role: "user",
        is_active: true,
        created_at: "",
      },
    });

    renderWithRouter("/profile");

    expect(screen.getByTestId("profile-page")).toBeInTheDocument();
    expect(screen.queryByTestId("login-page")).not.toBeInTheDocument();
  });

  it("角色不匹配时重定向到首页", () => {
    useAuthStore.setState({
      token: "valid-token",
      user: {
        id: 1,
        username: "user1",
        email: "u@e.com",
        display_name: null,
        role: "user",
        is_active: true,
        created_at: "",
      },
    });

    renderWithRouter("/admin");

    expect(screen.getByTestId("home-page")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-page")).not.toBeInTheDocument();
    // 这一条不许写 returnTo：他已经登录了，权限也不会因为再登一次而变。
    // 写了就是让他登录完再撞一次同一堵墙。
    expect(sessionStorage.getItem("fojin.login.returnTo")).toBeNull();
  });

  it("admin 角色可以访问 admin 路由", () => {
    useAuthStore.setState({
      token: "admin-token",
      user: {
        id: 2,
        username: "admin",
        email: "admin@e.com",
        display_name: "管理员",
        role: "admin",
        is_active: true,
        created_at: "",
      },
    });

    renderWithRouter("/admin");

    expect(screen.getByTestId("admin-page")).toBeInTheDocument();
  });
});
