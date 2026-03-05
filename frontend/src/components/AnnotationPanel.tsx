import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Typography,
  List,
  Button,
  Input,
  Select,
  Tag,
  Space,
  Empty,
  Drawer,
  Popconfirm,
  message,
} from "antd";
import { PlusOutlined, DeleteOutlined, SendOutlined } from "@ant-design/icons";
import api from "../api/client";

const { Text, Paragraph } = Typography;

interface Annotation {
  id: number;
  text_id: number;
  juan_num: number;
  start_pos: number;
  end_pos: number;
  annotation_type: string;
  content: string;
  user_id: number;
  status: string;
  created_at: string;
}

interface AnnotationPanelProps {
  textId: number;
  juanNum: number;
  visible: boolean;
  onClose: () => void;
}

const typeLabels: Record<string, string> = {
  note: "笔记",
  correction: "校正",
  tag: "标签",
};

const statusColors: Record<string, string> = {
  draft: "default",
  pending: "processing",
  approved: "success",
  rejected: "error",
};

export default function AnnotationPanel({
  textId,
  juanNum,
  visible,
  onClose,
}: AnnotationPanelProps) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    start_pos: 0,
    end_pos: 0,
    annotation_type: "note",
    content: "",
  });

  const { data: annotations } = useQuery<Annotation[]>({
    queryKey: ["annotations", textId, juanNum],
    queryFn: async () =>
      (await api.get("/annotations", { params: { text_id: textId, juan_num: juanNum } })).data,
    enabled: visible,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.post("/annotations", {
        text_id: textId,
        juan_num: juanNum,
        ...form,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", textId, juanNum] });
      setShowForm(false);
      setForm({ start_pos: 0, end_pos: 0, annotation_type: "note", content: "" });
      message.success("标注已创建");
    },
  });

  const submitMutation = useMutation({
    mutationFn: (id: number) => api.post(`/annotations/${id}/submit`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", textId, juanNum] });
      message.success("已提交审核");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/annotations/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", textId, juanNum] });
      message.success("已删除");
    },
  });

  return (
    <Drawer
      title="标注面板"
      placement="right"
      width={400}
      open={visible}
      onClose={onClose}
    >
      <Button
        type="dashed"
        block
        icon={<PlusOutlined />}
        onClick={() => setShowForm(!showForm)}
        style={{ marginBottom: 16 }}
      >
        {showForm ? "取消" : "新增标注"}
      </Button>

      {showForm && (
        <div style={{ marginBottom: 16, padding: 12, background: "#fafafa", borderRadius: 8 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>
              <Input
                placeholder="起始位置"
                aria-label="起始位置"
                type="number"
                value={form.start_pos}
                onChange={(e) => setForm({ ...form, start_pos: Number(e.target.value) })}
                style={{ width: 100 }}
              />
              <Input
                placeholder="结束位置"
                aria-label="结束位置"
                type="number"
                value={form.end_pos}
                onChange={(e) => setForm({ ...form, end_pos: Number(e.target.value) })}
                style={{ width: 100 }}
              />
              <Select
                value={form.annotation_type}
                onChange={(v) => setForm({ ...form, annotation_type: v })}
                style={{ width: 100 }}
              >
                <Select.Option value="note">笔记</Select.Option>
                <Select.Option value="correction">校正</Select.Option>
                <Select.Option value="tag">标签</Select.Option>
              </Select>
            </Space>
            <Input.TextArea
              rows={3}
              placeholder="标注内容"
              aria-label="标注内容"
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
            />
            <Button
              type="primary"
              size="small"
              onClick={() => createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!form.content.trim()}
            >
              保存
            </Button>
          </Space>
        </div>
      )}

      {!annotations || annotations.length === 0 ? (
        <Empty description="暂无标注" />
      ) : (
        <List
          size="small"
          dataSource={annotations}
          renderItem={(ann) => (
            <List.Item
              actions={[
                ann.status === "draft" && (
                  <Button
                    key="submit"
                    size="small"
                    icon={<SendOutlined />}
                    onClick={() => submitMutation.mutate(ann.id)}
                  >
                    提交
                  </Button>
                ),
                <Popconfirm
                  key="delete"
                  title="确认删除"
                  description="确定要删除这条标注吗？"
                  onConfirm={() => deleteMutation.mutate(ann.id)}
                  okText="删除"
                  cancelText="取消"
                >
                  <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                  />
                </Popconfirm>,
              ].filter(Boolean)}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Tag>{typeLabels[ann.annotation_type] || ann.annotation_type}</Tag>
                    <Tag color={statusColors[ann.status]}>{ann.status}</Tag>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      [{ann.start_pos}-{ann.end_pos}]
                    </Text>
                  </Space>
                }
                description={<Paragraph ellipsis={{ rows: 2 }}>{ann.content}</Paragraph>}
              />
            </List.Item>
          )}
        />
      )}
    </Drawer>
  );
}
