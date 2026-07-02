import { useState } from "react";
import { useTranslation } from "react-i18next";
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

const typeLabelKeys: Record<string, string> = {
  note: "reader.annotation.type.note",
  correction: "reader.annotation.type.correction",
  tag: "reader.annotation.type.tag",
};

const statusLabelKeys: Record<string, string> = {
  draft: "reader.annotation.status.draft",
  pending: "reader.annotation.status.pending",
  approved: "reader.annotation.status.approved",
  rejected: "reader.annotation.status.rejected",
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
  const { t } = useTranslation();
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
      message.success(t("reader.annotation.created"));
    },
  });

  const submitMutation = useMutation({
    mutationFn: (id: number) => api.post(`/annotations/${id}/submit`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", textId, juanNum] });
      message.success(t("reader.annotation.submitted"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/annotations/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["annotations", textId, juanNum] });
      message.success(t("reader.annotation.deleted"));
    },
  });

  return (
    <Drawer
      title={t("reader.annotation.title")}
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
        {showForm ? t("chat.cancel") : t("reader.annotation.add")}
      </Button>

      {showForm && (
        <div style={{ marginBottom: 16, padding: 12, background: "#fafafa", borderRadius: 8 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space>
              <Input
                placeholder={t("reader.annotation.start_pos")}
                aria-label={t("reader.annotation.start_pos")}
                type="number"
                value={form.start_pos}
                onChange={(e) => setForm({ ...form, start_pos: Number(e.target.value) })}
                style={{ width: 100 }}
              />
              <Input
                placeholder={t("reader.annotation.end_pos")}
                aria-label={t("reader.annotation.end_pos")}
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
                <Select.Option value="note">{t("reader.annotation.type.note")}</Select.Option>
                <Select.Option value="correction">{t("reader.annotation.type.correction")}</Select.Option>
                <Select.Option value="tag">{t("reader.annotation.type.tag")}</Select.Option>
              </Select>
            </Space>
            <Input.TextArea
              rows={3}
              placeholder={t("reader.annotation.content")}
              aria-label={t("reader.annotation.content")}
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
              {t("reader.annotation.save")}
            </Button>
          </Space>
        </div>
      )}

      {!annotations || annotations.length === 0 ? (
        <Empty description={t("reader.annotation.empty")} />
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
                    {t("reader.annotation.submit")}
                  </Button>
                ),
                <Popconfirm
                  key="delete"
                  title={t("reader.annotation.confirm_delete")}
                  description={t("reader.annotation.confirm_delete_desc")}
                  onConfirm={() => deleteMutation.mutate(ann.id)}
                  okText={t("chat.delete")}
                  cancelText={t("chat.cancel")}
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
                    <Tag>{typeLabelKeys[ann.annotation_type] ? t(typeLabelKeys[ann.annotation_type]) : ann.annotation_type}</Tag>
                    <Tag color={statusColors[ann.status]}>
                      {statusLabelKeys[ann.status] ? t(statusLabelKeys[ann.status]) : ann.status}
                    </Tag>
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
