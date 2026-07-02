import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FloatButton, Modal, Input, message, Form } from "antd";
import { CommentOutlined } from "@ant-design/icons";
import { useAuthStore } from "../stores/authStore";
import { submitFeedback } from "../api/client";

const { TextArea } = Input;

export default function FeedbackButton() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  if (!user) return null;

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);
      await submitFeedback({
        content: values.content,
        contact: values.contact || undefined,
      });
      message.success(t("feedback.submitted"));
      form.resetFields();
      setOpen(false);
    } catch {
      // validation error or API error
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <FloatButton
        icon={<CommentOutlined style={{ color: "#8b4513" }} />}
        tooltip={t("feedback.title")}
        onClick={() => setOpen(true)}
        style={{ right: 24, bottom: 24 }}
      />
      <Modal
        title={t("feedback.title")}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleSubmit}
        confirmLoading={loading}
        okText={t("feedback.submit")}
        cancelText={t("chat.cancel")}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="content"
            label={t("feedback.content_label")}
            rules={[{ required: true, message: t("feedback.content_required") }]}
          >
            <TextArea
              rows={4}
              maxLength={2000}
              showCount
              placeholder={t("feedback.content_placeholder")}
            />
          </Form.Item>
          <Form.Item
            name="contact"
            label={t("feedback.contact_label")}
          >
            <Input placeholder={t("feedback.contact_placeholder")} maxLength={200} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
