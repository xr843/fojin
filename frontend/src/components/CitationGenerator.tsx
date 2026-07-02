import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t, i18n } = useTranslation();
  const [format, setFormat] = useState<CitationFormat>("bibtex");

  // Only fetch if the parent didn't pass textData
  const { data: fetched } = useQuery({
    queryKey: ["text", textId],
    queryFn: () => getTextDetail(textId),
    enabled: open && !!textId && !textData,
  });

  const text = textData ?? fetched;
  const meta = text ? buildMeta(text) : null;
  const citationOptions = {
    apaLocale: i18n.language.startsWith("en")
      ? "en-US"
      : i18n.language.startsWith("zh-Hant")
      ? "zh-Hant"
      : "zh-CN",
    siteName: t("reader.citation_generator.site_name"),
    accessedLabel: t("reader.citation_generator.accessed"),
  };
  const citation = meta ? generateCitation(format, meta, citationOptions) : "";

  const handleCopy = async () => {
    if (!citation) return;
    try {
      await navigator.clipboard.writeText(citation);
      message.success(t("reader.citation_generator.copied"));
    } catch {
      message.error(t("reader.citation_generator.copy_failed"));
    }
  };

  const handleDownload = () => {
    if (!meta) return;
    downloadCitation(format, meta, citationOptions);
    message.success(t("reader.citation_generator.downloaded"));
  };

  return (
    <Modal
      title={
        <Space>
          <BookOutlined /> {t("reader.citation_generator.title")}
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={560}
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <div>
          <Text style={{ marginRight: 8 }}>{t("reader.citation_generator.format_label")}</Text>
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
            {t("chat.copy")}
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={handleDownload}
            disabled={!meta}
          >
            {t("reader.citation_generator.download")}
          </Button>
        </Space>
      </Space>
    </Modal>
  );
}
