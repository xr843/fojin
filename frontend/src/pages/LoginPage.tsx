import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Form, Input, Button, Typography, Tabs, message } from "antd";
import { UserOutlined, LockOutlined, MailOutlined } from "@ant-design/icons";
import { useAuthStore } from "../stores/authStore";
import api from "../api/client";

const { Title } = Typography;

export default function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("login");

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const { data: tokenData } = await api.post("/auth/login", values);
      const { data: user } = await api.get("/auth/me", {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });
      setAuth(tokenData.access_token, user);
      message.success("登录成功");
      navigate("/");
    } catch (err: any) {
      message.error(err.response?.data?.detail || "登录失败");
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
      message.success("注册成功，请登录");
      setActiveTab("login");
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const msg = Array.isArray(detail) ? detail.map((d: any) => d.msg).join("; ") : detail || "注册失败";
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
      <Card style={{ width: 400 }}>
        <Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          佛津
        </Title>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          centered
          items={[
            {
              key: "login",
              label: "登录",
              children: (
                <Form onFinish={handleLogin} layout="vertical">
                  <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                    <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block size="large">
                      登录
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: "register",
              label: "注册",
              children: (
                <Form onFinish={handleRegister} layout="vertical">
                  <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
                    <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
                  </Form.Item>
                  <Form.Item
                    name="email"
                    rules={[
                      { required: true, message: "请输入邮箱" },
                      { type: "email", message: "邮箱格式不正确" },
                    ]}
                  >
                    <Input prefix={<MailOutlined />} placeholder="邮箱" size="large" />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    rules={[
                      { required: true, message: "请输入密码" },
                      { min: 8, message: "密码至少8位" },
                      { pattern: /[a-zA-Z]/, message: "密码必须包含字母" },
                      { pattern: /\d/, message: "密码必须包含数字" },
                    ]}
                  >
                    <Input.Password prefix={<LockOutlined />} placeholder="密码（至少8位，含字母和数字）" size="large" />
                  </Form.Item>
                  <Form.Item name="display_name">
                    <Input prefix={<UserOutlined />} placeholder="显示名称（选填）" size="large" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block size="large">
                      注册
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
