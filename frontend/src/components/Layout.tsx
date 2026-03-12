import { useState, useEffect } from "react";
import { Layout as AntLayout, Typography, Button, Dropdown, Space, Drawer, Modal, Badge } from "antd";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import {
  UserOutlined,
  LogoutOutlined,
  HeartOutlined,
  LoginOutlined,
  ApartmentOutlined,
  DatabaseOutlined,
  BookOutlined,
  MenuOutlined,
  SettingOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { useAuthStore } from "../stores/authStore";
import { getPendingSuggestionCount } from "../api/client";

const { Header, Content, Footer } = AntLayout;

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const isHome = location.pathname === "/";
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleLogout = () => {
    Modal.confirm({
      title: "确认退出",
      content: "确定要退出登录吗？",
      okText: "退出",
      cancelText: "取消",
      onOk: () => {
        logout();
        navigate("/");
      },
    });
  };

  /* 古典配色 */
  const ink = "var(--fj-ink)";
  const inkMuted = "var(--fj-ink-muted)";
  const accent = "var(--fj-accent)";
  const pageBg = "var(--fj-bg)";
  const headerBg = pageBg;

  const [pendingCount, setPendingCount] = useState(0);
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!isAdmin) return;
    getPendingSuggestionCount().then(setPendingCount).catch(() => {});
  }, [isAdmin, location.pathname]);

  const navItems = [
    { icon: <DatabaseOutlined />, label: "数据源", path: "/sources" },
    { icon: <BookOutlined />, label: "经典专题", path: "/collections" },
    { icon: <ApartmentOutlined />, label: "知识图谱", path: "/kg" },
    { icon: <RobotOutlined />, label: "AI 问答", path: "/chat" },
    ...(isAdmin
      ? [
          {
            icon: <Badge count={pendingCount} size="small" offset={[4, -2]}><SettingOutlined /></Badge>,
            label: "管理",
            path: "/admin/suggestions",
          },
        ]
      : []),
  ];

  return (
    <AntLayout style={{ minHeight: "100vh", background: pageBg }}>
      <a
        href="#main-content"
        style={{
          position: "absolute",
          left: -9999,
          top: "auto",
          width: 1,
          height: 1,
          overflow: "hidden",
          zIndex: 100,
        }}
        onFocus={(e) => {
          e.currentTarget.style.position = "fixed";
          e.currentTarget.style.left = "8px";
          e.currentTarget.style.top = "8px";
          e.currentTarget.style.width = "auto";
          e.currentTarget.style.height = "auto";
          e.currentTarget.style.overflow = "visible";
          e.currentTarget.style.background = "#fff";
          e.currentTarget.style.padding = "8px 16px";
          e.currentTarget.style.borderRadius = "4px";
          e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.15)";
        }}
        onBlur={(e) => {
          e.currentTarget.style.position = "absolute";
          e.currentTarget.style.left = "-9999px";
          e.currentTarget.style.width = "1px";
          e.currentTarget.style.height = "1px";
          e.currentTarget.style.overflow = "hidden";
        }}
      >
        跳至主要内容
      </a>
      <Header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: headerBg,
          backdropFilter: isHome ? "blur(12px)" : undefined,
          padding: "0 32px",
          height: 52,
          lineHeight: "52px",
          borderBottom: `1px solid rgba(217,208,193,0.5)`,
          position: isHome ? "sticky" : undefined,
          top: 0,
          zIndex: 10,
        }}
      >
        <Space size="large">
          <Typography.Title
            level={5}
            style={{
              color: ink,
              margin: 0,
              letterSpacing: 4,
              cursor: "pointer",
              fontWeight: 400,
              fontSize: 22,
              fontFamily: '"Ma Shan Zheng", "Noto Serif SC", serif',
            }}
            onClick={() => navigate("/")}
          >
            佛津
          </Typography.Title>
          <div className="nav-desktop">
            {navItems.map((item) => (
              <Button
                key={item.path}
                type="text"
                icon={item.icon}
                style={{
                  color: inkMuted,
                  fontSize: 13,
                  fontWeight: 400,
                  fontFamily: '"Noto Serif SC", serif',
                }}
                onClick={() => navigate(item.path)}
              >
                {item.label}
              </Button>
            ))}
          </div>
          <Button
            className="nav-mobile-trigger"
            type="text"
            icon={<MenuOutlined />}
            onClick={() => setDrawerOpen(true)}
            style={{ color: inkMuted }}
            aria-label="打开导航菜单"
          />
        </Space>
        <Space>
          {user ? (
            <Dropdown
              menu={{
                items: [
                  {
                    key: "profile",
                    icon: <UserOutlined />,
                    label: "个人中心",
                    onClick: () => navigate("/profile"),
                  },
                  {
                    key: "bookmarks",
                    icon: <HeartOutlined />,
                    label: "我的收藏",
                    onClick: () => navigate("/profile"),
                  },
                  { type: "divider" },
                  {
                    key: "logout",
                    icon: <LogoutOutlined />,
                    label: "退出登录",
                    onClick: handleLogout,
                  },
                ],
              }}
            >
              <Button
                type="text"
                icon={<UserOutlined />}
                style={{ color: inkMuted, fontSize: 13 }}
              >
                {user.display_name || user.username}
              </Button>
            </Dropdown>
          ) : (
            <Button
              type="text"
              icon={<LoginOutlined />}
              style={{
                color: "#fff",
                background: accent,
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 400,
                height: 30,
                padding: "0 16px",
                fontFamily: '"Noto Serif SC", serif',
              }}
              onClick={() => navigate("/login")}
            >
              登录
            </Button>
          )}
        </Space>
      </Header>
      <Content id="main-content" style={{ padding: isHome ? 0 : "24px 32px", flex: 1 }}>
        <Outlet />
      </Content>
      <Footer
        style={{
          textAlign: "center",
          fontSize: 12,
          fontFamily: '"Noto Serif SC", serif',
          color: inkMuted,
          background: pageBg,
          borderTop: "1px solid rgba(217,208,193,0.5)",
          padding: "16px 32px",
        }}
      >
        佛津 FoJin &copy; 2026 — 全球佛教古籍数字资源聚合平台
      </Footer>
      <Drawer
        title="导航"
        placement="left"
        width={240}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          {navItems.map((item) => (
            <Button
              key={item.path}
              type="text"
              icon={item.icon}
              block
              style={{ textAlign: "left", color: inkMuted }}
              onClick={() => { navigate(item.path); setDrawerOpen(false); }}
            >
              {item.label}
            </Button>
          ))}
        </Space>
      </Drawer>
    </AntLayout>
  );
}
