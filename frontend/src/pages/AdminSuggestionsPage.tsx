import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Button, Space, Select, message, Typography } from "antd";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import {
  getSourceSuggestions,
  updateSuggestionStatus,
  type SourceSuggestionItem,
} from "../api/client";

const statusColorMap: Record<string, string> = {
  pending: "orange",
  accepted: "green",
  rejected: "red",
};

const statusLabelMap: Record<string, string> = {
  pending: "待审核",
  accepted: "已采纳",
  rejected: "已拒绝",
};

export default function AdminSuggestionsPage() {
  const [items, setItems] = useState<SourceSuggestionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getSourceSuggestions(page, 20, statusFilter);
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载推荐列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStatusChange = async (id: number, status: string) => {
    try {
      await updateSuggestionStatus(id, status);
      message.success(status === "accepted" ? "已采纳" : "已拒绝");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const columns = [
    {
      title: "名称",
      dataIndex: "name",
      width: 200,
    },
    {
      title: "URL",
      dataIndex: "url",
      ellipsis: true,
      render: (url: string) => (
        <a href={url} target="_blank" rel="noopener noreferrer">
          {url}
        </a>
      ),
    },
    {
      title: "描述",
      dataIndex: "description",
      ellipsis: true,
      width: 300,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) => (
        <Tag color={statusColorMap[status]}>{statusLabelMap[status] || status}</Tag>
      ),
    },
    {
      title: "提交时间",
      dataIndex: "submitted_at",
      width: 180,
      render: (t: string | null) => (t ? new Date(t).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "操作",
      width: 160,
      render: (_: unknown, record: SourceSuggestionItem) =>
        record.status === "pending" ? (
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<CheckOutlined />}
              onClick={() => handleStatusChange(record.id, "accepted")}
            >
              采纳
            </Button>
            <Button
              danger
              size="small"
              icon={<CloseOutlined />}
              onClick={() => handleStatusChange(record.id, "rejected")}
            >
              拒绝
            </Button>
          </Space>
        ) : null,
    },
  ];

  return (
    <>
      <Helmet>
        <title>推荐数据源管理 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space
          style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            推荐数据源管理
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
              { value: "pending", label: "待审核" },
              { value: "accepted", label: "已采纳" },
              { value: "rejected", label: "已拒绝" },
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
