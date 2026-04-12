import { useState, useEffect, type ReactNode } from "react";
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
  FileTextOutlined,
  MenuOutlined,
  DashboardOutlined,
  RobotOutlined,
  GithubOutlined,
  GlobalOutlined,
  // NotificationOutlined,
  // FieldTimeOutlined,
  // BarChartOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../stores/authStore";
import { getPendingSuggestionCount, getPendingFeedbackCount } from "../api/client";
import FeedbackButton from "./FeedbackButton";
import NotificationBell from "./NotificationBell";
import CursorGlow from "./CursorGlow";

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
    Promise.all([getPendingSuggestionCount(), getPendingFeedbackCount()])
      .then(([sc, fc]) => setPendingCount(sc + fc))
      .catch(() => {});
  }, [isAdmin, location.pathname]);

  const navItems: Array<{
    icon: ReactNode;
    label: string;
    path: string;
    children?: Array<{ label: string; path: string }>;
  }> = [
    { icon: <DatabaseOutlined />, label: t("nav.sources"), path: "/sources" },
    { icon: <RobotOutlined />, label: t("nav.chat"), path: "/chat" },
    { icon: <FileTextOutlined />, label: t("nav.dictionary"), path: "/dictionary" },
    { icon: <ApartmentOutlined />, label: t("nav.kg"), path: "/kg" },
    // TODO: 佛教地理暂时隐藏，待人物 geocoding 数据质量问题解决后重新上线
    // （~1000 条中国僧人因 desc_match 贪心匹配被错投到韩国同名寺院，见 session 2026-04-12）
    // { icon: <GlobalOutlined />, label: t("nav.geo"), path: "/map" },
    { icon: <BookOutlined />, label: t("nav.collections"), path: "/collections" },
    // TODO: 佛学动态暂时隐藏，待加入cron定时抓取后重新上线
    // { icon: <NotificationOutlined />, label: t("nav.activity"), path: "/activity" },
    // TODO: 时间线和数据总览暂时隐藏，待优化后重新上线
    // { icon: <FieldTimeOutlined />, label: t("nav.timeline"), path: "/timeline" },
    // { icon: <BarChartOutlined />, label: t("nav.dashboard"), path: "/dashboard" },
    ...(isAdmin
      ? [
          {
            icon: <Badge count={pendingCount} size="small" offset={[4, -2]}><DashboardOutlined /></Badge>,
            label: t("nav.admin"),
            path: "/admin",
            children: [
              { label: t("nav.admin_overview"), path: "/admin" },
              { label: t("nav.admin_users"), path: "/admin/users" },
              { label: t("nav.admin_suggestions"), path: "/admin/suggestions" },
              { label: t("nav.admin_annotations"), path: "/admin/annotations" },
              { label: t("nav.admin_feedbacks"), path: "/admin/feedbacks" },
            ],
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
            {navItems.map((item) =>
              item.children ? (
                <Dropdown
                  key={item.path}
                  menu={{
                    items: item.children.map((child) => ({
                      key: child.path,
                      label: child.label,
                      onClick: () => navigate(child.path),
                    })),
                  }}
                >
                  <Button
                    type="text"
                    icon={item.icon}
                    style={{
                      color: inkMuted,
                      fontSize: 13,
                      fontWeight: 400,
                      fontFamily: '"Noto Serif SC", serif',
                    }}
                  >
                    {item.label}
                  </Button>
                </Dropdown>
              ) : (
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
              ),
            )}
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
          <NotificationBell />
          <Dropdown
            menu={{
              items: [
                { key: "zh", label: "中文简体" },
                { key: "zh-Hant", label: "中文繁體" },
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
              <span className="header-lang-text">{t(`language.${i18n.resolvedLanguage ?? i18n.language}`)}</span>
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
                <span className="header-username">{user.display_name || user.username}</span>
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
              <span className="header-login-text">{t("auth.login")}</span>
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
        width="100%"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          {navItems.map((item) =>
            item.children ? (
              <div key={item.path}>
                <Button
                  type="text"
                  icon={item.icon}
                  block
                  style={{ textAlign: "left", color: inkMuted, fontWeight: 500 }}
                  onClick={() => { navigate(item.path); setDrawerOpen(false); }}
                >
                  {item.label}
                </Button>
                {item.children.map((child) => (
                  <Button
                    key={child.path}
                    type="text"
                    block
                    style={{ textAlign: "left", color: inkMuted, paddingLeft: 32 }}
                    onClick={() => { navigate(child.path); setDrawerOpen(false); }}
                  >
                    {child.label}
                  </Button>
                ))}
              </div>
            ) : (
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
            ),
          )}
        </Space>
      </Drawer>
      {isHome && <FeedbackButton />}
      <CursorGlow />
    </AntLayout>
  );
}
