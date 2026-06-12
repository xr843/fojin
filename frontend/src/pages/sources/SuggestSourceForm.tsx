import { useState } from "react";
import { Button, Form, Input, message } from "antd";
import { SendOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { submitSourceSuggestion } from "../../api/client";

export default function SuggestSourceForm() {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (values: { name: string; url: string; description?: string }) => {
    setSubmitting(true);
    try {
      await submitSourceSuggestion(values);
      setSubmitted(true);
      form.resetFields();
    } catch {
      message.error(t("sources.suggest_submit_failed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="sources-suggest">
      <div className="sources-suggest-header">
        <h2 className="sources-suggest-title">{t("sources.suggest_title")}</h2>
        <p className="sources-suggest-desc">
          {t("sources.suggest_desc")}
        </p>
      </div>
      {submitted ? (
        <div className="sources-suggest-success">{t("sources.suggest_thanks")}</div>
      ) : (
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          className="sources-suggest-form"
        >
          <div className="sources-suggest-row">
            <Form.Item
              name="name"
              label={t("sources.suggest_name_label")}
              rules={[{ required: true, message: t("sources.suggest_name_required") }]}
              style={{ flex: 1 }}
            >
              <Input placeholder={t("sources.suggest_name_placeholder")} />
            </Form.Item>
            <Form.Item
              name="url"
              label={t("sources.suggest_url_label")}
              rules={[
                { required: true, message: t("sources.suggest_url_required") },
                { type: "url", message: t("sources.suggest_url_invalid") },
              ]}
              style={{ flex: 1 }}
            >
              <Input placeholder="https://..." />
            </Form.Item>
          </div>
          <Form.Item name="description" label={t("sources.suggest_desc_label")}>
            <Input.TextArea
              rows={3}
              placeholder={t("sources.suggest_desc_placeholder")}
              maxLength={2000}
              showCount
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={submitting}
              icon={<SendOutlined />}
              className="sources-suggest-btn"
            >
              {t("sources.suggest_submit")}
            </Button>
          </Form.Item>
        </Form>
      )}
    </div>
  );
}
