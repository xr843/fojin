import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Space, Select, Typography, message, Button, Modal, Input } from "antd";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import {
  getAdminFeedbacks,
  updateFeedbackStatus,
  replyFeedback,
  type AdminFeedbackItem,
} from "../api/client";
import { adminLabel, formatAdminDate } from "./adminI18n";

const statusColorMap: Record<string, string> = {
  pending: "orange",
  read: "blue",
  resolved: "green",
};

const statusLabelKeyMap: Record<string, string> = {
  pending: "admin_crud.feedback.status.pending",
  read: "admin_crud.feedback.status.read",
  resolved: "admin_crud.feedback.status.resolved",
};

export default function AdminFeedbacksPage() {
  const { t, i18n } = useTranslation();
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
      message.error(t("admin_crud.feedback.load_error"));
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStatusChange = async (id: number, status: string) => {
    try {
      await updateFeedbackStatus(id, status);
      message.success(t("admin_crud.feedback.status_updated"));
      fetchData();
    } catch {
      message.error(t("admin_crud.common.action_failed"));
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
      message.success(t("admin_crud.feedback.reply_sent"));
      setReplyModal(null);
      setReplyText("");
      fetchData();
    } catch {
      message.error(t("admin_crud.feedback.reply_failed"));
    } finally {
      setReplying(false);
    }
  };

  const columns = [
    {
      title: t("admin_crud.column.user"),
      dataIndex: "username",
      width: 120,
    },
    {
      title: t("admin_crud.column.feedback"),
      dataIndex: "content",
      ellipsis: true,
    },
    {
      title: t("admin_crud.column.contact"),
      dataIndex: "contact",
      width: 180,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("admin_crud.column.status"),
      dataIndex: "status",
      width: 100,
      render: (s: string) => (
        <Tag color={statusColorMap[s]}>{adminLabel(t, statusLabelKeyMap[s], s)}</Tag>
      ),
    },
    {
      title: t("admin_crud.column.submitted_at"),
      dataIndex: "created_at",
      width: 170,
      render: (value: string) => formatAdminDate(value, i18n.language),
    },
    {
      title: t("admin_crud.column.actions"),
      width: 260,
      render: (_: unknown, record: AdminFeedbackItem) => (
        <Space>
          <Button
            type={record.admin_reply ? "default" : "primary"}
            size="small"
            onClick={() => openReplyModal(record)}
          >
            {record.admin_reply ? t("admin_crud.feedback.view_reply") : t("admin_crud.feedback.reply")}
          </Button>
          {record.status === "pending" && (
            <Button
              size="small"
              onClick={() => handleStatusChange(record.id, "read")}
            >
              {t("admin_crud.feedback.mark_read")}
            </Button>
          )}
          {record.status !== "resolved" && (
            <Button
              size="small"
              onClick={() => handleStatusChange(record.id, "resolved")}
            >
              {t("admin_crud.feedback.resolve")}
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <Helmet>
        <title>{t("admin_crud.feedback.page_title")}</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {t("admin_crud.feedback.heading")}
          </Typography.Title>
          <Select
            style={{ width: 140 }}
            placeholder={t("admin_crud.common.filter_status")}
            allowClear
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v);
              setPage(1);
            }}
            options={[
              { value: "pending", label: t("admin_crud.feedback.status.pending") },
              { value: "read", label: t("admin_crud.feedback.status.read") },
              { value: "resolved", label: t("admin_crud.feedback.status.resolved") },
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
            showTotal: (count) => t("admin_crud.common.total_rows", { count }),
          }}
          size="middle"
        />
      </div>

      <Modal
        title={replyModal ? t("admin_crud.feedback.reply_modal_title", { username: replyModal.username }) : t("admin_crud.feedback.reply")}
        open={!!replyModal}
        onCancel={() => { setReplyModal(null); setReplyText(""); }}
        onOk={handleReply}
        okText={t("admin_crud.feedback.send_reply")}
        cancelText={t("admin_crud.common.cancel")}
        confirmLoading={replying}
        okButtonProps={{ disabled: !replyText.trim() }}
      >
        {replyModal && (
          <div style={{ marginBottom: 16 }}>
            <Typography.Text type="secondary">{t("admin_crud.feedback.user_feedback_label")}</Typography.Text>
            <div style={{
              background: "#faf8f5", padding: "8px 12px", borderRadius: 6,
              marginTop: 4, fontSize: 13, lineHeight: 1.6,
            }}>
              {replyModal.content}
            </div>
            {replyModal.contact && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#999" }}>
                {t("admin_crud.feedback.contact_label", { contact: replyModal.contact })}
              </div>
            )}
          </div>
        )}
        <Typography.Text type="secondary">{t("admin_crud.feedback.admin_reply_label")}</Typography.Text>
        <Input.TextArea
          rows={4}
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder={t("admin_crud.feedback.reply_placeholder")}
          maxLength={2000}
          showCount
          style={{ marginTop: 4 }}
        />
        {replyModal?.replied_at && (
          <div style={{ marginTop: 8, fontSize: 12, color: "#999" }}>
            {t("admin_crud.feedback.last_reply_at", { date: formatAdminDate(replyModal.replied_at, i18n.language) })}
          </div>
        )}
      </Modal>
    </>
  );
}
