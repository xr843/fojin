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
  });

  it("未登录时重定向到 /login", () => {
    renderWithRouter("/profile");

    expect(screen.getByTestId("login-page")).toBeInTheDocument();
    expect(screen.queryByTestId("profile-page")).not.toBeInTheDocument();
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
