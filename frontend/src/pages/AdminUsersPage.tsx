import { useEffect, useState, useCallback } from "react";
import { Alert, Button, Table, Tag, Input, Modal, Select, Space, Typography, message, Popconfirm, Switch } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  createAdminResetLink,
  getAdminUsers,
  updateAdminUser,
  type AdminResetLink,
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
  const [resetLink, setResetLink] = useState<AdminResetLink | null>(null);

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

  const handleResetLink = async (record: AdminUserItem) => {
    try {
      setResetLink(await createAdminResetLink(record.id));
    } catch {
      message.error(t("admin_crud.common.action_failed"));
    }
  };

  const copyResetLink = async () => {
    if (!resetLink) return;
    try {
      await navigator.clipboard.writeText(resetLink.url);
      message.success(t("admin_crud.users.reset_link_copied"));
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
    {
      title: t("admin_crud.column.actions"),
      key: "actions",
      width: 110,
      render: (_: unknown, record: AdminUserItem) =>
        record.is_active ? (
          <Popconfirm
            title={t("admin_crud.users.reset_link_confirm")}
            onConfirm={() => handleResetLink(record)}
            okText={t("admin_crud.common.confirm")}
            cancelText={t("admin_crud.common.cancel")}
          >
            <Button size="small">{t("admin_crud.users.reset_link")}</Button>
          </Popconfirm>
        ) : null,
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
      <Modal
        open={resetLink !== null}
        title={resetLink ? t("admin_crud.users.reset_link_title", { username: resetLink.username }) : ""}
        onCancel={() => setResetLink(null)}
        footer={null}
        destroyOnHidden
      >
        {resetLink && (
          <>
            <Alert type="warning" showIcon message={t("admin_crud.users.reset_link_note")} style={{ marginBottom: 12 }} />
            <Typography.Paragraph style={{ marginBottom: 8 }}>
              {t("admin_crud.users.reset_link_email", { email: resetLink.email })}
              {!resetLink.email_verified && (
                <Typography.Text type="secondary"> {t("admin_crud.users.reset_link_unverified")}</Typography.Text>
              )}
            </Typography.Paragraph>
            <Input.TextArea value={resetLink.url} readOnly autoSize style={{ fontFamily: "monospace", fontSize: 12 }} />
            <Button type="primary" style={{ marginTop: 12 }} onClick={copyResetLink}>
              {t("admin_crud.users.reset_link_copy")}
            </Button>
          </>
        )}
      </Modal>
    </>
  );
}
