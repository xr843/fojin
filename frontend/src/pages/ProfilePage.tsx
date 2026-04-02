import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Typography, Card, Tabs, List, Tag, Empty, Spin, Descriptions, Button, Space, Pagination, Input, Select, message, Alert } from "antd";
import { BookOutlined, HistoryOutlined, UserOutlined, ReadOutlined, KeyOutlined, DeleteOutlined, CheckCircleOutlined } from "@ant-design/icons";
import { useAuthStore } from "../stores/authStore";
import { getBookmarks, getHistory, getApiKeyStatus, saveApiKey, deleteApiKey } from "../api/client";

const { Title } = Typography;

const PROVIDERS = [
  // 国内
  { value: "deepseek", label: "DeepSeek" },
  { value: "dashscope", label: "通义千问 (DashScope)" },
  { value: "zhipu", label: "智谱 AI (GLM)" },
  { value: "moonshot", label: "月之暗面 (Kimi)" },
  { value: "doubao", label: "字节豆包 (Doubao)" },
  { value: "minimax", label: "MiniMax" },
  { value: "stepfun", label: "阶跃星辰 (StepFun)" },
  { value: "baichuan", label: "百川智能 (Baichuan)" },
  { value: "yi", label: "零一万物 (Yi)" },
  { value: "siliconflow", label: "SiliconFlow" },
  // 国际
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "gemini", label: "Google Gemini" },
  { value: "groq", label: "Groq" },
  { value: "mistral", label: "Mistral" },
  { value: "xai", label: "xAI (Grok)" },
  { value: "openrouter", label: "OpenRouter" },
  // 自定义
  { value: "custom", label: "自定义 (Custom)" },
];

export default function ProfilePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const [bmPage, setBmPage] = useState(1);
  const [histPage, setHistPage] = useState(1);
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState("dashscope");
  const [apiModel, setApiModel] = useState("");
  const [apiCustomUrl, setApiCustomUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const defaultTab = searchParams.get("tab") || "profile";

  const { data: keyStatus, refetch: refetchKey } = useQuery({
    queryKey: ["apiKeyStatus"],
    queryFn: getApiKeyStatus,
    enabled: !!user,
  });

  const handleSaveKey = async () => {
    if (!apiKey.trim()) { message.warning("请输入 API Key"); return; }
    setSaving(true);
    try {
      await saveApiKey({
        api_key: apiKey.trim(),
        provider,
        model: apiModel || undefined,
        custom_url: provider === "custom" ? apiCustomUrl.trim() || undefined : undefined,
      });
      message.success("API Key 已保存");
      setApiKey("");
      refetchKey();
      queryClient.invalidateQueries({ queryKey: ["apiKeyStatus"] });
    } catch (err: any) {
      message.error(err?.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteKey = async () => {
    try {
      await deleteApiKey();
      message.success("API Key 已删除");
      refetchKey();
      queryClient.invalidateQueries({ queryKey: ["apiKeyStatus"] });
    } catch {
      message.error("删除失败");
    }
  };

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
          defaultActiveKey={defaultTab}
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
                        onClick={() => navigate(`/texts/${item.text_id}`)}
                        actions={[
                          <Button type="link" icon={<ReadOutlined />}>
                            查看详情
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
            {
              key: "apikey",
              label: (
                <span>
                  <KeyOutlined /> API Key
                </span>
              ),
              children: (
                <Card>
                  <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                    <Alert
                      message="Bring Your Own Key (BYOK)"
                      description="配置自己的 AI API Key，即可无限使用 AI 佛典问答功能。不配置则使用平台免费额度（每日 10 次）。Key 经 AES 加密存储，仅用于调用 AI 接口。"
                      type="info"
                      showIcon
                    />
                    {keyStatus?.has_api_key && (
                      <Alert
                        message={
                          <Space>
                            <CheckCircleOutlined style={{ color: "#52c41a" }} />
                            已配置: {keyStatus.provider} · {keyStatus.key_preview}
                            {keyStatus.model && ` · ${keyStatus.model}`}
                          </Space>
                        }
                        type="success"
                        action={
                          <Button danger size="small" icon={<DeleteOutlined />} onClick={handleDeleteKey}>
                            删除
                          </Button>
                        }
                      />
                    )}
                    <div>
                      <Typography.Text strong>服务商</Typography.Text>
                      <Select
                        value={provider}
                        onChange={setProvider}
                        options={PROVIDERS}
                        showSearch
                        optionFilterProp="label"
                        style={{ width: "100%", marginTop: 4 }}
                      />
                    </div>
                    {provider === "custom" && (
                      <div>
                        <Typography.Text strong>API Base URL</Typography.Text>
                        <Input
                          value={apiCustomUrl}
                          onChange={(e) => setApiCustomUrl(e.target.value)}
                          placeholder="https://your-api.example.com/v1"
                          style={{ marginTop: 4 }}
                        />
                      </div>
                    )}
                    <div>
                      <Typography.Text strong>API Key</Typography.Text>
                      <Input.Password
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder="输入你的 API Key"
                        style={{ marginTop: 4 }}
                      />
                    </div>
                    <div>
                      <Typography.Text strong>模型（可选）</Typography.Text>
                      <Input
                        value={apiModel}
                        onChange={(e) => setApiModel(e.target.value)}
                        placeholder="留空使用默认模型"
                        style={{ marginTop: 4 }}
                      />
                    </div>
                    <Button type="primary" loading={saving} onClick={handleSaveKey}>
                      保存 API Key
                    </Button>
                  </Space>
                </Card>
              ),
            },
          ]}
        />
      </Space>
    </div>
  );
}
