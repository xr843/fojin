import { useState, useEffect, type ReactNode } from "react";
import { Layout as AntLayout, Typography, Button, Dropdown, Space, Drawer, Modal, Badge } from "antd";
import { Outlet, useNavigate, useLocation } from "react-router";

import AudioPlayerProvider from "../audio/AudioPlayerProvider";
import PlayerBar from "../audio/PlayerBar";
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
  // TranslationOutlined,  // cross-canon nav hidden (板块待打磨；路由仍可直达 /cross-canon)
  // DownloadOutlined,   // exports nav hidden (开放数据 暂不对外公开)
  // ExperimentOutlined,  // research nav hidden (研究助手 待重构后再上线)
  // BarChartOutlined,   // dashboard nav hidden (数据总览 暂不对外公开)
  // FieldTimeOutlined,  // timeline nav deferred (pending polish)
  // NotificationOutlined,  // activity nav deferred (empty Source-Updates subtab)
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { currentUILang } from "../i18n";
import ThemeToggle from "./ThemeToggle";
import { useAuthStore } from "../stores/authStore";
import { useXiaojinStore } from "../stores/xiaojinStore";
import { getAdminPendingSummary, type AdminPendingSummary } from "../api/client";
import NotificationBell from "./NotificationBell";
import CursorGlow from "./CursorGlow";

const { Header, Content, Footer } = AntLayout;

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const { t, i18n } = useTranslation();
  const isHome = location.pathname === "/";
  const xiaojinHidden = useXiaojinStore((st) => st.hidden);
  const recallXiaojin = useXiaojinStore((st) => st.show);
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

  const [pending, setPending] = useState<AdminPendingSummary | null>(null);
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!isAdmin) return;
    getAdminPendingSummary().then(setPending).catch(() => {});
  }, [isAdmin, location.pathname]);

  const inboxCount =
    (pending?.suggestions ?? 0) + (pending?.feedbacks ?? 0) + (pending?.annotations ?? 0);
  const adminBadgeTotal =
    (pending?.answer_quality ?? 0) + (pending?.alignment_candidates ?? 0) + inboxCount;

  const navItems: Array<{
    icon: ReactNode;
    label: string;
    path: string;
    children?: Array<{ label: string; path: string; count?: number }>;
  }> = [
    { icon: <DatabaseOutlined />, label: t("nav.sources"), path: "/sources" },
    { icon: <RobotOutlined />, label: t("nav.chat"), path: "/chat" },
    // 跨藏对照(/cross-canon)专属浏览页暂从导航撤下：独立板块当前呈现效果不佳，
    // 打磨后再对外公开。路由仍可直达 /cross-canon（供直达/测试），阅读器内的
    // 跨藏对照面板、文本详情段级入口、搜索藏/梵徽章等集成功能不受影响。
    // { icon: <TranslationOutlined />, label: t("nav.cross_canon"), path: "/cross-canon" },
    // 研究助手(/research)暂从导航撤下：当前输出偏"更长的问答"，未凸显跨藏对比这一
    // 差异化，等重构(跨藏对比表 + 内联可点证据 + 流式)后再上线。后端 API 与
    // fojin-mcp 保留，/research 路由仍可直达。
    // { icon: <ExperimentOutlined />, label: t("nav.research"), path: "/research" },
    { icon: <FileTextOutlined />, label: t("nav.dictionary"), path: "/dictionary" },
    { icon: <ApartmentOutlined />, label: t("nav.kg"), path: "/kg" },
    { icon: <GlobalOutlined />, label: t("nav.geo"), path: "/map" },
    { icon: <BookOutlined />, label: t("nav.collections"), path: "/collections" },
    // 在线读诵(/read-aloud)不占导航位：读诵是**读一部经时的一个动作**，不是与
    // 辞典/知识图谱并列的一个板块 —— 它的入口已经在阅读页工具栏上，和跨藏对照、
    // 高麗藏、校勘排在同一排（那正是这类"就地展开"功能该待的地方，见上面
    // cross_canon 那行同样的处置）。放进导航等于把同一个入口做两遍。
    // 路由仍可直达 /read-aloud（索引页留着，供分享与直达）。
    // { icon: <SoundOutlined />, label: t("nav.readaloud"), path: "/read-aloud" },
    // 开放数据(/exports)暂不对外公开：后端路由由 ENABLE_OPEN_DATA_EXPORTS 控制，
    // 默认关闭（未鉴权、无限流，单次 kg.json 达 50MB/60s）。前端入口与路由一并撤下，
    // 重新放出时需同时打开后端开关并恢复 App.tsx 里的 /exports 路由。
    // { icon: <DownloadOutlined />, label: t("nav.exports"), path: "/exports" },
    // 数据总览(/dashboard)暂不对外公开：从导航撤下，路由仍可直达 /dashboard。
    // { icon: <BarChartOutlined />, label: t("nav.dashboard"), path: "/dashboard" },
    // 历史时间线(/timeline)暂不放导航：待打磨后再上线（路由仍可直达 /timeline）。
    // { icon: <FieldTimeOutlined />, label: t("nav.timeline"), path: "/timeline" },
    // 佛学动态(/activity)仍暂不放导航：Source-Updates 子标签无数据流（空）；
    // 待隐掉该空子标签后再放（feed cron 每日跑、/activity 路由仍可直达）。
    // { icon: <NotificationOutlined />, label: t("nav.activity"), path: "/activity" },
    ...(isAdmin
      ? [
          {
            // 顶层只用一个红点表示「有活儿」,不显示精确总数:四位数的角标会盖住
            // 「管理」二字,而且它的 sup 会挡住触发区、导致悬停打不开菜单。精确计数
            // 由下拉里的每一项各自给出。pointerEvents:none 是双保险。
            icon: (
              <Badge
                dot={adminBadgeTotal > 0}
                offset={[2, -2]}
                style={{ pointerEvents: "none" }}
              >
                <DashboardOutlined />
              </Badge>
            ),
            label: t("nav.admin"),
            path: "/admin",
            // 常驻 4 项。判据是「需不需要你主动定期查看」:
            //   概览/用户管理 = 日常;差答案队列 + 跨藏对齐 = 有积压要处理。
            // 源建议/反馈/标注是被动响应型队列(没人提交就没活儿)→ 收进「待办」,
            // 计数为 0 时整项不渲染。审计日志移出菜单(挂在用户管理页)。
            children: [
              { label: t("nav.admin_overview"), path: "/admin" },
              { label: t("nav.admin_users"), path: "/admin/users" },
              {
                label: t("nav.admin_answer_quality"),
                path: "/admin/answer-quality",
                count: pending?.answer_quality ?? 0,
              },
              {
                label: t("nav.admin_alignment"),
                path: "/admin/alignment",
                count: pending?.alignment_candidates ?? 0,
              },
              ...(inboxCount > 0
                ? [{ label: t("nav.admin_inbox"), path: "/admin/inbox", count: inboxCount }]
                : []),
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
          e.currentTarget.style.background = "var(--fj-surface)";
          e.currentTarget.style.color = "var(--fj-ink)";
          e.currentTarget.style.border = "1px solid var(--fj-gold)";
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
            {t("app.name")}
          </Typography.Title>
          <div className="nav-desktop">
            {navItems.map((item) =>
              item.children ? (
                <Dropdown
                  key={item.path}
                  // Menu items carry count badges and can be wider than the
                  // trigger button; by default antd/rc-dropdown stretches the
                  // popup's min-width to match the (narrower) trigger, which
                  // pushed wide items into a horizontal scrollbar. Force a
                  // generous min-width instead.
                  overlayStyle={{ minWidth: 200 }}
                  menu={{
                    items: item.children.map((child) => ({
                      key: child.path,
                      // 角标必须是独立元素排在文字之后。用 <Badge> 包裹 label 会把
                      // 计数绝对定位到子元素右上角 —— 数字一长(447/758)就压在文字上。
                      label: child.count ? (
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 8,
                            width: "100%",
                          }}
                        >
                          <span>{child.label}</span>
                          <Badge
                            count={child.count}
                            size="small"
                            overflowCount={9999}
                            style={{ marginLeft: "auto" }}
                          />
                        </span>
                      ) : (
                        child.label
                      ),
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
          <ThemeToggle />
          <NotificationBell />
          <Dropdown
            menu={{
              items: [
                { key: "zh", label: t("language.zh") },
                { key: "zh-Hant", label: t("language.zh-Hant") },
                { key: "en", label: "English" },
              ],
              onClick: ({ key }) => i18n.changeLanguage(key),
              selectedKeys: [currentUILang(i18n)],
            }}
          >
            <Button
              type="text"
              icon={<GlobalOutlined />}
              style={{ color: inkMuted, fontSize: 13 }}
              aria-label={t("a11y.button.switch_language")}
            >
              <span className="header-lang-text">{t(`language.${currentUILang(i18n)}`)}</span>
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
                aria-label={t("a11y.button.user_menu")}
              >
                <span className="header-username">{user.display_name || user.username}</span>
              </Button>
            </Dropdown>
          ) : (
            <Button
              type="text"
              icon={<LoginOutlined />}
              style={{
                color: "var(--fj-on-accent)",
                background: accent,
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 400,
                height: 30,
                padding: "0 16px",
                fontFamily: '"Noto Serif SC", serif',
              }}
              onClick={() => navigate("/login")}
              aria-label={t("a11y.button.login")}
            >
              <span className="header-login-text">{t("auth.login")}</span>
            </Button>
          )}
        </Space>
      </Header>
      <Content id="main-content" style={{ padding: isHome ? 0 : undefined, flex: 1 }} className={isHome ? undefined : "layout-content-inner"}>
        <AudioPlayerProvider>
          <Outlet />
          {/* 播放器住 Layout 层：切卷会重挂载页面组件，住页面里跨卷续播必断 */}
          <PlayerBar />
        </AudioPlayerProvider>
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
        {/* 「退出小津」的找回入口。持久退出必须成对配一个恢复口，否则就是
            2026-08-07 那个单向门 bug。只在首页（小津的地盘）且确实退出了才露。 */}
        {isHome && xiaojinHidden && (
          <>
            <span style={{ margin: "0 8px", opacity: 0.4 }}>|</span>
            <button
              type="button"
              onClick={recallXiaojin}
              style={{
                border: 0,
                background: "none",
                color: "inherit",
                font: "inherit",
                cursor: "pointer",
                textDecoration: "underline",
                textUnderlineOffset: 2,
                padding: 0,
              }}
            >
              {t("xiaojin.recall")}
            </button>
          </>
        )}
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
                    {child.count ? (
                      <Badge
                        count={child.count}
                        size="small"
                        overflowCount={9999}
                        style={{ marginLeft: 8 }}
                      />
                    ) : null}
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
      <CursorGlow />
    </AntLayout>
  );
}
