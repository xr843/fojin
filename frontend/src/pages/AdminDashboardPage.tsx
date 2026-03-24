import { useEffect, useState } from "react";
import { Card, Col, Row, Statistic, Spin, message } from "antd";
import {
  UserOutlined,
  MessageOutlined,
  CommentOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { Line } from "@ant-design/charts";
import {
  getAdminOverview,
  getAdminTrends,
  type AdminOverview,
  type AdminTrends,
} from "../api/client";

export default function AdminDashboardPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [trends, setTrends] = useState<AdminTrends | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getAdminOverview(), getAdminTrends(30)])
      .then(([ov, tr]) => {
        setOverview(ov);
        setTrends(tr);
      })
      .catch(() => message.error("加载统计数据失败"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!overview || !trends) return null;

  const chartData = [
    ...trends.registrations.map((d) => ({ ...d, type: "新注册" })),
    ...trends.messages.map((d) => ({ ...d, type: "消息数" })),
    ...trends.active_users.map((d) => ({ ...d, type: "活跃用户" })),
  ];

  const lineConfig = {
    data: chartData,
    xField: "date",
    yField: "count",
    colorField: "type",
    smooth: true,
    height: 360,
    axis: {
      x: { labelAutoRotate: false },
    },
  };

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
                suffix={<span style={{ fontSize: 13, color: "#52c41a" }}>+{overview.new_users_today}</span>}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="聊天会话"
                value={overview.total_sessions}
                prefix={<CommentOutlined />}
                suffix={<span style={{ fontSize: 13, color: "#52c41a" }}>+{overview.new_sessions_today}</span>}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="总消息数"
                value={overview.total_messages}
                prefix={<MessageOutlined />}
                suffix={<span style={{ fontSize: 13, color: "#52c41a" }}>+{overview.new_messages_today}</span>}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card>
              <Statistic
                title="待审核"
                value={overview.pending_suggestions + overview.pending_annotations}
                prefix={<WarningOutlined />}
                valueStyle={{ color: overview.pending_suggestions + overview.pending_annotations > 0 ? "#faad14" : undefined }}
              />
            </Card>
          </Col>
        </Row>

        <Card title="最近 30 天趋势" style={{ marginTop: 16 }}>
          <Line {...lineConfig} />
        </Card>
      </div>
    </>
  );
}
