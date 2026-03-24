import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Input, Select, Space, Typography, message, Popconfirm, Switch } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { Helmet } from "react-helmet-async";
import {
  getAdminUsers,
  updateAdminUser,
  type AdminUserItem,
} from "../api/client";
import { useAuthStore } from "../stores/authStore";

const roleColorMap: Record<string, string> = {
  admin: "red",
  reviewer: "blue",
  user: "default",
};

export default function AdminUsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const [items, setItems] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminUsers({
        page,
        size: 20,
        q: search || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载用户列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, search, sortBy, sortOrder]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggleActive = async (record: AdminUserItem) => {
    try {
      await updateAdminUser(record.id, { is_active: !record.is_active });
      message.success(record.is_active ? "已禁用" : "已启用");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const handleRoleChange = async (record: AdminUserItem, role: string) => {
    try {
      await updateAdminUser(record.id, { role });
      message.success("角色已更新");
      fetchData();
    } catch {
      message.error("操作失败");
    }
  };

  const columns = [
    {
      title: "用户名",
      dataIndex: "username",
      width: 120,
    },
    {
      title: "显示名",
      dataIndex: "display_name",
      width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: "邮箱",
      dataIndex: "email",
      ellipsis: true,
    },
    {
      title: "角色",
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
      title: "状态",
      dataIndex: "is_active",
      width: 80,
      render: (active: boolean, record: AdminUserItem) => {
        if (record.id === currentUser?.id) {
          return <Tag color="green">正常</Tag>;
        }
        return (
          <Popconfirm
            title={active ? "确定禁用此用户？" : "确定启用此用户？"}
            onConfirm={() => handleToggleActive(record)}
            okText="确定"
            cancelText="取消"
          >
            <Switch checked={active} size="small" />
          </Popconfirm>
        );
      },
    },
    {
      title: "注册时间",
      dataIndex: "created_at",
      width: 170,
      sorter: true,
      render: (t: string) => new Date(t).toLocaleString("zh-CN"),
    },
    {
      title: "最后活跃",
      dataIndex: "last_active_at",
      width: 170,
      sorter: true,
      render: (t: string | null) => (t ? new Date(t).toLocaleString("zh-CN") : "-"),
    },
  ];

  return (
    <>
      <Helmet>
        <title>用户管理 - 佛津</title>
      </Helmet>
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        <Space style={{ marginBottom: 16, justifyContent: "space-between", width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            用户管理
          </Typography.Title>
          <Input.Search
            placeholder="搜索用户名或邮箱"
            allowClear
            prefix={<SearchOutlined />}
            style={{ width: 280 }}
            onSearch={(v) => {
              setSearch(v);
              setPage(1);
            }}
          />
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
            showTotal: (t) => `共 ${t} 个用户`,
          }}
          size="middle"
        />
      </div>
    </>
  );
}
