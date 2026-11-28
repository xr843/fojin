import { useMemo, useState } from "react";
import { Alert, Button, Card, Col, Row, Tabs, Statistic, Spin, Segmented, Empty, Tooltip, Typography, message, DatePicker, Table, Tag } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import {
  UserOutlined,
  MessageOutlined,
  CommentOutlined,
  WarningOutlined,
  LikeOutlined,
  BookOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
} from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { DualAxes } from "@ant-design/charts";
import {
  getAdminOverview,
  getAdminTrends,
  getAdminModuleUsage,
  getAdminActiveUsers,
  type AdminOverview,
  type ActiveUserDetail,
  type SectionUsageItem,
} from "../api/client";
import { getPlatformActivity } from "../api/feed";
import { useEffectiveTheme } from "../hooks/useTheme";
import { adminLabel, formatAdminDate } from "./adminI18n";
import { groupModuleEvents, MIN_USERS, type UsageGroup, type UsageRow } from "./adminModuleGroups";

const { Text } = Typography;

function DeltaSuffix({ today, yesterday }: { today: number; yesterday: number }) {
  const { t } = useTranslation();
  const diff = today - yesterday;
  const Arrow = diff >= 0 ? ArrowUpOutlined : ArrowDownOutlined;
  const todayColor = today > 0 ? "var(--fj-success)" : "var(--fj-text-secondary)";
  const diffColor =
    diff > 0 ? "var(--fj-success)" : diff < 0 ? "var(--fj-danger)" : "var(--fj-text-secondary)";
  return (
    <Tooltip title={t("admin_dashboard.delta.tooltip", { today, yesterday })}>
      <span style={{ fontSize: 13, color: todayColor, marginLeft: 4 }}>+{today}</span>
      <span style={{ fontSize: 12, color: diffColor, marginLeft: 6 }}>
        <Arrow style={{ fontSize: 10 }} /> {Math.abs(diff)}
      </span>
    </Tooltip>
  );
}

function PendingCard({ overview }: { overview: AdminOverview }) {
  const { t } = useTranslation();
  const total = overview.pending_suggestions + overview.pending_annotations;
  const tip = t("admin_dashboard.pending.tooltip", {
    suggestions: overview.pending_suggestions,
    annotations: overview.pending_annotations,
  });
  return (
    <Card>
      <Tooltip title={tip}>
        <Statistic
          title={t("admin_dashboard.pending.title")}
          value={total}
          prefix={<WarningOutlined />}
          valueStyle={{ color: total > 0 ? "var(--fj-warning)" : undefined }}
          suffix={
            total > 0 ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t("admin_dashboard.pending.suffix", {
                  suggestions: overview.pending_suggestions,
                  annotations: overview.pending_annotations,
                })}
              </Text>
            ) : (
              <Text type="success" style={{ fontSize: 12 }}>
                {t("admin_dashboard.pending.cleared")}
              </Text>
            )
          }
        />
      </Tooltip>
    </Card>
  );
}

function ActiveUsersCard({ date, onDateChange }: { date: string | null; onDateChange: (d: string) => void }) {
  const { t, i18n } = useTranslation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["adminActiveUsers", date],
    queryFn: () => getAdminActiveUsers(date!),
    enabled: !!date,
    staleTime: 60_000,
  });

  const columns = [
    {
      title: t("admin_dashboard.active_users.column.user"),
      key: "user",
      render: (_: unknown, r: ActiveUserDetail) => (
        <Link to={`/admin/users?q=${encodeURIComponent(r.username ?? String(r.user_id))}`}>
          {r.display_name || r.username || `#${r.user_id}`}
        </Link>
      ),
    },
    { title: t("admin_dashboard.active_users.column.email"), dataIndex: "email", key: "email", render: (v: string | null) => v || "—" },
    {
      title: t("admin_dashboard.active_users.column.role"),
      dataIndex: "role",
      key: "role",
      render: (v: string) =>
        v === "admin" ? (
          <Tag color="gold">{t("admin_dashboard.active_users.role.admin")}</Tag>
        ) : (
          <Tag>{t("admin_dashboard.active_users.role.user")}</Tag>
        ),
    },
    {
      title: t("admin_dashboard.active_users.column.chat_messages"),
      dataIndex: "chat_messages",
      key: "chat_messages",
      sorter: (a: ActiveUserDetail, b: ActiveUserDetail) => a.chat_messages - b.chat_messages,
      defaultSortOrder: "descend" as const,
    },
    {
      title: t("admin_dashboard.active_users.column.texts_read"),
      dataIndex: "texts_read",
      key: "texts_read",
      sorter: (a: ActiveUserDetail, b: ActiveUserDetail) => a.texts_read - b.texts_read,
    },
    {
      title: t("admin_dashboard.active_users.column.dict_views"),
      dataIndex: "dict_views",
      key: "dict_views",
      render: (v: number | null | undefined) => (v == null ? "—" : v),
      sorter: (a: ActiveUserDetail, b: ActiveUserDetail) => (a.dict_views ?? 0) - (b.dict_views ?? 0),
    },
    {
      title: t("admin_dashboard.active_users.column.history_views"),
      dataIndex: "history_views",
      key: "history_views",
      render: (v: number | null | undefined) => (v == null ? "—" : v),
      sorter: (a: ActiveUserDetail, b: ActiveUserDetail) => (a.history_views ?? 0) - (b.history_views ?? 0),
    },
    {
      title: t("admin_dashboard.active_users.column.search_views"),
      dataIndex: "search_views",
      key: "search_views",
      render: (v: number | null | undefined) => (v == null ? "—" : v),
      sorter: (a: ActiveUserDetail, b: ActiveUserDetail) => (a.search_views ?? 0) - (b.search_views ?? 0),
    },
    {
      title: t("admin_dashboard.active_users.column.api_provider"),
      dataIndex: "api_provider",
      key: "api_provider",
      render: (v: string | null) => (v ? <Tag color="green">{v}</Tag> : "—"),
    },
    {
      title: t("admin_dashboard.active_users.column.last_active"),
      dataIndex: "last_active_at",
      key: "last_active_at",
      render: (v: string | null) => formatAdminDate(v, i18n.language),
    },
  ];

  return (
    <Card
      title={
        data
          ? t("admin_dashboard.active_users.title_with_count", { count: data.total })
          : t("admin_dashboard.active_users.title")
      }
      style={{ marginTop: 16 }}
      extra={
        <DatePicker
          value={date ? dayjs(date) : null}
          onChange={(d: Dayjs | null) => d && onDateChange(d.format("YYYY-MM-DD"))}
          allowClear={false}
        />
      }
    >
      {data && data.guest_messages != null && (
        <div style={{ marginBottom: 12 }}>
          <Tag color="cyan">{t("admin_dashboard.active_users.guest_tag")}</Tag>
          <Text>{t("admin_dashboard.active_users.guest_line", { n: data.guest_messages })}</Text>
        </div>
      )}
      {isError ? (
        <Empty description={t("admin_dashboard.common.load_failed")} />
      ) : isLoading ? (
        <div style={{ textAlign: "center", padding: 24 }}><Spin /></div>
      ) : !data || data.users.length === 0 ? (
        <Empty description={t("admin_dashboard.active_users.empty")} />
      ) : (
        <Table
          rowKey="user_id"
          size="small"
          columns={columns}
          dataSource={data.users}
          pagination={data.users.length > 20 ? { pageSize: 20 } : false}
        />
      )}
      <Text type="secondary" style={{ fontSize: 12 }}>
        {t("admin_dashboard.active_users.note_v2", { since: data?.members_since ?? "2026-11-28" })}
      </Text>
    </Card>
  );
}

export default function AdminDashboardPage() {
  const { t, i18n } = useTranslation();
  const isDark = useEffectiveTheme() === "dark";
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const overviewQuery = useQuery({
    queryKey: ["adminOverview"],
    queryFn: getAdminOverview,
    staleTime: 60_000,
  });
  const trendsQuery = useQuery({
    queryKey: ["adminTrends", 30],
    queryFn: () => getAdminTrends(30),
    staleTime: 60_000,
  });

  if (overviewQuery.isLoading || trendsQuery.isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (overviewQuery.isError || trendsQuery.isError) {
    message.error(t("admin_dashboard.common.stats_load_failed"));
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Empty description={t("admin_dashboard.common.load_failed_retry")} />
      </div>
    );
  }

  // React Query can report a query as neither loading nor error while its data is
  // still undefined — status:'pending' + fetchStatus:'idle' (e.g. the gap after a
  // transient 503, before a retry lands). `isLoading` is `isPending && isFetching`,
  // so it reads false there. Guarding on the actual payload (instead of a `!`
  // assertion) keeps a momentary backend blip from throwing at `trends.messages`
  // and taking the whole admin route down via the ErrorBoundary; the page shows a
  // spinner and recovers once the data arrives.
  const overview = overviewQuery.data;
  const trends = trendsQuery.data;

  if (!overview || !trends) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  // Dual Y-axis: 消息数 (tens~hundreds) on the left, 新增用户 + 活跃用户
  // (single digits ~ teens) on the right. On a shared axis the two
  // small-magnitude series flatten to the baseline and can't be read.
  // Series labels: defined once so the chart data, the legend and the shared
  // color domain below all reference the exact same strings (a mismatch would
  // silently drop a series back to a default color).
  const S_MESSAGES = t("admin_dashboard.trends.series.messages");
  const S_ANON_MESSAGES = t("admin_dashboard.trends.series.anonymous_messages");
  const S_NEW_USERS = t("admin_dashboard.trends.series.new_users");
  const S_ACTIVE_USERS = t("admin_dashboard.trends.series.active_users");
  // 游客消息数（内容不落库，只记数）——没有它，这张图只覆盖注册用户。
  // ?? []：滚动部署期间旧后端还没有这个字段，别让 map 炸掉整页。
  const messagesData = [
    ...trends.messages.map((d) => ({ ...d, type: S_MESSAGES })),
    ...(trends.anonymous_messages ?? []).map((d) => ({ ...d, type: S_ANON_MESSAGES })),
  ];
  const usersData = [
    ...trends.registrations.map((d) => ({ ...d, type: S_NEW_USERS })),
    ...trends.active_users.map((d) => ({ ...d, type: S_ACTIVE_USERS })),
  ];

  // Latest day in the trend = default selection for the active-users table.
  const latestDay = trends.active_users.length
    ? trends.active_users[trends.active_users.length - 1].date
    : null;

  // Both children map colorField "type" to ONE shared G2 color scale (keyed by
  // field name). If each declares only its own range, the merged scale picks up
  // the 2-color range and cycles it across the 3 series, so 消息数 and 活跃用户
  // both land on orange. Declaring the SAME full domain→range on both children
  // pins every series to a distinct color: 消息数 蓝 / 新增用户 橙 / 活跃用户 绿.
  const seriesColor = {
    domain: [S_MESSAGES, S_ANON_MESSAGES, S_NEW_USERS, S_ACTIVE_USERS],
    range: ["#1677ff", "#13c2c2", "#fa8c16", "#52c41a"],
  };
  // G2 draws into a <canvas>, so the --fj-* custom properties never reach it: the
  // chart kept G2's light theme and painted its axis labels a dark grey that is
  // unreadable on the dark card. Switch G2's own theme (which also carries the
  // legend and tooltip, and keeps the plot background transparent) and hand the
  // axis colours over as literals, warm ones rather than G2's cool blue-grey.
  const axisStyle = isDark
    ? {
        labelFill: "#d2c7b1", // --fj-ink-light, 5.99:1 on the card
        titleFill: "#d2c7b1",
        lineStroke: "#60553f", // --fj-border
        tickStroke: "#60553f",
        gridStroke: "#3c342a",
      }
    : {};
  const chartConfig = {
    // Light stays on G2's default theme — untouched, byte for byte.
    ...(isDark ? { theme: "classicDark" } : {}),
    xField: "date",
    height: 360,
    legend: { color: { itemMarker: "round" } },
    axis: { x: { labelAutoRotate: false, ...axisStyle } },
    children: [
      {
        data: messagesData,
        type: "line",
        yField: "count",
        colorField: "type",
        smooth: true,
        axis: { y: { ...axisStyle } },
        scale: { color: seriesColor },
      },
      {
        data: usersData,
        type: "line",
        yField: "count",
        colorField: "type",
        smooth: true,
        axis: { y: { position: "right", ...axisStyle } },
        scale: { color: seriesColor },
      },
    ],
    // Click any point to drill the active-users table to that day.
    onReady: ({ chart }: { chart: { on: (ev: string, cb: (e: { data?: { data?: { date?: string } } }) => void) => void } }) => {
      chart.on("element:click", (e) => {
        const d = e?.data?.data?.date;
        if (d) setActiveDate(d);
      });
    },
  };

  const lastUpdated = overview.last_updated
    ? formatAdminDate(overview.last_updated, i18n.language)
    : "—";

  return (
    <>
      <Helmet>
        <title>{t("admin_dashboard.page_title")}</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title={t("admin_dashboard.overview.total_users")}
                value={overview.total_users}
                prefix={<UserOutlined />}
                suffix={
                  <DeltaSuffix
                    today={overview.new_users_today}
                    yesterday={overview.new_users_yesterday}
                  />
                }
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title={t("admin_dashboard.overview.total_sessions")}
                value={overview.total_sessions}
                prefix={<CommentOutlined />}
                suffix={
                  <DeltaSuffix
                    today={overview.new_sessions_today}
                    yesterday={overview.new_sessions_yesterday}
                  />
                }
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title={t("admin_dashboard.overview.total_messages")}
                value={overview.total_messages}
                prefix={<MessageOutlined />}
                suffix={
                  <DeltaSuffix
                    today={overview.new_messages_today}
                    yesterday={overview.new_messages_yesterday}
                  />
                }
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <PendingCard overview={overview} />
          </Col>
        </Row>

        <UsageErrorsBanner />

        <Card
          title={t("admin_dashboard.trends.title")}
          style={{ marginTop: 16 }}
          extra={<Text type="secondary" style={{ fontSize: 12 }}>{t("admin_dashboard.trends.updated_at", { date: lastUpdated })}</Text>}
        >
          <DualAxes {...chartConfig} />
        </Card>

        <ActiveUsersCard
          date={activeDate ?? latestDay}
          onDateChange={setActiveDate}
        />

        <ModuleUsageCard />
        <AnswerQualityAndKeywords />
        <PlatformActivityCard />
      </div>
    </>
  );
}

function UsageGroupTable({ group }: { group: UsageGroup | { key: "other"; danger: false; rows: UsageRow[] } }) {
  const { t } = useTranslation();
  const arrow = (a: number, b: number | undefined, kind: UsageRow["kind"]) => (kind === "funnel" ? `${a} → ${b ?? 0}` : String(a));
  const hasFunnel = group.rows.some((r) => r.kind === "funnel");
  return (
    <Table<UsageRow>
      size="small"
      rowKey="key"
      pagination={false}
      dataSource={group.rows}
      columns={[
        {
          title: t("admin_dashboard.module_usage.col_feature"),
          render: (_, r) => adminLabel(t, r.labelKey, r.fallback),
        },
        {
          title: t("admin_dashboard.module_usage.col_users"),
          align: "right",
          width: 90,
          render: (_, r) => <Text strong>{arrow(r.users, r.toUsers, r.kind)}</Text>,
        },
        {
          title: t("admin_dashboard.module_usage.col_count"),
          align: "right",
          width: 100,
          render: (_, r) => <Text type="secondary">{arrow(r.count, r.toCount, r.kind)}</Text>,
        },
        ...(hasFunnel
          ? [
              {
                title: t("admin_dashboard.module_usage.col_rate"),
                align: "right" as const,
                width: 70,
                render: (_: unknown, r: UsageRow) => (r.kind === "funnel" && r.rate != null ? `${r.rate}%` : ""),
              },
            ]
          : []),
      ]}
    />
  );
}

/** 板块总览的显示顺序：先看主功能，other 放最后 */
const SECTION_ORDER = ["chat", "read", "dict", "history", "search", "sources", "texts", "home", "daily", "kg", "other"];

function useModuleUsage(days: number) {
  return useQuery({
    queryKey: ["adminModuleUsage", days],
    queryFn: () => getAdminModuleUsage(days),
    staleTime: 300_000,
  });
}

/** 上一周期少于这个数就不画涨跌箭头：2→5 显示「↑150%」只会误导 */
const TREND_MIN_BASE = 10;

function Trend({ cur, prev }: { cur: number; prev: number }) {
  if (prev < TREND_MIN_BASE || cur === prev) return null;
  const pct = Math.round(((cur - prev) / prev) * 100);
  if (pct === 0) return null;
  return (
    <Text style={{ fontSize: 12, marginLeft: 4, color: pct > 0 ? "var(--fj-success)" : "var(--fj-danger)" }}>
      {pct > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
      {Math.abs(pct)}%
    </Text>
  );
}

/** 页面顶部的异常提示：最近 7 天有问答断流 / 溯源出错才显示 */
function UsageErrorsBanner() {
  const { t } = useTranslation();
  const { data } = useModuleUsage(7);
  const grouped = useMemo(() => groupModuleEvents(data?.events ?? []), [data]);
  const errors = grouped.groups.find((g) => g.danger);
  if (!errors || errors.rows.length === 0) return null;
  return (
    <Alert
      type="warning"
      showIcon
      style={{ marginTop: 16 }}
      message={t("admin_dashboard.module_usage.errors_banner_title")}
      description={errors.rows
        .map((r) => t("admin_dashboard.module_usage.errors_banner_item", {
          label: adminLabel(t, r.labelKey, r.fallback),
          n: r.count,
          users: r.users,
        }))
        .join(" · ")}
    />
  );
}

function ModuleUsageCard() {
  const { t } = useTranslation();
  const [days, setDays] = useState<number>(7);
  const { data, isLoading } = useModuleUsage(days);
  const grouped = useMemo(() => groupModuleEvents(data?.events ?? []), [data]);
  const sections = useMemo(
    () =>
      [...(data?.sections ?? [])].sort(
        (a, b) => SECTION_ORDER.indexOf(a.section) - SECTION_ORDER.indexOf(b.section),
      ),
    [data],
  );
  const detailGroups = grouped.groups.filter((g) => !g.danger);

  return (
    <Card
      title={t("admin_dashboard.module_usage.title_v2")}
      style={{ marginTop: 16 }}
      extra={
        <Segmented
          value={days}
          onChange={(v) => setDays(v as number)}
          options={[
            { label: t("admin_dashboard.days", { count: 7 }), value: 7 },
            { label: t("admin_dashboard.days", { count: 14 }), value: 14 },
            { label: t("admin_dashboard.days", { count: 30 }), value: 30 },
          ]}
        />
      }
    >
      {isLoading ? (
        <Spin />
      ) : !data || data.events.length === 0 ? (
        <Empty description={t("admin_dashboard.module_usage.empty")} />
      ) : (
        <>
          {sections.length > 0 && (
            <>
              <Table<SectionUsageItem>
                size="small"
                rowKey="section"
                pagination={false}
                dataSource={sections}
                columns={[
                  {
                    title: t("admin_dashboard.module_usage.col_section"),
                    render: (_, r) => t(`admin_dashboard.module_usage.section.${r.section}`, { defaultValue: r.section }),
                  },
                  {
                    title: t("admin_dashboard.module_usage.col_active_users"),
                    align: "right",
                    render: (_, r) => (
                      <>
                        <Text strong>{r.users}</Text>
                        <Trend cur={r.users} prev={r.prev_users} />
                      </>
                    ),
                  },
                  {
                    title: t("admin_dashboard.module_usage.col_actions"),
                    align: "right",
                    render: (_, r) => (
                      <>
                        {r.count}
                        <Trend cur={r.count} prev={r.prev_count} />
                      </>
                    ),
                  },
                  {
                    title: t("admin_dashboard.module_usage.col_members"),
                    align: "right",
                    render: (_, r) => r.members,
                  },
                  {
                    title: t("admin_dashboard.module_usage.col_pageviews"),
                    align: "right",
                    render: (_, r) => <Text type="secondary">{r.pageviews}</Text>,
                  },
                ]}
              />
              <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 4, marginBottom: 16 }}>
                {t("admin_dashboard.module_usage.sections_note", {
                  n: data.excluded_staff_events ?? 0,
                  since: data.members_since ?? "",
                })}
              </Text>
            </>
          )}

          <Tabs
            size="small"
            items={[
              ...detailGroups.map((g) => ({
                key: g.key,
                label: t(`admin_dashboard.module_usage.group.${g.key}`),
                children: <UsageGroupTable group={g} />,
              })),
              ...(grouped.other.length > 0
                ? [
                    {
                      key: "other",
                      label: t("admin_dashboard.module_usage.tab_other", { n: grouped.other.length }),
                      children: (
                        <>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {t("admin_dashboard.module_usage.group.other", { n: grouped.other.length, min: MIN_USERS })}
                          </Text>
                          <UsageGroupTable group={{ key: "other", danger: false, rows: grouped.other }} />
                        </>
                      ),
                    },
                  ]
                : []),
            ]}
          />
        </>
      )}
    </Card>
  );
}

/** 回答质量 + 热门检索词：原来塞在模块使用卡底部，拆成并排两张小卡 */
function AnswerQualityAndKeywords() {
  const { t } = useTranslation();
  const [days, setDays] = useState<number>(7);
  const { data } = useModuleUsage(days);
  if (!data) return null;
  const q = data.answer_quality;
  const daysSwitch = (
    <Segmented
      size="small"
      value={days}
      onChange={(v) => setDays(v as number)}
      options={[
        { label: t("admin_dashboard.days", { count: 7 }), value: 7 },
        { label: t("admin_dashboard.days", { count: 30 }), value: 30 },
      ]}
    />
  );
  return (
    <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
      <Col xs={24} lg={12}>
        <Card title={t("admin_dashboard.answer_quality.title")} extra={daysSwitch} style={{ height: "100%" }}>
          {q && (
            <>
              <Row gutter={[16, 16]}>
                <Col span={8}>
                  <Tooltip title={t("admin_dashboard.answer_quality.citation_click_tooltip", {
                    clicks: q.citation_click,
                    questions: q.chat_questions,
                  })}>
                    <Statistic
                      title={t("admin_dashboard.answer_quality.citation_click_rate")}
                      value={q.citation_click_rate ?? "—"}
                      suffix={q.citation_click_rate == null ? "" : "%"}
                    />
                  </Tooltip>
                </Col>
                <Col span={8}>
                  <Tooltip title={t("admin_dashboard.answer_quality.copy_tooltip", {
                    copies: q.chat_copy,
                    questions: q.chat_questions,
                  })}>
                    <Statistic
                      title={t("admin_dashboard.answer_quality.copy_rate")}
                      value={q.copy_rate ?? "—"}
                      suffix={q.copy_rate == null ? "" : "%"}
                    />
                  </Tooltip>
                </Col>
                <Col span={8}>
                  <Tooltip title={t("admin_dashboard.answer_quality.retry_tooltip", {
                    retries: q.chat_retry,
                    questions: q.chat_questions,
                  })}>
                    <Statistic
                      title={t("admin_dashboard.answer_quality.retry_rate")}
                      value={q.retry_rate ?? "—"}
                      suffix={q.retry_rate == null ? "" : "%"}
                      valueStyle={{ color: (q.retry_rate ?? 0) > 5 ? "var(--fj-danger)" : undefined }}
                    />
                  </Tooltip>
                </Col>
              </Row>
              <Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>
                {t("admin_dashboard.answer_quality.subtitle")}
              </Text>
            </>
          )}
        </Card>
      </Col>
      <Col xs={24} lg={12}>
        <Card title={t("admin_dashboard.module_usage.top_keywords")} style={{ height: "100%" }}>
          {data.top_search_keywords.length === 0 ? (
            <Empty />
          ) : (
            data.top_search_keywords.map((kw, i) => (
              <div
                key={`${kw.keyword}-${i}`}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "3px 0",
                  borderBottom: i < data.top_search_keywords.length - 1 ? "1px solid var(--fj-border, #f0f0f0)" : undefined,
                }}
              >
                <span>
                  <Text type="secondary" style={{ marginRight: 8 }}>{i + 1}.</Text>
                  {kw.keyword}
                </span>
                <span style={{ color: "var(--fj-text-secondary)" }}>{t("admin_dashboard.unit.times", { count: kw.count })}</span>
              </div>
            ))
          )}
        </Card>
      </Col>
    </Row>
  );
}

function PlatformActivityCard() {
  const { t } = useTranslation();
  const [days, setDays] = useState<number>(7);
  const [showAllTexts, setShowAllTexts] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["platformActivity", days],
    queryFn: () => getPlatformActivity({ days }),
    staleTime: 300_000,
  });

  if (isLoading) {
    return (
      <Card title={t("admin_dashboard.platform_activity.title")} style={{ marginTop: 16 }}>
        <Spin />
      </Card>
    );
  }
  if (!data) {
    return (
      <Card title={t("admin_dashboard.platform_activity.title")} style={{ marginTop: 16 }}>
        <Empty />
      </Card>
    );
  }

  // Two distinct metrics (was conflated into one misleading "好评率 = 赞/总消息"):
  //   反馈率 = (赞+踩)/消息  — how many answers users bothered to rate
  //   好评率 = 赞/(赞+踩)     — of those rated, how many were liked
  const ratedCount = data.chat.positive_feedback + data.chat.negative_feedback;
  const feedbackRate =
    data.chat.total_messages > 0
      ? `${((ratedCount / data.chat.total_messages) * 100).toFixed(1)}%`
      : "—";
  const positiveRate =
    ratedCount > 0 ? `${((data.chat.positive_feedback / ratedCount) * 100).toFixed(1)}%` : "—";

  // 未引经率 = 无来源的 AI 回答 / AI 回答总数。粗略质量信号：含真·RAG 召回缺口，
  // 但也含寒暄/身份类提问(本就无需引经)和 AI 出错回答,故不等于纯检索失败率。
  const failRate =
    data.chat.assistant_messages > 0
      ? `${((data.chat.assistant_no_source / data.chat.assistant_messages) * 100).toFixed(1)}%`
      : "—";
  // 自带 Key 占活跃用户比例（其余跑平台 key = 你补贴的成本）
  const byokRate =
    data.users.active_users > 0
      ? `${((data.users.byok_active_users / data.users.active_users) * 100).toFixed(0)}%`
      : "—";

  return (
    <Card
      title={t("admin_dashboard.platform_activity.title")}
      style={{ marginTop: 16 }}
      extra={
        <Segmented
          value={days}
          onChange={(v) => setDays(v as number)}
          options={[
            { label: t("admin_dashboard.days", { count: 7 }), value: 7 },
            { label: t("admin_dashboard.days", { count: 14 }), value: 14 },
            { label: t("admin_dashboard.days", { count: 30 }), value: 30 },
          ]}
        />
      }
    >
      <Text type="secondary" style={{ fontSize: 12 }}>{t("admin_dashboard.platform_activity.users_section")}</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title={t("admin_dashboard.platform_activity.new_users")} value={data.users.new_users} prefix={<UserOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title={t("admin_dashboard.platform_activity.active_users")} value={data.users.active_users} />
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title={t("admin_dashboard.platform_activity.returning_users_tooltip")}>
            <Statistic
              title={t("admin_dashboard.platform_activity.returning_users")}
              value={data.users.returning_users}
              valueStyle={{ color: data.users.returning_users > data.users.new_users ? "var(--fj-success)" : undefined }}
            />
          </Tooltip>
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title={t("admin_dashboard.platform_activity.byok_tooltip", {
            count: data.users.byok_active_users,
            rate: byokRate,
          })}>
            <Statistic
              title={t("admin_dashboard.platform_activity.byok")}
              value={t("admin_dashboard.platform_activity.byok_value", {
                count: data.users.byok_active_users,
                rate: byokRate,
              })}
            />
          </Tooltip>
        </Col>
      </Row>

      <Text type="secondary" style={{ fontSize: 12 }}>{t("admin_dashboard.platform_activity.chat_reading_section")}</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={4}>
          <Statistic title={t("admin_dashboard.platform_activity.new_sessions")} value={data.chat.total_sessions} prefix={<CommentOutlined />} />
        </Col>
        <Col xs={12} sm={4}>
          <Statistic title={t("admin_dashboard.platform_activity.new_messages")} value={data.chat.total_messages} prefix={<MessageOutlined />} />
        </Col>
        <Col xs={12} sm={4}>
          <Tooltip title={t("admin_dashboard.platform_activity.feedback_rate_tooltip", {
            rated: ratedCount,
            positive: data.chat.positive_feedback,
            negative: data.chat.negative_feedback,
            total: data.chat.total_messages,
          })}>
            <Statistic title={t("admin_dashboard.platform_activity.feedback_rate")} value={feedbackRate} prefix={<LikeOutlined />} />
          </Tooltip>
        </Col>
        <Col xs={12} sm={4}>
          <Tooltip title={t("admin_dashboard.platform_activity.positive_rate_tooltip", {
            positive: data.chat.positive_feedback,
            negative: data.chat.negative_feedback,
            rated: ratedCount,
          })}>
            <Statistic
              title={t("admin_dashboard.platform_activity.positive_rate")}
              value={positiveRate}
              valueStyle={{ color: ratedCount > 0 && data.chat.positive_feedback >= data.chat.negative_feedback ? "var(--fj-success)" : undefined }}
            />
          </Tooltip>
        </Col>
        <Col xs={12} sm={4}>
          <Tooltip title={t("admin_dashboard.platform_activity.no_source_tooltip", {
            noSource: data.chat.assistant_no_source,
            total: data.chat.assistant_messages,
          })}>
            <Statistic
              title={t("admin_dashboard.platform_activity.no_source_rate")}
              value={failRate}
              valueStyle={{ color: data.chat.assistant_messages > 0 && data.chat.assistant_no_source / data.chat.assistant_messages > 0.3 ? "#cf1322" : undefined }}
            />
          </Tooltip>
        </Col>
        {/* 阅读次数仅记录登录用户；全站阅读见「各板块使用」的阅读行 */}
        <Col xs={12} sm={4}>
          <Statistic title={t("admin_dashboard.reading.total_reads_members")} value={data.reading.total_reads} prefix={<BookOutlined />} />
        </Col>
      </Row>


      {data.reading.top_texts.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4>{t("admin_dashboard.reading.top_texts")}</h4>
          {data.reading.top_texts.slice(0, showAllTexts ? undefined : 5).map((text, i) => (
            <div
              key={`${text.text_id}-${i}`}
              style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}
            >
              <Link to={`/texts/${text.text_id}`}>{text.title_zh}</Link>
              <span style={{ color: "var(--fj-text-secondary)" }}>{t("admin_dashboard.unit.times", { count: text.read_count })}</span>
            </div>
          ))}
          {data.reading.top_texts.length > 5 && (
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setShowAllTexts((v) => !v)}>
              {showAllTexts
                ? t("admin_dashboard.reading.collapse")
                : t("admin_dashboard.reading.show_all", { n: data.reading.top_texts.length })}
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}
