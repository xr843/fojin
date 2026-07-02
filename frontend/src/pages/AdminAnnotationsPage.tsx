import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Button, Space, Select, Typography, message } from "antd";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import {
  getAdminAnnotations,
  reviewAnnotation,
  type AdminAnnotationItem,
} from "../api/client";
import { adminLabel, formatAdminDate } from "./adminI18n";

const statusColorMap: Record<string, string> = {
  draft: "default",
  pending: "orange",
  approved: "green",
  rejected: "red",
};

const statusLabelKeyMap: Record<string, string> = {
  draft: "admin_crud.annotation.status.draft",
  pending: "admin_crud.annotation.status.pending",
  approved: "admin_crud.annotation.status.approved",
  rejected: "admin_crud.annotation.status.rejected",
};

const typeLabelKeyMap: Record<string, string> = {
  note: "admin_crud.annotation.type.note",
  correction: "admin_crud.annotation.type.correction",
  tag: "admin_crud.annotation.type.tag",
};

export default function AdminAnnotationsPage() {
  const { t, i18n } = useTranslation();
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
      message.error(t("admin_crud.annotation.load_error"));
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleReview = async (id: number, action: string) => {
    try {
      await reviewAnnotation(id, { action });
      message.success(action === "approve" ? t("admin_crud.annotation.approved") : t("admin_crud.annotation.rejected"));
      fetchData();
    } catch {
      message.error(t("admin_crud.common.action_failed"));
    }
  };

  const columns = [
    {
      title: t("admin_crud.column.type"),
      dataIndex: "annotation_type",
      width: 80,
      render: (value: string) => adminLabel(t, typeLabelKeyMap[value], value),
    },
    {
      title: t("admin_crud.column.content"),
      dataIndex: "content",
      ellipsis: true,
    },
    {
      title: t("admin_crud.column.user"),
      dataIndex: "username",
      width: 120,
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
              {t("admin_crud.annotation.approve")}
            </Button>
            <Button
              danger
              size="small"
              icon={<CloseOutlined />}
              onClick={() => handleReview(record.id, "reject")}
            >
              {t("admin_crud.annotation.reject")}
            </Button>
          </Space>
        ) : null,
    },
  ];

  return (
    <>
      <Helmet>
        <title>{t("admin_crud.annotation.page_title")}</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {t("admin_crud.annotation.heading")}
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
              { value: "pending", label: t("admin_crud.annotation.status.pending") },
              { value: "approved", label: t("admin_crud.annotation.status.approved") },
              { value: "rejected", label: t("admin_crud.annotation.status.rejected") },
              { value: "draft", label: t("admin_crud.annotation.status.draft") },
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
