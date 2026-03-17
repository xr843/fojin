import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Typography, Button, Space, message, Modal, Segmented } from "antd";
import { CopyOutlined, DownloadOutlined, BookOutlined } from "@ant-design/icons";
import { getTextDetail, type TextDetail } from "../api/client";
import {
  generateCitation,
  downloadCitation,
  type CitationFormat,
  type CitationMeta,
} from "../utils/citationFormats";

const { Paragraph, Text } = Typography;

interface CitationGeneratorProps {
  /** Text ID to generate citations for. */
  textId: number;
  /** If textData is already available (e.g. from parent), skip the fetch. */
  textData?: TextDetail | null;
  open: boolean;
  onClose: () => void;
}

const FORMAT_OPTIONS: { value: CitationFormat; label: string }[] = [
  { value: "bibtex", label: "BibTeX" },
  { value: "ris", label: "RIS" },
  { value: "apa", label: "APA" },
];

function buildMeta(t: TextDetail): CitationMeta {
  return {
    id: t.id,
    cbetaId: t.cbeta_id,
    titleZh: t.title_zh,
    titleEn: null,
    translator: t.translator,
    dynasty: t.dynasty,
    category: t.category,
  };
}

export default function CitationGenerator({
  textId,
  textData,
  open,
  onClose,
}: CitationGeneratorProps) {
  const [format, setFormat] = useState<CitationFormat>("bibtex");

  // Only fetch if the parent didn't pass textData
  const { data: fetched } = useQuery({
    queryKey: ["text", textId],
    queryFn: () => getTextDetail(textId),
    enabled: open && !!textId && !textData,
  });

  const text = textData ?? fetched;
  const meta = text ? buildMeta(text) : null;
  const citation = meta ? generateCitation(format, meta) : "";

  const handleCopy = async () => {
    if (!citation) return;
    try {
      await navigator.clipboard.writeText(citation);
      message.success("引用已复制到剪贴板");
    } catch {
      message.error("复制失败，请手动选择文本复制");
    }
  };

  const handleDownload = () => {
    if (!meta) return;
    downloadCitation(format, meta);
    message.success("文件已下载");
  };

  return (
    <Modal
      title={
        <Space>
          <BookOutlined /> 导出引用
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={560}
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <div>
          <Text style={{ marginRight: 8 }}>引用格式:</Text>
          <Segmented
            value={format}
            onChange={(v) => setFormat(v as CitationFormat)}
            options={FORMAT_OPTIONS}
          />
        </div>

        {citation && (
          <div
            style={{
              background: "#fafafa",
              padding: 16,
              borderRadius: 8,
              border: "1px solid #f0f0f0",
              maxHeight: 240,
              overflow: "auto",
            }}
          >
            <Paragraph
              style={{
                margin: 0,
                whiteSpace: "pre-wrap",
                fontFamily:
                  format === "apa"
                    ? "inherit"
                    : "'Fira Code', 'Cascadia Code', monospace",
                fontSize: format === "apa" ? 14 : 13,
              }}
            >
              {citation}
            </Paragraph>
          </div>
        )}

        <Space>
          <Button
            icon={<CopyOutlined />}
            onClick={handleCopy}
            disabled={!citation}
          >
            复制
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleDownload}
            disabled={!meta}
          >
            下载文件
          </Button>
        </Space>
      </Space>
    </Modal>
  );
}
