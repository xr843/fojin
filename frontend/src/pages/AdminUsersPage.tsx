import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Input, Select, Space, Typography, message, Popconfirm, Switch } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  getAdminUsers,
  updateAdminUser,
  type AdminUserItem,
} from "../api/client";
import { useAuthStore } from "../stores/authStore";
import { formatAdminDate } from "./adminI18n";

const roleColorMap: Record<string, string> = {
  admin: "red",
  reviewer: "blue",
  user: "default",
};

export default function AdminUsersPage() {
  const { t, i18n } = useTranslation();
  const currentUser = useAuthStore((s) => s.user);
  const [items, setItems] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");

  const fetchData = useCallback(() => {
    return getAdminUsers({
      page,
      size: 20,
      q: search || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
    })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        message.error(t("admin_crud.users.load_error"));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [page, search, sortBy, sortOrder, t]);

  // Spinner state for param changes is adjusted during render; the fetch
  // effect below only sets state from promise callbacks.
  const queryKey = `${page}|${search}|${sortBy}|${sortOrder}`;
  const [prevQueryKey, setPrevQueryKey] = useState(queryKey);
  if (prevQueryKey !== queryKey) {
    setPrevQueryKey(queryKey);
    setLoading(true);
  }

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const refresh = useCallback(() => {
    setLoading(true);
    void fetchData();
  }, [fetchData]);

  const handleToggleActive = async (record: AdminUserItem) => {
    try {
      await updateAdminUser(record.id, { is_active: !record.is_active });
      message.success(record.is_active ? t("admin_crud.users.disabled") : t("admin_crud.users.enabled"));
      refresh();
    } catch {
      message.error(t("admin_crud.common.action_failed"));
    }
  };

  const handleRoleChange = async (record: AdminUserItem, role: string) => {
    try {
      await updateAdminUser(record.id, { role });
      message.success(t("admin_crud.users.role_updated"));
      refresh();
    } catch {
      message.error(t("admin_crud.common.action_failed"));
    }
  };

  const columns = [
    {
      title: t("admin_crud.column.username"),
      dataIndex: "username",
      width: 120,
    },
    {
      title: t("admin_crud.column.display_name"),
      dataIndex: "display_name",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: t("admin_crud.column.email"),
      dataIndex: "email",
      ellipsis: true,
    },
    {
      title: t("admin_crud.column.role"),
      dataIndex: "role",
      width: 120,
      render: (role: string, record: AdminUserItem) => {
        if (record.id === currentUser?.id) {
          return <Tag color={roleColorMap[role]}>{role}</Tag>;
        }
        return (
          <Select
            size="small"
            value={role}
            style={{ width: 100 }}
            onChange={(v) => handleRoleChange(record, v)}
            options={[
              { value: "user", label: "user" },
              { value: "reviewer", label: "reviewer" },
              { value: "admin", label: "admin" },
            ]}
          />
        );
      },
    },
    {
      title: t("admin_crud.column.status"),
      dataIndex: "is_active",
      width: 80,
      render: (active: boolean, record: AdminUserItem) => {
        if (record.id === currentUser?.id) {
          return <Tag color="green">{t("admin_crud.users.active")}</Tag>;
        }
        return (
          <Popconfirm
            title={active ? t("admin_crud.users.confirm_disable") : t("admin_crud.users.confirm_enable")}
            onConfirm={() => handleToggleActive(record)}
            okText={t("admin_crud.common.confirm")}
            cancelText={t("admin_crud.common.cancel")}
          >
            <Switch checked={active} size="small" />
          </Popconfirm>
        );
      },
    },
    {
      title: t("admin_crud.column.registered_at"),
      dataIndex: "created_at",
      width: 170,
      sorter: true,
      render: (value: string) => formatAdminDate(value, i18n.language),
    },
    {
      title: t("admin_crud.column.last_active"),
      dataIndex: "last_active_at",
      width: 170,
      sorter: true,
      render: (value: string | null) => formatAdminDate(value, i18n.language),
    },
  ];

  return (
    <>
      <Helmet>
        <title>{t("admin_crud.users.page_title")}</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {t("admin_crud.users.heading")}
          </Typography.Title>
          <Space>
            <Input.Search
              placeholder={t("admin_crud.users.search_placeholder")}
              allowClear
              prefix={<SearchOutlined />}
              style={{ width: 280 }}
              onSearch={(v) => {
                setSearch(v);
                setPage(1);
              }}
            />
            <Link to="/admin/audit-log" style={{ fontSize: 13 }}>{t("nav.admin_audit_log")}</Link>
          </Space>
        </Space>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          onChange={(_pagination, _filters, sorter) => {
            if (!Array.isArray(sorter) && sorter.field) {
              setSortBy(sorter.field as string);
              setSortOrder(sorter.order === "ascend" ? "asc" : "desc");
            }
          }}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (count) => t("admin_crud.users.total_users", { count }),
          }}
          size="middle"
        />
      </div>
    </>
  );
}
