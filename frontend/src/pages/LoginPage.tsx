import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Card, Form, Input, Button, Typography, Tabs, Divider, message, Space } from "antd";
import { UserOutlined, LockOutlined, MailOutlined, GithubOutlined, GoogleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import axios from "axios";
import { useAuthStore } from "../stores/authStore";
import api from "../api/client";

const { Title, Text } = Typography;

interface ApiErrorData {
  detail?: string | Array<{ msg?: string }>;
}

/**
 * 登录成功后的回跳目标。用 sessionStorage 而非 location.state：OAuth 流程
 * 经第三方往返后 state 必然丢失，sessionStorage 两条路径通吃。
 * 只接受站内相对路径，防 open-redirect。
 */
function consumeReturnTo(): string {
  try {
    const v = sessionStorage.getItem("fojin.login.returnTo");
    sessionStorage.removeItem("fojin.login.returnTo");
    if (v && v.startsWith("/") && !v.startsWith("//")) return v;
  } catch { /* ignore */ }
  return "/";
}

function getApiErrorDetail(err: unknown): ApiErrorData["detail"] | undefined {
  if (!axios.isAxiosError<ApiErrorData>(err)) return undefined;
  return err.response?.data?.detail;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("login");
  const [searchParams] = useSearchParams();

  // Handle OAuth callback: ?provider=github&code=xxx
  // The backend redirects with a one-time exchange code (NOT a JWT) to
  // keep tokens out of nginx access logs, browser history, and Referer.
  useEffect(() => {
    const code = searchParams.get("code");
    const provider = searchParams.get("provider");
    const error = searchParams.get("error");

    if (error) {
      message.error(t("auth.oauth_fail_with_error", { error }));
      return;
    }

    if (code && provider) {
      (async () => {
        try {
          const { data: tokenData } = await api.post("/auth/oauth/exchange", { code });
          const token = tokenData.access_token;
          const { data: user } = await api.get("/auth/me", {
            headers: { Authorization: `Bearer ${token}` },
          });
          setAuth(token, user);
          message.success(t("auth.oauth_success", {
            provider: provider === "github" ? "GitHub" : "Google",
          }));
          navigate(consumeReturnTo(), { replace: true });
        } catch {
          message.error(t("auth.oauth_fail_retry"));
          navigate("/login", { replace: true });
        }
      })();
    }
  }, [searchParams, setAuth, navigate, t]);

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const { data: tokenData } = await api.post("/auth/login", values);
      const { data: user } = await api.get("/auth/me", {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });
      setAuth(tokenData.access_token, user);
      message.success(t("auth.login_success"));
      navigate(consumeReturnTo());
    } catch (err: unknown) {
      const detail = getApiErrorDetail(err);
      message.error(typeof detail === "string" ? detail : t("auth.login_fail"));
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: {
    username: string;
    email: string;
    password: string;
    display_name?: string;
  }) => {
    setLoading(true);
    try {
      await api.post("/auth/register", values);
      message.success(t("auth.register_success"));
      setActiveTab("login");
    } catch (err: unknown) {
      const detail = getApiErrorDetail(err);
      const msg = Array.isArray(detail)
        ? detail
            .map((d) => d.msg)
            .filter((value): value is string => Boolean(value))
            .join("; ") || t("auth.register_fail")
        : detail || t("auth.register_fail");
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "calc(100vh - 200px)",
        padding: 24,
      }}
    >
      <Card style={{ width: 420 }}>
        <Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          {t("app.name")}
        </Title>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          centered
          items={[
            {
              key: "login",
              label: t("auth.login"),
              children: (
                <>
                  <Form onFinish={handleLogin} layout="vertical">
                    <Form.Item name="username" rules={[{ required: true, message: t("auth.username_required") }]}>
                      <Input prefix={<UserOutlined />} placeholder={t("auth.username")} size="large" />
                    </Form.Item>
                    <Form.Item name="password" rules={[{ required: true, message: t("auth.password_required") }]}>
                      <Input.Password prefix={<LockOutlined />} placeholder={t("auth.password")} size="large" />
                    </Form.Item>
                    <Form.Item>
                      <Button type="primary" htmlType="submit" loading={loading} block size="large">
                        {t("auth.login")}
                      </Button>
                    </Form.Item>
                  </Form>
                  <SocialLoginButtons />
                </>
              ),
            },
            {
              key: "register",
              label: t("auth.register"),
              children: (
                <Form onFinish={handleRegister} layout="vertical">
                  <Form.Item name="username" rules={[{ required: true, message: t("auth.username_required") }]}>
                    <Input prefix={<UserOutlined />} placeholder={t("auth.username")} size="large" />
                  </Form.Item>
                  <Form.Item
                    name="email"
                    rules={[
                      { required: true, message: t("auth.email_required") },
                      { type: "email", message: t("auth.email_invalid") },
                    ]}
                  >
                    <Input prefix={<MailOutlined />} placeholder={t("auth.email")} size="large" />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    rules={[
                      { required: true, message: t("auth.password_required") },
                      { min: 8, message: t("auth.password_min") },
                      { pattern: /[a-zA-Z]/, message: t("auth.password_letter") },
                      { pattern: /\d/, message: t("auth.password_digit") },
                    ]}
                  >
                    <Input.Password prefix={<LockOutlined />} placeholder={t("auth.password_hint")} size="large" />
                  </Form.Item>
                  <Form.Item name="display_name">
                    <Input prefix={<UserOutlined />} placeholder={t("auth.display_name")} size="large" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block size="large">
                      {t("auth.register")}
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}


function SocialLoginButtons() {
  const { t } = useTranslation();

  return (
    <>
      <Divider plain>
        <Text type="secondary" style={{ fontSize: 12 }}>{t("auth.social_login_divider")}</Text>
      </Divider>
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Button
          icon={<GithubOutlined />}
          block
          size="large"
          onClick={async () => { try { const { data } = await api.get("/auth/github/login"); window.location.href = data.url; } catch { message.error(t("auth.github_login_fail")); } }}
        >
          {t("auth.github_login")}
        </Button>
        <Button
          icon={<GoogleOutlined />}
          block
          size="large"
          onClick={async () => { try { const { data } = await api.get("/auth/google/login"); window.location.href = data.url; } catch { message.error(t("auth.google_login_fail")); } }}
        >
          {t("auth.google_login")}
        </Button>
      </Space>
    </>
  );
}
