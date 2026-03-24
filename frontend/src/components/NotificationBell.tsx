import { useState, useEffect, useCallback } from "react";
import { Badge, Popover, List, Button, Typography, Empty, Space } from "antd";
import { BellOutlined } from "@ant-design/icons";
import { useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";
import {
  getNotifications,
  getUnreadNotificationCount,
  markNotificationRead,
  markAllNotificationsRead,
  type NotificationItem,
} from "../api/client";

export default function NotificationBell() {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const fetchUnreadCount = useCallback(() => {
    if (!user) return;
    getUnreadNotificationCount().then(setUnreadCount).catch(() => {});
  }, [user]);

  useEffect(() => {
    fetchUnreadCount();
  }, [fetchUnreadCount, location.pathname]);

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const res = await getNotifications(1, 10);
      setItems(res.items);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleOpenChange = (visible: boolean) => {
    setOpen(visible);
    if (visible) {
      fetchNotifications();
    }
  };

  const handleMarkRead = async (id: number) => {
    await markNotificationRead(id);
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    setUnreadCount((c) => Math.max(0, c - 1));
  };

  const handleMarkAllRead = async () => {
    await markAllNotificationsRead();
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
  };

  if (!user) return null;

  const content = (
    <div style={{ width: 320 }}>
      {unreadCount > 0 && (
        <div style={{ textAlign: "right", marginBottom: 8 }}>
          <Button type="link" size="small" onClick={handleMarkAllRead}>
            全部已读
          </Button>
        </div>
      )}
      {items.length === 0 ? (
        <Empty description="暂无通知" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          loading={loading}
          dataSource={items}
          renderItem={(item) => (
            <List.Item
              style={{
                background: item.is_read ? undefined : "rgba(22,119,255,0.04)",
                padding: "8px 12px",
                cursor: item.is_read ? "default" : "pointer",
              }}
              onClick={() => !item.is_read && handleMarkRead(item.id)}
            >
              <List.Item.Meta
                title={
                  <Space>
                    {!item.is_read && <Badge status="processing" />}
                    <Typography.Text strong={!item.is_read} style={{ fontSize: 13 }}>
                      {item.title}
                    </Typography.Text>
                  </Space>
                }
                description={
                  <>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {item.content}
                    </Typography.Text>
                    <br />
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      {new Date(item.created_at).toLocaleString("zh-CN")}
                    </Typography.Text>
                  </>
                }
              />
            </List.Item>
          )}
        />
      )}
    </div>
  );

  return (
    <Popover
      content={content}
      title="通知"
      trigger="click"
      open={open}
      onOpenChange={handleOpenChange}
      placement="bottomRight"
    >
      <Badge count={unreadCount} size="small" offset={[2, -2]}>
        <BellOutlined
          style={{ fontSize: 16, cursor: "pointer", color: "var(--fj-ink-muted)" }}
        />
      </Badge>
    </Popover>
  );
}
