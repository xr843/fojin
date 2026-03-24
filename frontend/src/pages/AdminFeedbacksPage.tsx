import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Space, Select, Typography, message, Button } from "antd";
import { Helmet } from "react-helmet-async";
import {
  getAdminFeedbacks,
  updateFeedbackStatus,
  type AdminFeedbackItem,
} from "../api/client";

const statusColorMap: Record<string, string> = {
  pending: "orange",
  read: "blue",
  resolved: "green",
};

const statusLabelMap: Record<string, string> = {
  pending: "待处理",
  read: "已读",
  resolved: "已解决",
};

export default function AdminFeedbacksPage() {
  const [items, setItems] = useState<AdminFeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminFeedbacks({
        page,
        size: 20,
        status: statusFilter,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载反馈列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStatusChange = async (id: number, status: string) => {
    try {
      await updateFeedbackStatus(id, status);
      message.success("状态已更新");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const columns = [
    {
      title: "用户",
      dataIndex: "username",
      width: 120,
    },
    {
      title: "反馈内容",
      dataIndex: "content",
      ellipsis: true,
    },
    {
      title: "联系方式",
      dataIndex: "contact",
      width: 180,
      render: (v: string | null) => v || "-",
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (s: string) => <Tag color={statusColorMap[s]}>{statusLabelMap[s] || s}</Tag>,
    },
    {
      title: "提交时间",
      dataIndex: "created_at",
      width: 170,
      render: (t: string) => new Date(t).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      width: 200,
      render: (_: unknown, record: AdminFeedbackItem) => (
        <Space>
          {record.status === "pending" && (
            <Button
              type="primary"
              size="small"
              onClick={() => handleStatusChange(record.id, "read")}
            >
              标为已读
            </Button>
          )}
          {record.status !== "resolved" && (
            <Button
              size="small"
              onClick={() => handleStatusChange(record.id, "resolved")}
            >
              已解决
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <Helmet>
        <title>用户反馈 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            用户反馈
          </Typography.Title>
          <Select
            style={{ width: 140 }}
            placeholder="筛选状态"
            allowClear
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v);
              setPage(1);
            }}
            options={[
              { value: "pending", label: "待处理" },
              { value: "read", label: "已读" },
              { value: "resolved", label: "已解决" },
            ]}
          />
        </Space>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="middle"
        />
      </div>
    </>
  );
}
