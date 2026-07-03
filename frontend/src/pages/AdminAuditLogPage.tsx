import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Select, Typography, message } from "antd";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { getAdminAuditLog, type AdminAuditLogItem } from "../api/client";
import { adminLabel, formatAdminDate } from "./adminI18n";

const actionLabelKeyMap: Record<string, string> = {
  update_user: "admin_crud.audit.action.update_user",
  update_suggestion: "admin_crud.audit.action.update_suggestion",
  delete_suggestion: "admin_crud.audit.action.delete_suggestion",
};

const actionColor: Record<string, string> = {
  update_user: "blue",
  update_suggestion: "green",
  delete_suggestion: "red",
};

const fieldLabelKeyMap: Record<string, string> = {
  role: "admin_crud.audit.field.role",
  is_active: "admin_crud.audit.field.is_active",
  status: "admin_crud.audit.field.status",
  name: "admin_crud.audit.field.name",
  url: "admin_crud.audit.field.url",
};

function renderValue(t: TFunction, v: unknown): string {
  if (v === true) return t("admin_crud.audit.value.enabled");
  if (v === false) return t("admin_crud.audit.value.disabled");
  if (v === null || v === undefined) return "—";
  return String(v);
}

function renderDetail(t: TFunction, detail: Record<string, unknown> | null) {
  if (!detail || Object.keys(detail).length === 0) return <span style={{ color: "#999" }}>—</span>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {Object.entries(detail).map(([key, value]) => {
        const label = adminLabel(t, fieldLabelKeyMap[key], key);
        if (value && typeof value === "object" && "from" in value && "to" in value) {
          const diff = value as { from: unknown; to: unknown };
          return (
            <span key={key} style={{ fontSize: 13 }}>
              {t("admin_crud.audit.detail_diff", { label, from: renderValue(t, diff.from), to: renderValue(t, diff.to) })}
            </span>
          );
        }
        return (
          <span key={key} style={{ fontSize: 13 }}>
            {t("admin_crud.audit.detail_value", { label, value: renderValue(t, value) })}
          </span>
        );
      })}
    </div>
  );
}

export default function AdminAuditLogPage() {
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<AdminAuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState<string | undefined>(undefined);

  const fetchData = useCallback(() => {
    return getAdminAuditLog({ page, size: 20, action: actionFilter })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        message.error(t("admin_crud.audit.load_error"));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [page, actionFilter, t]);

  // Spinner state for param changes is adjusted during render; the fetch
  // effect below only sets state from promise callbacks.
  const queryKey = `${page}|${actionFilter}`;
  const [prevQueryKey, setPrevQueryKey] = useState(queryKey);
  if (prevQueryKey !== queryKey) {
    setPrevQueryKey(queryKey);
    setLoading(true);
  }

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const columns = [
    {
      title: t("admin_crud.column.time"),
      dataIndex: "created_at",
      width: 170,
      render: (value: string) => formatAdminDate(value, i18n.language),
    },
    {
      title: t("admin_crud.column.actor"),
      dataIndex: "actor_username",
      width: 130,
      render: (name: string | null) => name || <span style={{ color: "#999" }}>{t("admin_crud.audit.deleted_user")}</span>,
    },
    {
      title: t("admin_crud.column.action"),
      dataIndex: "action",
      width: 110,
      render: (a: string) => <Tag color={actionColor[a]}>{adminLabel(t, actionLabelKeyMap[a], a)}</Tag>,
    },
    {
      title: t("admin_crud.column.target"),
      width: 150,
      render: (_: unknown, record: AdminAuditLogItem) =>
        record.target_id != null ? `${record.target_type} #${record.target_id}` : record.target_type,
    },
    {
      title: t("admin_crud.column.detail"),
      dataIndex: "detail",
      render: (detail: Record<string, unknown> | null) => renderDetail(t, detail),
    },
  ];

  return (
    <>
      <Helmet>
        <title>{t("admin_crud.audit.page_title")}</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            {t("admin_crud.audit.heading")}
          </Typography.Title>
          <Select
            style={{ width: 160 }}
            placeholder={t("admin_crud.common.filter_action")}
            allowClear
            value={actionFilter}
            onChange={(v) => {
              setActionFilter(v);
              setPage(1);
            }}
            options={[
              { value: "update_user", label: t("admin_crud.audit.action.update_user") },
              { value: "update_suggestion", label: t("admin_crud.audit.action.update_suggestion") },
              { value: "delete_suggestion", label: t("admin_crud.audit.action.delete_suggestion") },
            ]}
          />
        </div>
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
