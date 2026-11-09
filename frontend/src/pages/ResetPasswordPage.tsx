import { useState } from "react";
import { Link } from "react-router";
import { Alert, Button, Card, Form, Input, Typography } from "antd";
import { LockOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { Helmet } from "react-helmet-async";
import axios from "axios";
import { resetPasswordWithToken } from "../api/client";

const { Title } = Typography;

/**
 * 令牌放在 # 后面而不是 ?token=：片段不会发给服务器，也不进 Referer 和
 * nginx/Cloudflare 的访问日志——这条链接在 24 小时内等于这个账号的钥匙。
 */
function readToken(): string {
  const m = /(?:^|[#&])token=([A-Za-z0-9_-]+)/.exec(window.location.hash);
  return m ? m[1] : "";
}

function errorDetail(err: unknown): string | undefined {
  if (!axios.isAxiosError<{ detail?: unknown }>(err)) return undefined;
  const d = err.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join("; ") || undefined;
  }
  return undefined;
}

export default function ResetPasswordPage() {
  const { t } = useTranslation();
  const [token] = useState(readToken);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFinish = async (values: { password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await resetPasswordWithToken(token, values.password);
      // 令牌已用掉：从地址栏抹掉，免得被截图、被同步到别的设备的历史里。
      window.history.replaceState(null, "", window.location.pathname);
      setDone(true);
    } catch (err) {
      setError(errorDetail(err) ?? t("auth.reset.fail"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "48px 16px" }}>
      <Helmet>
        <title>{`${t("auth.reset.title")} - ${t("app.name")}`}</title>
        <meta name="robots" content="noindex" />
      </Helmet>
      <Card style={{ width: 420, maxWidth: "100%" }}>
        <Title level={4} style={{ textAlign: "center", marginBottom: 20 }}>
          {t("auth.reset.title")}
        </Title>
        {done ? (
          <>
            <Alert type="success" showIcon message={t("auth.reset.success")} style={{ marginBottom: 16 }} />
            <Link to="/login">
              <Button type="primary" block size="large">{t("auth.reset.go_login")}</Button>
            </Link>
          </>
        ) : !token ? (
          <Alert type="warning" showIcon message={t("auth.reset.no_token")} />
        ) : (
          <Form layout="vertical" onFinish={onFinish}>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            <Form.Item
              name="password"
              rules={[
                { required: true, message: t("auth.password_required") },
                { min: 8, message: t("auth.password_min") },
                { pattern: /[a-zA-Z]/, message: t("auth.password_letter") },
                { pattern: /\d/, message: t("auth.password_digit") },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder={t("auth.reset.new_password")}
                size="large"
                autoComplete="new-password"
              />
            </Form.Item>
            <Form.Item
              name="confirm"
              dependencies={["password"]}
              rules={[
                { required: true, message: t("auth.password_required") },
                ({ getFieldValue }) => ({
                  validator: (_, v) =>
                    !v || v === getFieldValue("password")
                      ? Promise.resolve()
                      : Promise.reject(new Error(t("auth.reset.mismatch"))),
                }),
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder={t("auth.reset.confirm")}
                size="large"
                autoComplete="new-password"
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              {t("auth.reset.submit")}
            </Button>
          </Form>
        )}
      </Card>
    </div>
  );
}
