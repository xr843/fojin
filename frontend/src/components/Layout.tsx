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
  GithubOutlined,
  GlobalOutlined,
  FieldTimeOutlined,
  BarChartOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../stores/authStore";
import { getPendingSuggestionCount } from "../api/client";

const { Header, Content, Footer } = AntLayout;

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const { t, i18n } = useTranslation();
  const isHome = location.pathname === "/";
  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleLogout = () => {
    Modal.confirm({
      title: t("auth.logout_confirm_title"),
      content: t("auth.logout_confirm_content"),
      okText: t("auth.logout_ok"),
      cancelText: t("auth.cancel"),
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
    { icon: <DatabaseOutlined />, label: t("nav.sources"), path: "/sources" },
    { icon: <BookOutlined />, label: t("nav.collections"), path: "/collections" },
    { icon: <ApartmentOutlined />, label: t("nav.kg"), path: "/kg" },
    { icon: <FieldTimeOutlined />, label: t("nav.timeline"), path: "/timeline" },
    { icon: <BarChartOutlined />, label: t("nav.dashboard"), path: "/dashboard" },
    { icon: <RobotOutlined />, label: t("nav.chat"), path: "/chat" },
    ...(isAdmin
      ? [
          {
            icon: <Badge count={pendingCount} size="small" offset={[4, -2]}><SettingOutlined /></Badge>,
            label: t("nav.admin"),
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
        {t("nav.skip_to_content")}
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
            aria-label={t("nav.open_menu")}
          />
        </Space>
        <Space>
          <Dropdown
            menu={{
              items: [
                { key: "zh", label: "中文" },
                { key: "en", label: "English" },
                { key: "ja", label: "日本語" },
                { key: "ko", label: "한국어" },
                { key: "th", label: "ไทย" },
                { key: "vi", label: "Tiếng Việt" },
                { key: "si", label: "සිංහල" },
                { key: "my", label: "မြန်မာ" },
              ],
              onClick: ({ key }) => i18n.changeLanguage(key),
              selectedKeys: [i18n.resolvedLanguage ?? i18n.language],
            }}
          >
            <Button type="text" icon={<GlobalOutlined />} style={{ color: inkMuted, fontSize: 13 }}>
              {t(`language.${i18n.resolvedLanguage ?? i18n.language}`)}
            </Button>
          </Dropdown>
          {user ? (
            <Dropdown
              menu={{
                items: [
                  {
                    key: "profile",
                    icon: <UserOutlined />,
                    label: t("auth.profile"),
                    onClick: () => navigate("/profile"),
                  },
                  {
                    key: "bookmarks",
                    icon: <HeartOutlined />,
                    label: t("auth.bookmarks"),
                    onClick: () => navigate("/profile"),
                  },
                  { type: "divider" },
                  {
                    key: "logout",
                    icon: <LogoutOutlined />,
                    label: t("auth.logout"),
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
              {t("auth.login")}
            </Button>
          )}
        </Space>
      </Header>
      <Content id="main-content" style={{ padding: isHome ? 0 : undefined, flex: 1 }} className={isHome ? undefined : "layout-content-inner"}>
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
        {t("footer.copyright")}
        <span style={{ margin: "0 8px", opacity: 0.4 }}>|</span>
        <a
          href="https://github.com/xr843/fojin"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "inherit" }}
        >
          <GithubOutlined /> GitHub
        </a>
      </Footer>
      <Drawer
        title={t("nav.drawer_title")}
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
