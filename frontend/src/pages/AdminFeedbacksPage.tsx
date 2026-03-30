import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Space, Select, Typography, message, Button, Modal, Input } from "antd";
import { Helmet } from "react-helmet-async";
import {
  getAdminFeedbacks,
  updateFeedbackStatus,
  replyFeedback,
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
  const [replyModal, setReplyModal] = useState<AdminFeedbackItem | null>(null);
  const [replyText, setReplyText] = useState("");
  const [replying, setReplying] = useState(false);

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

  const openReplyModal = (record: AdminFeedbackItem) => {
    setReplyModal(record);
    setReplyText(record.admin_reply || "");
  };

  const handleReply = async () => {
    if (!replyModal || !replyText.trim()) return;
    setReplying(true);
    try {
      await replyFeedback(replyModal.id, replyText.trim());
      message.success("回复已发送，用户将收到通知");
      setReplyModal(null);
      setReplyText("");
      fetchData();
    } catch {
      message.error("回复失败");
    } finally {
      setReplying(false);
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
      width: 260,
      render: (_: unknown, record: AdminFeedbackItem) => (
        <Space>
          <Button
            type={record.admin_reply ? "default" : "primary"}
            size="small"
            onClick={() => openReplyModal(record)}
          >
            {record.admin_reply ? "查看回复" : "回复"}
          </Button>
          {record.status === "pending" && (
            <Button
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

      <Modal
        title={replyModal ? `回复 ${replyModal.username} 的反馈` : "回复"}
        open={!!replyModal}
        onCancel={() => { setReplyModal(null); setReplyText(""); }}
        onOk={handleReply}
        okText="发送回复"
        cancelText="取消"
        confirmLoading={replying}
        okButtonProps={{ disabled: !replyText.trim() }}
      >
        {replyModal && (
          <div style={{ marginBottom: 16 }}>
            <Typography.Text type="secondary">用户反馈：</Typography.Text>
            <div style={{
              background: "#faf8f5", padding: "8px 12px", borderRadius: 6,
              marginTop: 4, fontSize: 13, lineHeight: 1.6,
            }}>
              {replyModal.content}
            </div>
            {replyModal.contact && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#999" }}>
                联系方式：{replyModal.contact}
              </div>
            )}
          </div>
        )}
        <Typography.Text type="secondary">管理员回复：</Typography.Text>
        <Input.TextArea
          rows={4}
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder="输入回复内容，用户将在通知中心收到此回复"
          maxLength={2000}
          showCount
          style={{ marginTop: 4 }}
        />
        {replyModal?.replied_at && (
          <div style={{ marginTop: 8, fontSize: 12, color: "#999" }}>
            上次回复时间：{new Date(replyModal.replied_at).toLocaleString("zh-CN")}
          </div>
        )}
      </Modal>
    </>
  );
}
