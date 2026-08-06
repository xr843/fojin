import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Input, message, Form } from "antd";
import { submitFeedback } from "../api/client";

const { TextArea } = Input;

/**
 * 意见反馈弹窗（受控）。前身是 FeedbackButton 里的 Modal —— 右下角的浮球
 * 已经让位给小津，反馈入口收进了小津气泡的底部，弹窗本体抽到这里复用。
 */
export default function FeedbackModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

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
      onClose();
    } catch {
      // validation error or API error
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={t("feedback.title")}
      open={open}
      onCancel={onClose}
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
  );
}
