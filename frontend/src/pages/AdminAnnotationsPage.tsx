import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Button, Space, Select, Typography, message } from "antd";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import {
  getAdminAnnotations,
  reviewAnnotation,
  type AdminAnnotationItem,
} from "../api/client";

const statusColorMap: Record<string, string> = {
  draft: "default",
  pending: "orange",
  approved: "green",
  rejected: "red",
};

const statusLabelMap: Record<string, string> = {
  draft: "草稿",
  pending: "待审核",
  approved: "已通过",
  rejected: "已拒绝",
};

const typeLabel: Record<string, string> = {
  note: "笔记",
  correction: "勘误",
  tag: "标签",
};

export default function AdminAnnotationsPage() {
  const [items, setItems] = useState<AdminAnnotationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>("pending");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminAnnotations({
        page,
        size: 20,
        status: statusFilter,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载标注列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleReview = async (id: number, action: string) => {
    try {
      await reviewAnnotation(id, { action });
      message.success(action === "approve" ? "已通过" : "已拒绝");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const columns = [
    {
      title: "类型",
      dataIndex: "annotation_type",
      width: 80,
      render: (t: string) => typeLabel[t] || t,
    },
    {
      title: "内容",
      dataIndex: "content",
      ellipsis: true,
    },
    {
      title: "用户",
      dataIndex: "username",
      width: 120,
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
      width: 180,
      render: (_: unknown, record: AdminAnnotationItem) =>
        record.status === "pending" ? (
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<CheckOutlined />}
              onClick={() => handleReview(record.id, "approve")}
            >
              通过
            </Button>
            <Button
              danger
              size="small"
              icon={<CloseOutlined />}
              onClick={() => handleReview(record.id, "reject")}
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
        <title>标注审核 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            标注审核
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
              { value: "approved", label: "已通过" },
              { value: "rejected", label: "已拒绝" },
              { value: "draft", label: "草稿" },
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
