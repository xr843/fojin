import { useState } from "react";
import { FloatButton, Modal, Input, message, Form } from "antd";
import { CommentOutlined } from "@ant-design/icons";
import { useAuthStore } from "../stores/authStore";
import { submitFeedback } from "../api/client";

const { TextArea } = Input;

export default function FeedbackButton() {
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
      message.success("反馈已提交，感谢您的意见！");
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
        tooltip="意见反馈"
        onClick={() => setOpen(true)}
        style={{ right: 24, bottom: 24 }}
      />
      <Modal
        title="意见反馈"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleSubmit}
        confirmLoading={loading}
        okText="提交"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="content"
            label="反馈内容"
            rules={[{ required: true, message: "请输入反馈内容" }]}
          >
            <TextArea
              rows={4}
              maxLength={2000}
              showCount
              placeholder="请描述您的建议、问题或意见..."
            />
          </Form.Item>
          <Form.Item
            name="contact"
            label="联系方式（选填）"
          >
            <Input placeholder="邮箱或其他联系方式，方便我们回复您" maxLength={200} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
