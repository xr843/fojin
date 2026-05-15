import { useEffect, useState, useCallback } from "react";
import { Table, Tag, Select, Typography, message } from "antd";
import { Helmet } from "react-helmet-async";
import { getAdminAuditLog, type AdminAuditLogItem } from "../api/client";

const actionLabel: Record<string, string> = {
  update_user: "用户变更",
  update_suggestion: "建议审核",
  delete_suggestion: "删除建议",
};

const actionColor: Record<string, string> = {
  update_user: "blue",
  update_suggestion: "green",
  delete_suggestion: "red",
};

const fieldLabel: Record<string, string> = {
  role: "角色",
  is_active: "账号状态",
  status: "状态",
  name: "名称",
  url: "链接",
};

function renderValue(v: unknown): string {
  if (v === true) return "启用";
  if (v === false) return "停用";
  if (v === null || v === undefined) return "—";
  return String(v);
}

function renderDetail(detail: Record<string, unknown> | null) {
  if (!detail || Object.keys(detail).length === 0) return <span style={{ color: "#999" }}>—</span>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {Object.entries(detail).map(([key, value]) => {
        const label = fieldLabel[key] || key;
        if (value && typeof value === "object" && "from" in value && "to" in value) {
          const diff = value as { from: unknown; to: unknown };
          return (
            <span key={key} style={{ fontSize: 13 }}>
              {label}：<span style={{ color: "#999" }}>{renderValue(diff.from)}</span>
              {" → "}
              <span style={{ color: "#1677ff" }}>{renderValue(diff.to)}</span>
            </span>
          );
        }
        return (
          <span key={key} style={{ fontSize: 13 }}>
            {label}：{renderValue(value)}
          </span>
        );
      })}
    </div>
  );
}

export default function AdminAuditLogPage() {
  const [items, setItems] = useState<AdminAuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [actionFilter, setActionFilter] = useState<string | undefined>(undefined);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminAuditLog({ page, size: 20, action: actionFilter });
      setItems(res.items);
      setTotal(res.total);
    } catch {
      message.error("加载审计日志失败");
    } finally {
      setLoading(false);
    }
  }, [page, actionFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const columns = [
    {
      title: "时间",
      dataIndex: "created_at",
      width: 170,
      render: (t: string) => new Date(t).toLocaleString("zh-CN", { hour12: false }),
    },
    {
      title: "操作人",
      dataIndex: "actor_username",
      width: 130,
      render: (name: string | null) => name || <span style={{ color: "#999" }}>已删除用户</span>,
    },
    {
      title: "动作",
      dataIndex: "action",
      width: 110,
      render: (a: string) => <Tag color={actionColor[a]}>{actionLabel[a] || a}</Tag>,
    },
    {
      title: "对象",
      width: 150,
      render: (_: unknown, record: AdminAuditLogItem) =>
        record.target_id != null ? `${record.target_type} #${record.target_id}` : record.target_type,
    },
    {
      title: "变更详情",
      dataIndex: "detail",
      render: (detail: Record<string, unknown> | null) => renderDetail(detail),
    },
  ];

  return (
    <>
      <Helmet>
        <title>审计日志 - 佛津</title>
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
            审计日志
          </Typography.Title>
          <Select
            style={{ width: 160 }}
            placeholder="筛选动作"
            allowClear
            value={actionFilter}
            onChange={(v) => {
              setActionFilter(v);
              setPage(1);
            }}
            options={[
              { value: "update_user", label: "用户变更" },
              { value: "update_suggestion", label: "建议审核" },
              { value: "delete_suggestion", label: "删除建议" },
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
            showTotal: (t) => `共 ${t} 条`,
          }}
          size="middle"
        />
      </div>
    </>
  );
}
