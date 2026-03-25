import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Card, Form, Input, Button, Typography, Tabs, Divider, message, Space } from "antd";
import { UserOutlined, LockOutlined, MailOutlined, MobileOutlined, GithubOutlined, GoogleOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../stores/authStore";
import api from "../api/client";

const { Title, Text } = Typography;

export default function LoginPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("login");
  const [searchParams] = useSearchParams();

  // Handle OAuth callback: ?token=xxx&provider=github
  useEffect(() => {
    const token = searchParams.get("token");
    const provider = searchParams.get("provider");
    const error = searchParams.get("error");

    if (error) {
      message.error(`第三方登录失败: ${error}`);
      return;
    }

    if (token && provider) {
      // Got token from OAuth callback, fetch user info
      (async () => {
        try {
          const { data: user } = await api.get("/auth/me", {
            headers: { Authorization: `Bearer ${token}` },
          });
          setAuth(token, user);
          message.success(`${provider === "github" ? "GitHub" : "Google"} 登录成功`);
          navigate("/", { replace: true });
        } catch {
          message.error("登录失败，请重试");
        }
      })();
    }
  }, [searchParams, setAuth, navigate]);

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const { data: tokenData } = await api.post("/auth/login", values);
      const { data: user } = await api.get("/auth/me", {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });
      setAuth(tokenData.access_token, user);
      message.success(t("auth.login_success"));
      navigate("/");
    } catch (err: any) {
      message.error(err.response?.data?.detail || t("auth.login_fail"));
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
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const msg = Array.isArray(detail) ? detail.map((d: any) => d.msg).join("; ") : detail || t("auth.register_fail");
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
            {
              key: "phone",
              label: "手机登录",
              children: <PhoneLoginForm />,
            },
          ]}
        />
      </Card>
    </div>
  );
}


function SocialLoginButtons() {
  return (
    <>
      <Divider plain>
        <Text type="secondary" style={{ fontSize: 12 }}>或使用第三方账号登录</Text>
      </Divider>
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Button
          icon={<GithubOutlined />}
          block
          size="large"
          onClick={async () => { try { const { data } = await api.get("/auth/github/login"); window.location.href = data.url; } catch { message.error("GitHub 登录失败"); } }}
          style={{ background: "#24292e", color: "#fff", borderColor: "#24292e" }}
        >
          GitHub 登录
        </Button>
        <Button
          icon={<GoogleOutlined />}
          block
          size="large"
          onClick={async () => { try { const { data } = await api.get("/auth/google/login"); window.location.href = data.url; } catch { message.error("Google 登录失败"); } }}
        >
          Google 登录
        </Button>
      </Space>
    </>
  );
}


function PhoneLoginForm() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [loading, setLoading] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [form] = Form.useForm();

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const handleSendCode = async () => {
    const phone = form.getFieldValue("phone");
    if (!phone || phone.length < 10) {
      message.warning("请输入有效的手机号码");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/sms/send-code", { phone });
      if (data.ok) {
        setCodeSent(true);
        setCountdown(60);
        message.success("验证码已发送");
      } else {
        message.error(data.message || "发送失败");
      }
    } catch {
      message.error("发送失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (values: { phone: string; code: string }) => {
    setLoading(true);
    try {
      const { data: tokenData } = await api.post("/auth/sms/login", values);
      const { data: user } = await api.get("/auth/me", {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });
      setAuth(tokenData.access_token, user);
      message.success("登录成功");
      navigate("/");
    } catch (err: any) {
      message.error(err.response?.data?.detail || "验证码错误或已过期");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Form form={form} onFinish={handleLogin} layout="vertical">
      <Form.Item name="phone" rules={[{ required: true, message: "请输入手机号" }]}>
        <Input
          prefix={<MobileOutlined />}
          placeholder="手机号码"
          size="large"
          maxLength={15}
        />
      </Form.Item>
      <Form.Item>
        <Space.Compact style={{ width: "100%" }}>
          <Form.Item name="code" noStyle rules={[{ required: true, message: "请输入验证码" }]}>
            <Input
              prefix={<LockOutlined />}
              placeholder="验证码"
              size="large"
              maxLength={6}
              style={{ flex: 1 }}
            />
          </Form.Item>
          <Button
            size="large"
            onClick={handleSendCode}
            disabled={countdown > 0}
            loading={loading && !codeSent}
          >
            {countdown > 0 ? `${countdown}s` : codeSent ? "重新发送" : "获取验证码"}
          </Button>
        </Space.Compact>
      </Form.Item>
      <Form.Item>
        <Button type="primary" htmlType="submit" loading={loading} block size="large">
          登录 / 注册
        </Button>
      </Form.Item>
      <Text type="secondary" style={{ fontSize: 12, display: "block", textAlign: "center" }}>
        首次使用手机号登录将自动创建账号
      </Text>
    </Form>
  );
}
