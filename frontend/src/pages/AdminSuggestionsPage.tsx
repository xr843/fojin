import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Button, Space, Select, message, Typography, Popconfirm } from "antd";
import { CheckOutlined, CloseOutlined, DeleteOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import {
  getSourceSuggestions,
  updateSuggestionStatus,
  deleteSourceSuggestion,
  type SourceSuggestionItem,
} from "../api/client";
import { adminLabel, formatAdminDate } from "./adminI18n";

const statusColorMap: Record<string, string> = {
  pending: "orange",
  accepted: "green",
  rejected: "red",
};

const statusLabelKeyMap: Record<string, string> = {
  pending: "admin_crud.suggestion.status.pending",
  accepted: "admin_crud.suggestion.status.accepted",
  rejected: "admin_crud.suggestion.status.rejected",
};

export default function AdminSuggestionsPage() {
  const { t, i18n } = useTranslation();
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
      message.error(t("admin_crud.suggestion.load_error"));
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleStatusChange = async (id: number, status: string) => {
    try {
      await updateSuggestionStatus(id, status);
      message.success(status === "accepted" ? t("admin_crud.suggestion.accepted") : t("admin_crud.suggestion.rejected"));
      fetchData();
    } catch {
      message.error(t("admin_crud.common.action_failed"));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteSourceSuggestion(id);
      message.success(t("admin_crud.suggestion.deleted"));
      fetchData();
    } catch {
      message.error(t("admin_crud.suggestion.delete_failed"));
    }
  };

  const columns = [
    {
      title: t("admin_crud.column.name"),
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
      title: t("admin_crud.column.description"),
      dataIndex: "description",
      ellipsis: true,
      width: 300,
    },
    {
      title: t("admin_crud.column.status"),
      dataIndex: "status",
      width: 100,
      render: (status: string) => (
        <Tag color={statusColorMap[status]}>{adminLabel(t, statusLabelKeyMap[status], status)}</Tag>
      ),
    },
    {
      title: t("admin_crud.column.submitted_at"),
      dataIndex: "submitted_at",
      width: 180,
      render: (value: string | null) => formatAdminDate(value, i18n.language),
    },
    {
      title: t("admin_crud.column.actions"),
      width: 220,
      render: (_: unknown, record: SourceSuggestionItem) => (
        <Space>
          {record.status === "pending" && (
            <>
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                onClick={() => handleStatusChange(record.id, "accepted")}
              >
                {t("admin_crud.suggestion.accept")}
              </Button>
              <Button
                danger
                size="small"
                icon={<CloseOutlined />}
                onClick={() => handleStatusChange(record.id, "rejected")}
              >
                {t("admin_crud.suggestion.reject")}
              </Button>
            </>
          )}
          <Popconfirm
            title={t("admin_crud.suggestion.confirm_delete")}
            onConfirm={() => handleDelete(record.id)}
            okText={t("admin_crud.common.delete")}
            cancelText={t("admin_crud.common.cancel")}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              {t("admin_crud.common.delete")}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Helmet>
        <title>{t("admin_crud.suggestion.page_title")}</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space
          style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            {t("admin_crud.suggestion.heading")}
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
              { value: "pending", label: t("admin_crud.suggestion.status.pending") },
              { value: "accepted", label: t("admin_crud.suggestion.status.accepted") },
              { value: "rejected", label: t("admin_crud.suggestion.status.rejected") },
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
    </>
  );
}
