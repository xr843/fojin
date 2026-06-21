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

const { Text } = Typography;

function DeltaSuffix({ today, yesterday }: { today: number; yesterday: number }) {
  const diff = today - yesterday;
  const Arrow = diff >= 0 ? ArrowUpOutlined : ArrowDownOutlined;
  const todayColor = today > 0 ? "#52c41a" : "#999";
  const diffColor = diff > 0 ? "#52c41a" : diff < 0 ? "#ff4d4f" : "#999";
  return (
    <Tooltip title={`今日 +${today} / 昨日 +${yesterday}`}>
      <span style={{ fontSize: 13, color: todayColor, marginLeft: 4 }}>+{today}</span>
      <span style={{ fontSize: 12, color: diffColor, marginLeft: 6 }}>
        <Arrow style={{ fontSize: 10 }} /> {Math.abs(diff)}
      </span>
    </Tooltip>
  );
}

function PendingCard({ overview }: { overview: AdminOverview }) {
  const total = overview.pending_suggestions + overview.pending_annotations;
  const tip = `源建议 ${overview.pending_suggestions} 条 · 标注 ${overview.pending_annotations} 条`;
  return (
    <Card>
      <Tooltip title={tip}>
        <Statistic
          title="待审核"
          value={total}
          prefix={<WarningOutlined />}
          valueStyle={{ color: total > 0 ? "#faad14" : undefined }}
          suffix={
            total > 0 ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {overview.pending_suggestions}建议 / {overview.pending_annotations}标注
              </Text>
            ) : (
              <Text type="success" style={{ fontSize: 12 }}>✓ 已清空</Text>
            )
          }
        />
      </Tooltip>
    </Card>
  );
}

function ActiveUsersCard({ date, onDateChange }: { date: string | null; onDateChange: (d: string) => void }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["adminActiveUsers", date],
    queryFn: () => getAdminActiveUsers(date!),
    enabled: !!date,
    staleTime: 60_000,
  });

  const columns = [
    {
      title: "用户",
      key: "user",
      render: (_: unknown, r: ActiveUserDetail) => (
        <Link to={`/admin/users?q=${encodeURIComponent(r.username ?? String(r.user_id))}`}>
          {r.display_name || r.username || `#${r.user_id}`}
        </Link>
      ),
    },
    { title: "邮箱", dataIndex: "email", key: "email", render: (v: string | null) => v || "—" },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      render: (v: string) => (v === "admin" ? <Tag color="gold">管理员</Tag> : <Tag>用户</Tag>),
    },
    {
      title: "提问数",
      dataIndex: "chat_messages",
      key: "chat_messages",
      sorter: (a: ActiveUserDetail, b: ActiveUserDetail) => a.chat_messages - b.chat_messages,
      defaultSortOrder: "descend" as const,
    },
    {
      title: "读经数",
      dataIndex: "texts_read",
      key: "texts_read",
      sorter: (a: ActiveUserDetail, b: ActiveUserDetail) => a.texts_read - b.texts_read,
    },
    {
      title: "自带 Key",
      dataIndex: "api_provider",
      key: "api_provider",
      render: (v: string | null) => (v ? <Tag color="green">{v}</Tag> : "—"),
    },
    {
      title: "最后活跃",
      dataIndex: "last_active_at",
      key: "last_active_at",
      render: (v: string | null) =>
        v ? new Date(v).toLocaleString("zh-CN", { hour12: false }) : "—",
    },
  ];

  return (
    <Card
      title={`当日活跃用户${data ? `（${data.total} 人）` : ""}`}
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
        <Empty description="加载失败" />
      ) : isLoading ? (
        <div style={{ textAlign: "center", padding: 24 }}><Spin /></div>
      ) : !data || data.users.length === 0 ? (
        <Empty description="当日无活跃用户（登录用户的提问/读经）" />
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
        “活跃”= 当天发过提问或读过经文的登录用户（与上方趋势图口径一致）；匿名访客无身份不计入。点击趋势图上的点可切换日期。
        本表为实时数据，趋势图有约 5 分钟缓存，查看“今天”时两者人数可能略有出入。
      </Text>
    </Card>
  );
}

export default function AdminDashboardPage() {
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
    message.error("加载统计数据失败");
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Empty description="加载失败，请刷新重试" />
      </div>
    );
  }

  const overview = overviewQuery.data!;
  const trends = trendsQuery.data!;

  // Dual Y-axis: 消息数 (tens~hundreds) on the left, 新增用户 + 活跃用户
  // (single digits ~ teens) on the right. On a shared axis the two
  // small-magnitude series flatten to the baseline and can't be read.
  // Series labels: defined once so the chart data, the legend and the shared
  // color domain below all reference the exact same strings (a mismatch would
  // silently drop a series back to a default color).
  const S_MESSAGES = "消息数";
  const S_NEW_USERS = "新增用户";
  const S_ACTIVE_USERS = "活跃用户";
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
  const chartConfig = {
    xField: "date",
    height: 360,
    legend: { color: { itemMarker: "round" } },
    axis: { x: { labelAutoRotate: false } },
    children: [
      {
        data: messagesData,
        type: "line",
        yField: "count",
        colorField: "type",
        smooth: true,
        scale: { color: seriesColor },
      },
      {
        data: usersData,
        type: "line",
        yField: "count",
        colorField: "type",
        smooth: true,
        axis: { y: { position: "right" } },
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
    ? new Date(overview.last_updated).toLocaleString("zh-CN", { hour12: false })
    : "—";

  return (
    <>
      <Helmet>
        <title>管理后台 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Row gutter={[16, 16]}>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="总用户数"
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
                title="聊天会话"
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
                title="总消息数"
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
          title="最近 30 天趋势"
          style={{ marginTop: 16 }}
          extra={<Text type="secondary" style={{ fontSize: 12 }}>更新于 {lastUpdated}</Text>}
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
  const [days, setDays] = useState<number>(7);
  const { data, isLoading } = useQuery({
    queryKey: ["adminModuleUsage", days],
    queryFn: () => getAdminModuleUsage(days),
    staleTime: 300_000,
  });

  return (
    <Card
      title="板块使用情况"
      style={{ marginTop: 16 }}
      extra={
        <Segmented
          value={days}
          onChange={(v) => setDays(v as number)}
          options={[
            { label: "7天", value: 7 },
            { label: "14天", value: 14 },
            { label: "30天", value: 30 },
          ]}
        />
      }
    >
      {isLoading ? (
        <Spin />
      ) : !data || data.events.length === 0 ? (
        <Empty description="暂无 Umami 数据" />
      ) : (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>
            各板块事件量（全站访客，含未登录）
          </Text>
          <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
            {data.events.map((ev: ModuleEventItem) => (
              <Col xs={12} sm={6} key={ev.event_name}>
                <Statistic
                  title={ev.label}
                  value={ev.count}
                  prefix={_eventIcon(ev.event_name)}
                />
              </Col>
            ))}
          </Row>

          {data.top_search_keywords.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                热门检索词（Top 10）
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
                    <span style={{ color: "#999" }}>{kw.count} 次</span>
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
  const [days, setDays] = useState<number>(7);
  const { data, isLoading } = useQuery({
    queryKey: ["platformActivity", days],
    queryFn: () => getPlatformActivity({ days }),
    staleTime: 300_000,
  });

  if (isLoading) {
    return (
      <Card title="平台活跃度" style={{ marginTop: 16 }}>
        <Spin />
      </Card>
    );
  }
  if (!data) {
    return (
      <Card title="平台活跃度" style={{ marginTop: 16 }}>
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
      title="平台活跃度"
      style={{ marginTop: 16 }}
      extra={
        <Segmented
          value={days}
          onChange={(v) => setDays(v as number)}
          options={[
            { label: "7天", value: 7 },
            { label: "14天", value: 14 },
            { label: "30天", value: 30 },
          ]}
        />
      }
    >
      <Text type="secondary" style={{ fontSize: 12 }}>用户</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title="新增用户" value={data.users.new_users} prefix={<UserOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="活跃用户" value={data.users.active_users} />
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title="本期活跃且在本期之前就注册的老用户（留存信号）">
            <Statistic
              title="回访用户"
              value={data.users.returning_users}
              valueStyle={{ color: data.users.returning_users > data.users.new_users ? "#52c41a" : undefined }}
            />
          </Tooltip>
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title={`${data.users.byok_active_users} 个活跃用户自带 API Key（占活跃 ${byokRate}），其余跑平台 Key`}>
            <Statistic title="自带Key" value={`${data.users.byok_active_users}（${byokRate}）`} />
          </Tooltip>
        </Col>
      </Row>

      <Text type="secondary" style={{ fontSize: 12 }}>对话</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title="新增会话" value={data.chat.total_sessions} prefix={<CommentOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="新增消息" value={data.chat.total_messages} prefix={<MessageOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title={`${ratedCount} 条已评价（👍${data.chat.positive_feedback} / 👎${data.chat.negative_feedback}）/ ${data.chat.total_messages} 条消息`}>
            <Statistic title="反馈率" value={feedbackRate} prefix={<LikeOutlined />} />
          </Tooltip>
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title={`👍${data.chat.positive_feedback} / 👎${data.chat.negative_feedback}（共 ${ratedCount} 条评价）`}>
            <Statistic
              title="好评率"
              value={positiveRate}
              valueStyle={{ color: ratedCount > 0 && data.chat.positive_feedback >= data.chat.negative_feedback ? "#52c41a" : undefined }}
            />
          </Tooltip>
        </Col>
        <Col xs={12} sm={6}>
          <Tooltip title={`${data.chat.assistant_no_source} / ${data.chat.assistant_messages} 条 AI 回答未引用经文来源。含三类：RAG 没召回到经文（真·检索缺口）、寒暄/身份类提问（本就无需引经）、AI 服务出错。越低越好，用作粗略质量信号`}>
            <Statistic
              title="未引经率"
              value={failRate}
              valueStyle={{ color: data.chat.assistant_messages > 0 && data.chat.assistant_no_source / data.chat.assistant_messages > 0.3 ? "#cf1322" : undefined }}
            />
          </Tooltip>
        </Col>
      </Row>

      {/* 阅读次数仅记录登录用户；全站(含匿名)阅读量见「板块使用情况」的「在线阅读」。
          已移除「阅读经文数(unique)」「本期新增经文」(批量灌入、平时恒为0,信号低)。 */}
      <Text type="secondary" style={{ fontSize: 12 }}>阅读（仅登录用户）</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title="阅读次数" value={data.reading.total_reads} prefix={<BookOutlined />} />
        </Col>
      </Row>

      {data.reading.top_texts.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4>热门阅读经文</h4>
          {data.reading.top_texts.map((t, i) => (
            <div
              key={`${t.text_id}-${i}`}
              style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}
            >
              <Link to={`/texts/${t.text_id}`}>{t.title_zh}</Link>
              <span style={{ color: "#999" }}>{t.read_count} 次</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
