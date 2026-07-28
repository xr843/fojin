import { useState } from "react";
import { Card, Col, Row, Statistic, Spin, Segmented, Empty, Tooltip, Typography, message, DatePicker, Table, Tag } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import {
  UserOutlined,
  MessageOutlined,
  CommentOutlined,
  WarningOutlined,
  LikeOutlined,
  BookOutlined,
  DatabaseOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  SearchOutlined,
  RobotOutlined,
  ReadOutlined,
  LinkOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { DualAxes } from "@ant-design/charts";
import {
  getAdminOverview,
  getAdminTrends,
  getAdminModuleUsage,
  getAdminActiveUsers,
  type AdminOverview,
  type ModuleEventItem,
  type ActiveUserDetail,
} from "../api/client";
import { getPlatformActivity } from "../api/feed";
import { useEffectiveTheme } from "../hooks/useTheme";
import { adminLabel, formatAdminDate } from "./adminI18n";

const { Text } = Typography;

const moduleEventLabelKeyMap: Record<string, string> = {
  search: "admin_dashboard.module_usage.event.search",
  chat: "admin_dashboard.module_usage.event.chat",
  read: "admin_dashboard.module_usage.event.read",
  source_click: "admin_dashboard.module_usage.event.source_click",
  "cbeta-shortcut": "admin_dashboard.module_usage.event.cbeta_shortcut",
};

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
        {t("admin_dashboard.active_users.note")}
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
  const S_NEW_USERS = t("admin_dashboard.trends.series.new_users");
  const S_ACTIVE_USERS = t("admin_dashboard.trends.series.active_users");
  const messagesData = trends.messages.map((d) => ({ ...d, type: S_MESSAGES }));
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
    domain: [S_MESSAGES, S_NEW_USERS, S_ACTIVE_USERS],
    range: ["#1677ff", "#fa8c16", "#52c41a"],
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

        <PlatformActivityCard />
        <ModuleUsageCard />
      </div>
    </>
  );
}

/** Map event_name → antd icon for the module usage card. */
function _eventIcon(name: string) {
  switch (name) {
    case "search":       return <SearchOutlined />;
    case "chat":         return <RobotOutlined />;
    case "read":         return <ReadOutlined />;
    case "source_click": return <LinkOutlined />;
    case "cbeta-shortcut": return <ThunderboltOutlined />;
    default:             return <DatabaseOutlined />;
  }
}

function ModuleUsageCard() {
  const { t } = useTranslation();
  const [days, setDays] = useState<number>(7);
  const { data, isLoading } = useQuery({
    queryKey: ["adminModuleUsage", days],
    queryFn: () => getAdminModuleUsage(days),
    staleTime: 300_000,
  });

  return (
    <Card
      title={t("admin_dashboard.module_usage.title")}
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
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t("admin_dashboard.module_usage.subtitle")}
          </Text>
          <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
            {data.events.map((ev: ModuleEventItem) => (
              <Col xs={12} sm={6} key={ev.event_name}>
                <Statistic
                  title={adminLabel(t, moduleEventLabelKeyMap[ev.event_name], ev.label)}
                  value={ev.count}
                  prefix={_eventIcon(ev.event_name)}
                />
              </Col>
            ))}
          </Row>

          {data.answer_quality && (
            <div style={{ marginTop: 8, marginBottom: 16 }}>
              <Text strong>{t("admin_dashboard.answer_quality.title")}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t("admin_dashboard.answer_quality.subtitle")}
              </Text>
              <Row gutter={[16, 16]} style={{ marginTop: 4 }}>
                <Col xs={12} sm={8}>
                  <Tooltip title={t("admin_dashboard.answer_quality.citation_click_tooltip", {
                    clicks: data.answer_quality.citation_click,
                    questions: data.answer_quality.chat_questions,
                  })}>
                    <Statistic
                      title={t("admin_dashboard.answer_quality.citation_click_rate")}
                      value={data.answer_quality.citation_click_rate ?? "—"}
                      suffix={data.answer_quality.citation_click_rate == null ? "" : "%"}
                    />
                  </Tooltip>
                </Col>
                <Col xs={12} sm={8}>
                  <Tooltip title={t("admin_dashboard.answer_quality.copy_tooltip", {
                    copies: data.answer_quality.chat_copy,
                    questions: data.answer_quality.chat_questions,
                  })}>
                    <Statistic
                      title={t("admin_dashboard.answer_quality.copy_rate")}
                      value={data.answer_quality.copy_rate ?? "—"}
                      suffix={data.answer_quality.copy_rate == null ? "" : "%"}
                    />
                  </Tooltip>
                </Col>
                <Col xs={12} sm={8}>
                  <Tooltip title={t("admin_dashboard.answer_quality.retry_tooltip", {
                    retries: data.answer_quality.chat_retry,
                    questions: data.answer_quality.chat_questions,
                  })}>
                    <Statistic
                      title={t("admin_dashboard.answer_quality.retry_rate")}
                      value={data.answer_quality.retry_rate ?? "—"}
                      suffix={data.answer_quality.retry_rate == null ? "" : "%"}
                      valueStyle={{ color: (data.answer_quality.retry_rate ?? 0) > 5 ? "var(--fj-danger)" : undefined }}
                    />
                  </Tooltip>
                </Col>
              </Row>
            </div>
          )}

          {data.top_search_keywords.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t("admin_dashboard.module_usage.top_keywords")}
              </Text>
              <div style={{ marginTop: 8 }}>
                {data.top_search_keywords.map((kw, i) => (
                  <div
                    key={`${kw.keyword}-${i}`}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "4px 0",
                      borderBottom: i < data.top_search_keywords.length - 1
                        ? "1px solid #f0f0f0"
                        : undefined,
                    }}
                  >
                    <span>
                      <Text type="secondary" style={{ marginRight: 8 }}>
                        {i + 1}.
                      </Text>
                      {kw.keyword}
                    </span>
                    <span style={{ color: "var(--fj-text-secondary)" }}>{t("admin_dashboard.unit.times", { count: kw.count })}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function PlatformActivityCard() {
  const { t } = useTranslation();
  const [days, setDays] = useState<number>(7);
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

      <Text type="secondary" style={{ fontSize: 12 }}>{t("admin_dashboard.platform_activity.chat_section")}</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title={t("admin_dashboard.platform_activity.new_sessions")} value={data.chat.total_sessions} prefix={<CommentOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title={t("admin_dashboard.platform_activity.new_messages")} value={data.chat.total_messages} prefix={<MessageOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title={t("admin_dashboard.platform_activity.feedback_rate_tooltip", {
            rated: ratedCount,
            positive: data.chat.positive_feedback,
            negative: data.chat.negative_feedback,
            total: data.chat.total_messages,
          })}>
            <Statistic title={t("admin_dashboard.platform_activity.feedback_rate")} value={feedbackRate} prefix={<LikeOutlined />} />
          </Tooltip>
        </Col>
        <Col xs={12} sm={6}>
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
        <Col xs={12} sm={6}>
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
      </Row>

      {/* 阅读次数仅记录登录用户；全站(含匿名)阅读量见「板块使用情况」的「在线阅读」。
          已移除「阅读经文数(unique)」「本期新增经文」(批量灌入、平时恒为0,信号低)。 */}
      <Text type="secondary" style={{ fontSize: 12 }}>{t("admin_dashboard.reading.section")}</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title={t("admin_dashboard.reading.total_reads")} value={data.reading.total_reads} prefix={<BookOutlined />} />
        </Col>
      </Row>

      {data.reading.top_texts.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4>{t("admin_dashboard.reading.top_texts")}</h4>
          {data.reading.top_texts.map((text, i) => (
            <div
              key={`${text.text_id}-${i}`}
              style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}
            >
              <Link to={`/texts/${text.text_id}`}>{text.title_zh}</Link>
              <span style={{ color: "var(--fj-text-secondary)" }}>{t("admin_dashboard.unit.times", { count: text.read_count })}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
