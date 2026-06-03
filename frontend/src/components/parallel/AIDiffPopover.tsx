import { Card, Tag, Spin, Alert, Button } from "antd";
import { CloseOutlined, RobotOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { postAiDiff, type AiDiffChunkInput, type AiDiffResponse } from "../../api/client";

interface Props {
  chunks: AiDiffChunkInput[];
  onClose: () => void;
  /** Override for testing; defaults to postAiDiff. */
  fetchAiDiff?: (chunks: AiDiffChunkInput[]) => Promise<AiDiffResponse>;
}

function chunksKey(chunks: AiDiffChunkInput[]): string {
  return chunks
    .map((c) => `${c.text_id}-${c.juan_num}-${c.chunk_index}`)
    .sort()
    .join("|");
}

export default function AIDiffPopover({ chunks, onClose, fetchAiDiff = postAiDiff }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["ai-diff", chunksKey(chunks)],
    queryFn: () => fetchAiDiff(chunks),
    enabled: chunks.length >= 2,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });

  return (
    <Card
      className="ai-diff-popover"
      size="small"
      title={
        <div className="ai-diff-popover-header">
          <RobotOutlined /> <span>AI 差异分析</span>
          {data?.cached && <Tag color="default">缓存</Tag>}
          <Button
            type="text"
            size="small"
            icon={<CloseOutlined />}
            onClick={onClose}
            aria-label="关闭"
            style={{ marginLeft: "auto" }}
          />
        </div>
      }
    >
      {isLoading && (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin />
          <div style={{ marginTop: 8, color: "#888", fontSize: 13 }}>正在生成差异分析…</div>
        </div>
      )}
      {isError && (
        <Alert
          type="error"
          showIcon
          message="分析失败"
          description="请稍后重试。"
          style={{ margin: "8px 0" }}
        />
      )}
      {data && (
        <div className="ai-diff-popover-body">
          {data.analysis.summary && (
            <p className="ai-diff-summary">{data.analysis.summary}</p>
          )}
          {data.analysis.differences && data.analysis.differences.length > 0 && (
            <>
              <div className="ai-diff-section-label">差异</div>
              <ul className="ai-diff-differences">
                {data.analysis.differences.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </>
          )}
          {data.analysis.doctrinal_notes && (
            <>
              <div className="ai-diff-section-label">教义注</div>
              <p className="ai-diff-doctrinal">{data.analysis.doctrinal_notes}</p>
            </>
          )}
          <div className="ai-diff-meta">
            <span>{data.model}</span>
            <span style={{ marginLeft: 8 }}>prompt {data.prompt_version}</span>
          </div>
        </div>
      )}
    </Card>
  );
}
