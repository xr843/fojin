import { useState } from "react";
import { Card, Col, Row, Statistic, Spin, Segmented, Empty, Tooltip, Typography, message } from "antd";
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
} from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Line } from "@ant-design/charts";
import {
  getAdminOverview,
  getAdminTrends,
  type AdminOverview,
  type DailyCount,
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

function MiniTrend({ title, data, color }: { title: string; data: DailyCount[]; color: string }) {
  const peak = data.reduce((m, d) => Math.max(m, d.count), 0);
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <Text type="secondary" style={{ fontSize: 13 }}>{title}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>峰值 {peak}</Text>
      </div>
      <Line
        data={data}
        xField="date"
        yField="count"
        smooth
        height={200}
        style={{ stroke: color }}
      />
    </div>
  );
}

export default function AdminDashboardPage() {
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
          {/* Three separately-scaled charts: a shared Y axis would squash
              新注册/消息数 (single digits) against 活跃用户 (hundreds). */}
          <Row gutter={[16, 16]}>
            <Col xs={24} md={8}>
              <MiniTrend title="新注册" data={trends.registrations} color="#1677ff" />
            </Col>
            <Col xs={24} md={8}>
              <MiniTrend title="消息数" data={trends.messages} color="#fa8c16" />
            </Col>
            <Col xs={24} md={8}>
              <MiniTrend title="活跃用户" data={trends.active_users} color="#13c2c2" />
            </Col>
          </Row>
        </Card>

        <PlatformActivityCard />
      </div>
    </>
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

  const fbRate =
    data.chat.total_messages > 0
      ? `${((data.chat.positive_feedback / data.chat.total_messages) * 100).toFixed(1)}%`
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
          <Tooltip title={`${data.chat.positive_feedback} 条 👍 / ${data.chat.total_messages} 条消息`}>
            <Statistic
              title="好评率"
              value={fbRate}
              prefix={<LikeOutlined />}
              valueStyle={{ color: data.chat.positive_feedback > 0 ? "#52c41a" : undefined }}
            />
          </Tooltip>
        </Col>
      </Row>

      <Text type="secondary" style={{ fontSize: 12 }}>阅读</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title="阅读次数" value={data.reading.total_reads} prefix={<BookOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="阅读经文数" value={data.reading.unique_texts_read} />
        </Col>
      </Row>

      <Text type="secondary" style={{ fontSize: 12 }}>内容</Text>
      <Row gutter={[16, 16]} style={{ marginTop: 4, marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Statistic title="新增经文" value={data.content.new_texts} prefix={<DatabaseOutlined />} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="经文总数" value={data.content.total_texts} />
        </Col>
        <Col xs={12} sm={6}>
          <Statistic title="活跃数据源" value={data.content.total_sources} />
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
