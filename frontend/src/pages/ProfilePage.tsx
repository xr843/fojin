import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { Typography, Card, Tabs, List, Tag, Empty, Spin, Descriptions, Button, Space, Pagination, Input, Select, message, Alert, Form } from "antd";
import { BookOutlined, HistoryOutlined, UserOutlined, ReadOutlined, KeyOutlined, DeleteOutlined, CheckCircleOutlined, LockOutlined, ArrowLeftOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../stores/authStore";
import { getBookmarks, getHistory, getApiKeyStatus, saveApiKey, deleteApiKey, changePassword } from "../api/client";

const { Title } = Typography;

// Recommended model presets per provider — clicking a chip fills the model field.
// Users can still type any custom model ID. Hints describe role (cheap/flagship/vision)
// instead of exact prices to avoid drift; check provider docs for current pricing.
const PROVIDER_MODELS: Record<string, Array<{ value: string; label: string; hintKey: string }>> = {
  deepseek: [
    { value: "deepseek-v4-flash", label: "V4 Flash", hintKey: "profile.modelHint.economy_daily" },
    { value: "deepseek-v4-pro", label: "V4 Pro", hintKey: "profile.modelHint.flagship" },
  ],
  dashscope: [
    { value: "qwen-plus", label: "Qwen Plus", hintKey: "profile.modelHint.stable_general" },
    { value: "qwen-turbo", label: "Qwen Turbo", hintKey: "profile.modelHint.economy_fast" },
    { value: "qwen-max", label: "Qwen Max", hintKey: "profile.modelHint.flagship" },
    { value: "qwen3.6-flash", label: "Qwen 3.6 Flash", hintKey: "profile.modelHint.next_gen_economy" },
    { value: "qwen3.6-plus", label: "Qwen 3.6 Plus", hintKey: "profile.modelHint.next_gen_main" },
  ],
  moonshot: [
    { value: "moonshot-v1-8k", label: "v1-8k", hintKey: "profile.modelHint.context_8k_economy" },
    { value: "moonshot-v1-32k", label: "v1-32k", hintKey: "profile.modelHint.context_32k" },
    { value: "moonshot-v1-128k", label: "v1-128k", hintKey: "profile.modelHint.context_128k" },
  ],
  zhipu: [
    { value: "glm-4-flash", label: "GLM-4 Flash", hintKey: "profile.modelHint.free_low_cost" },
    { value: "glm-4-air", label: "GLM-4 Air", hintKey: "profile.modelHint.midrange" },
    { value: "glm-4-plus", label: "GLM-4 Plus", hintKey: "profile.modelHint.flagship" },
  ],
  anthropic: [
    { value: "claude-haiku-4-5", label: "Haiku 4.5", hintKey: "profile.modelHint.fast_economy" },
    { value: "claude-sonnet-4-6", label: "Sonnet 4.6", hintKey: "profile.modelHint.main_recommended" },
    { value: "claude-opus-4-7", label: "Opus 4.7", hintKey: "profile.modelHint.flagship" },
  ],
  openai: [
    { value: "gpt-4o-mini", label: "GPT-4o mini", hintKey: "profile.modelHint.economy_daily" },
    { value: "gpt-4o", label: "GPT-4o", hintKey: "profile.modelHint.main" },
  ],
  gemini: [
    { value: "gemini-2.0-flash", label: "2.0 Flash", hintKey: "profile.modelHint.fast_economy" },
    { value: "gemini-2.5-pro", label: "2.5 Pro", hintKey: "profile.modelHint.flagship" },
  ],
  doubao: [
    { value: "doubao-1.5-lite-32k", label: "1.5 Lite", hintKey: "profile.modelHint.economy" },
    { value: "doubao-1.5-pro-32k", label: "1.5 Pro", hintKey: "profile.modelHint.main" },
  ],
  siliconflow: [
    { value: "deepseek-ai/DeepSeek-V3", label: "DeepSeek V3", hintKey: "profile.modelHint.deepseek_mirror" },
    { value: "Qwen/Qwen2.5-72B-Instruct", label: "Qwen 2.5 72B", hintKey: "profile.modelHint.qwen_large" },
    { value: "Pro/moonshotai/Kimi-K2-Instruct", label: "Kimi K2", hintKey: "profile.modelHint.moonshot_mirror_pro" },
  ],
  xai: [
    { value: "grok-2-latest", label: "Grok 2", hintKey: "profile.modelHint.stable" },
  ],
};

const PROVIDERS = [
  { value: "deepseek", labelKey: "profile.provider.deepseek" },
  { value: "dashscope", labelKey: "profile.provider.dashscope" },
  { value: "zhipu", labelKey: "profile.provider.zhipu" },
  { value: "moonshot", labelKey: "profile.provider.moonshot" },
  { value: "doubao", labelKey: "profile.provider.doubao" },
  { value: "minimax", labelKey: "profile.provider.minimax" },
  { value: "stepfun", labelKey: "profile.provider.stepfun" },
  { value: "baichuan", labelKey: "profile.provider.baichuan" },
  { value: "yi", labelKey: "profile.provider.yi" },
  { value: "siliconflow", labelKey: "profile.provider.siliconflow" },
  { value: "openai", labelKey: "profile.provider.openai" },
  { value: "anthropic", labelKey: "profile.provider.anthropic" },
  { value: "gemini", labelKey: "profile.provider.gemini" },
  { value: "groq", labelKey: "profile.provider.groq" },
  { value: "mistral", labelKey: "profile.provider.mistral" },
  { value: "xai", labelKey: "profile.provider.xai" },
  { value: "openrouter", labelKey: "profile.provider.openrouter" },
  { value: "custom", labelKey: "profile.provider.custom" },
];

function uiDateLocale(language: string): string {
  if (language.startsWith("zh-Hant")) return "zh-Hant";
  if (language.startsWith("en")) return "en-US";
  return "zh-CN";
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const [searchParams] = useSearchParams();
  const { user, token, setAuth } = useAuthStore();
  const queryClient = useQueryClient();
  const [bmPage, setBmPage] = useState(1);
  const [histPage, setHistPage] = useState(1);
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] = useState("dashscope");
  const [apiModel, setApiModel] = useState("");
  const [apiCustomUrl, setApiCustomUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [pwForm] = Form.useForm();
  const [changingPw, setChangingPw] = useState(false);

  const defaultTab = searchParams.get("tab") || "profile";
  const dateLocale = uiDateLocale(i18n.language);
  const providerOptions = PROVIDERS.map((p) => ({
    value: p.value,
    label: t(p.labelKey),
  }));

  const { data: keyStatus, refetch: refetchKey } = useQuery({
    queryKey: ["apiKeyStatus"],
    queryFn: getApiKeyStatus,
    enabled: !!user,
  });

  const handleSaveKey = async () => {
    if (!apiKey.trim()) { message.warning(t("profile.api_key_required")); return; }
    setSaving(true);
    try {
      await saveApiKey({
        api_key: apiKey.trim(),
        provider,
        model: apiModel || undefined,
        custom_url: provider === "custom" ? apiCustomUrl.trim() || undefined : undefined,
      });
      message.success(t("profile.api_key_saved"));
      setApiKey("");
      refetchKey();
      queryClient.invalidateQueries({ queryKey: ["apiKeyStatus"] });
    } catch (err) {
      const detail =
        axios.isAxiosError(err) && typeof err.response?.data?.detail === "string"
          ? err.response.data.detail
          : t("profile.save_failed");
      message.error(detail);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteKey = async () => {
    try {
      await deleteApiKey();
      message.success(t("profile.api_key_deleted"));
      refetchKey();
      queryClient.invalidateQueries({ queryKey: ["apiKeyStatus"] });
    } catch {
      message.error(t("profile.delete_failed"));
    }
  };

  const handleChangePassword = async (values: {
    old_password: string;
    new_password: string;
    confirm_password: string;
  }) => {
    if (!user || !token) return;
    setChangingPw(true);
    try {
      const { access_token } = await changePassword({
        old_password: values.old_password,
        new_password: values.new_password,
      });
      setAuth(access_token, user);
      pwForm.resetFields();
      message.success(t("profile.password_changed"));
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 429) {
        message.error(t("profile.password_too_frequent"));
      } else {
        message.error(t("profile.password_change_failed"));
      }
    } finally {
      setChangingPw(false);
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
        <Typography.Text type="secondary">{t("profile.login_required")}</Typography.Text>
        <br />
        <Button type="primary" style={{ marginTop: 16 }} onClick={() => navigate("/login")}>
          {t("profile.go_login")}
        </Button>
      </div>
    );
  }

  // 这一页的 API Key 面板全站只有 /chat 的三个「配置 Key」入口进得来，所以从那里
  // 来的人需要一条回头路。判据用 from=chat 而不是无条件显示：从头像菜单点进个人
  // 中心的人，看到一个「返回 AI 问答」只会莫名其妙。
  // 带上 ?s= 一起回去，才是真的"返回"——否则落在空白新对话上，和点顶部导航没区别
  // （sessionId 只是 ChatPage 的组件 state，离开就没了）。
  const cameFromChat = searchParams.get("from") === "chat";
  const backSid = searchParams.get("s");
  const backToChat = backSid && /^\d+$/.test(backSid) ? `/chat?s=${backSid}` : "/chat";

  return (
    <div style={{ maxWidth: 800, margin: "24px auto" }}>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        {cameFromChat && (
          <Button
            type="link"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(backToChat)}
            style={{ paddingLeft: 0, alignSelf: "flex-start" }}
          >
            {t("profile.back_to_chat")}
          </Button>
        )}
        <Title level={3}>{t("auth.profile")}</Title>

        <Tabs
          defaultActiveKey={defaultTab}
          items={[
            {
              key: "profile",
              label: (
                <span>
                  <UserOutlined /> {t("profile.tab_profile")}
                </span>
              ),
              children: (
                <Card>
                  <Descriptions column={1} bordered size="small">
                    <Descriptions.Item label={t("profile.username")}>{user.username}</Descriptions.Item>
                    <Descriptions.Item label={t("profile.display_name")}>{user.display_name || "-"}</Descriptions.Item>
                    <Descriptions.Item label={t("profile.email")}>{user.email}</Descriptions.Item>
                    <Descriptions.Item label={t("profile.joined")}>
                      {new Date(user.created_at).toLocaleDateString(dateLocale)}
                    </Descriptions.Item>
                  </Descriptions>
                </Card>
              ),
            },
            {
              key: "bookmarks",
              label: (
                <span>
                  <BookOutlined /> {t("profile.tab_bookmarks")} {bookmarksData ? `(${bookmarksData.total})` : ""}
                </span>
              ),
              children: bmLoading ? (
                <div style={{ textAlign: "center", padding: 40 }}>
                  <Spin />
                </div>
              ) : !bookmarksData?.items?.length ? (
                <Empty description={t("profile.no_bookmarks")} />
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
                            t("profile.bookmarked_at", {
                              date: new Date(item.created_at).toLocaleDateString(dateLocale),
                            })
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
                  <HistoryOutlined /> {t("profile.tab_history")} {historyData ? `(${historyData.total})` : ""}
                </span>
              ),
              children: histLoading ? (
                <div style={{ textAlign: "center", padding: 40 }}>
                  <Spin />
                </div>
              ) : !historyData?.items?.length ? (
                <Empty description={t("profile.no_history")} />
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
                            {t("profile.view_details")}
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={item.title_zh}
                          description={t("profile.history_description", {
                            cbetaId: item.cbeta_id,
                            n: item.juan_num,
                            date: new Date(item.last_read_at).toLocaleDateString(dateLocale),
                          })}
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
                      description={t("profile.byok_description")}
                      type="info"
                      showIcon
                    />
                    {keyStatus?.has_api_key && (
                      <Alert
                        message={
                          <Space>
                            <CheckCircleOutlined style={{ color: "var(--fj-success)" }} />
                            {t("profile.api_key_configured", {
                              provider: keyStatus.provider,
                              preview: keyStatus.key_preview,
                            })}
                            {keyStatus.model && ` · ${keyStatus.model}`}
                          </Space>
                        }
                        type="success"
                        action={
                          <Button danger size="small" icon={<DeleteOutlined />} onClick={handleDeleteKey}>
                            {t("profile.delete")}
                          </Button>
                        }
                      />
                    )}
                    <div>
                      <Typography.Text strong>{t("profile.provider")}</Typography.Text>
                      <Select
                        value={provider}
                        onChange={setProvider}
                        options={providerOptions}
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
                        placeholder={t("profile.api_key_placeholder")}
                        style={{ marginTop: 4 }}
                      />
                    </div>
                    <div>
                      <Typography.Text strong>{t("profile.model_optional")}</Typography.Text>
                      <Input
                        value={apiModel}
                        onChange={(e) => setApiModel(e.target.value)}
                        placeholder={t("profile.model_placeholder")}
                        style={{ marginTop: 4 }}
                      />
                      {PROVIDER_MODELS[provider] && (
                        <Space wrap size={[6, 6]} style={{ marginTop: 8 }}>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {t("profile.recommended")}
                          </Typography.Text>
                          {PROVIDER_MODELS[provider].map((m) => (
                            <Tag.CheckableTag
                              key={m.value}
                              checked={apiModel === m.value}
                              onChange={() => setApiModel(m.value)}
                              style={{ cursor: "pointer", border: "1px solid #d9d9d9" }}
                            >
                              <span style={{ fontWeight: 500 }}>{m.label}</span>
                              <span style={{ marginLeft: 6, color: "#8c8c8c", fontSize: 11 }}>
                                {t(m.hintKey)}
                              </span>
                            </Tag.CheckableTag>
                          ))}
                        </Space>
                      )}
                    </div>
                    <Button type="primary" loading={saving} onClick={handleSaveKey}>
                      {t("profile.save_api_key")}
                    </Button>
                  </Space>
                </Card>
              ),
            },
            {
              key: "security",
              label: (
                <span>
                  <LockOutlined /> {t("profile.tab_security")}
                </span>
              ),
              children: (
                <Card>
                  <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                    <Alert
                      message={t("profile.password_title")}
                      description={
                        <div>
                          <div style={{ marginBottom: 8 }}>
                            {t("profile.password_description_1")}
                          </div>
                          <div style={{ color: "#8c6e3e" }}>
                            {t("profile.password_description_2")}
                          </div>
                        </div>
                      }
                      type="info"
                      showIcon
                    />
                    <Form
                      form={pwForm}
                      layout="vertical"
                      onFinish={handleChangePassword}
                      autoComplete="off"
                    >
                      <Form.Item
                        label={t("profile.current_password")}
                        name="old_password"
                        rules={[{ required: true, message: t("profile.current_password_required") }]}
                      >
                        <Input.Password autoComplete="current-password" size="large" />
                      </Form.Item>
                      <Form.Item
                        label={t("profile.new_password")}
                        name="new_password"
                        rules={[
                          { required: true, message: t("profile.new_password_required") },
                          { min: 8, message: t("auth.password_min") },
                          { pattern: /[a-zA-Z]/, message: t("auth.password_letter") },
                          { pattern: /\d/, message: t("auth.password_digit") },
                        ]}
                      >
                        <Input.Password autoComplete="new-password" size="large" />
                      </Form.Item>
                      <Form.Item
                        label={t("profile.confirm_password")}
                        name="confirm_password"
                        dependencies={["new_password"]}
                        rules={[
                          { required: true, message: t("profile.confirm_password_required") },
                          ({ getFieldValue }) => ({
                            validator(_, value) {
                              if (!value || getFieldValue("new_password") === value) {
                                return Promise.resolve();
                              }
                              return Promise.reject(new Error(t("profile.password_mismatch")));
                            },
                          }),
                        ]}
                      >
                        <Input.Password autoComplete="new-password" size="large" />
                      </Form.Item>
                      <Form.Item>
                        <Button type="primary" htmlType="submit" loading={changingPw}>
                          {t("profile.change_password")}
                        </Button>
                      </Form.Item>
                    </Form>
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
