import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Typography, Card, Tabs, List, Tag, Empty, Spin, Descriptions, Button, Space, Pagination } from "antd";
import { BookOutlined, HistoryOutlined, UserOutlined, ReadOutlined } from "@ant-design/icons";
import { useAuthStore } from "../stores/authStore";
import { getBookmarks, getHistory } from "../api/client";

const { Title } = Typography;

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [bmPage, setBmPage] = useState(1);
  const [histPage, setHistPage] = useState(1);

  const { data: bookmarksData, isLoading: bmLoading } = useQuery({
    queryKey: ["bookmarks", bmPage],
    queryFn: () => getBookmarks(bmPage),
    enabled: !!user,
  });

  const { data: historyData, isLoading: histLoading } = useQuery({
    queryKey: ["history", histPage],
    queryFn: () => getHistory(histPage),
    enabled: !!user,
  });

  if (!user) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Typography.Text type="secondary">请先登录</Typography.Text>
        <br />
        <Button type="primary" style={{ marginTop: 16 }} onClick={() => navigate("/login")}>
          去登录
        </Button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800, margin: "24px auto" }}>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Title level={3}>个人中心</Title>

        <Tabs
          items={[
            {
              key: "profile",
              label: (
                <span>
                  <UserOutlined /> 个人资料
                </span>
              ),
              children: (
                <Card>
                  <Descriptions column={1} bordered size="small">
                    <Descriptions.Item label="用户名">{user.username}</Descriptions.Item>
                    <Descriptions.Item label="显示名称">{user.display_name || "-"}</Descriptions.Item>
                    <Descriptions.Item label="邮箱">{user.email}</Descriptions.Item>
                    <Descriptions.Item label="注册时间">
                      {new Date(user.created_at).toLocaleDateString("zh-CN")}
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
              ),
            },
            {
              key: "bookmarks",
              label: (
                <span>
                  <BookOutlined /> 我的收藏 {bookmarksData ? `(${bookmarksData.total})` : ""}
                </span>
              ),
              children: bmLoading ? (
                <div style={{ textAlign: "center", padding: 40 }}>
                  <Spin />
                </div>
              ) : !bookmarksData?.items?.length ? (
                <Empty description="暂无收藏" />
              ) : (
                <>
                  <List
                    dataSource={bookmarksData?.items}
                    renderItem={(item) => (
                      <List.Item
                        style={{ cursor: "pointer" }}
                        onClick={() => navigate(`/texts/${item.text_id}`)}
                        actions={[
                          <Tag color="blue">{item.cbeta_id}</Tag>,
                        ]}
                      >
                        <List.Item.Meta
                          title={item.title_zh}
                          description={
                            item.note ||
                            `收藏于 ${new Date(item.created_at).toLocaleDateString("zh-CN")}`
                          }
                        />
                      </List.Item>
                    )}
                  />
                  {bookmarksData && bookmarksData.total > 20 && (
                    <div style={{ textAlign: "center", marginTop: 16 }}>
                      <Pagination current={bmPage} total={bookmarksData.total} pageSize={20}
                        showSizeChanger={false} onChange={(p) => setBmPage(p)} />
                    </div>
                  )}
                </>
              ),
            },
            {
              key: "history",
              label: (
                <span>
                  <HistoryOutlined /> 阅读历史 {historyData ? `(${historyData.total})` : ""}
                </span>
              ),
              children: histLoading ? (
                <div style={{ textAlign: "center", padding: 40 }}>
                  <Spin />
                </div>
              ) : !historyData?.items?.length ? (
                <Empty description="暂无阅读记录" />
              ) : (
                <>
                  <List
                    dataSource={historyData?.items}
                    renderItem={(item) => (
                      <List.Item
                        style={{ cursor: "pointer" }}
                        onClick={() => navigate(`/read/${item.text_id}?juan=${item.juan_num}`)}
                        actions={[
                          <Button type="link" icon={<ReadOutlined />}>
                            继续阅读
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={item.title_zh}
                          description={`${item.cbeta_id} · 第${item.juan_num}卷 · ${new Date(item.last_read_at).toLocaleDateString("zh-CN")}`}
                        />
                      </List.Item>
                    )}
                  />
                  {historyData && historyData.total > 20 && (
                    <div style={{ textAlign: "center", marginTop: 16 }}>
                      <Pagination current={histPage} total={historyData.total} pageSize={20}
                        showSizeChanger={false} onChange={(p) => setHistPage(p)} />
                    </div>
                  )}
                </>
              ),
            },
          ]}
        />
      </Space>
    </div>
  );
}
