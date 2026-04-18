import { useState } from "react";
import { Button, Form, Input, message } from "antd";
import { SendOutlined } from "@ant-design/icons";
import { submitSourceSuggestion } from "../../api/client";

export default function SuggestSourceForm() {
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
      message.error("提交失败，请稍后再试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="sources-suggest">
      <div className="sources-suggest-header">
        <h2 className="sources-suggest-title">推荐数据源</h2>
        <p className="sources-suggest-desc">
          如果您知道尚未收录的佛教数字资源网站，欢迎推荐给我们
        </p>
      </div>
      {submitted ? (
        <div className="sources-suggest-success">感谢您的推荐！我们会尽快查阅。</div>
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
              label="网站名称"
              rules={[{ required: true, message: "请输入网站名称" }]}
              style={{ flex: 1 }}
            >
              <Input placeholder="例：CBETA 在线阅读" />
            </Form.Item>
            <Form.Item
              name="url"
              label="网站 URL"
              rules={[
                { required: true, message: "请输入网站地址" },
                { type: "url", message: "请输入有效的网址" },
              ]}
              style={{ flex: 1 }}
            >
              <Input placeholder="https://..." />
            </Form.Item>
          </div>
          <Form.Item name="description" label="简要说明">
            <Input.TextArea
              rows={3}
              placeholder="简要描述该网站收录的内容、语种、特色等（选填）"
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
              提交推荐
            </Button>
          </Form.Item>
        </Form>
      )}
    </div>
  );
}
