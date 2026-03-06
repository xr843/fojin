import { Typography, Tag, Space } from "antd";
import { UserOutlined, RobotOutlined, BookOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

const { Paragraph, Text } = Typography;

interface ChatSource {
  text_id: number;
  juan_num: number;
  chunk_text: string;
  score: number;
}

interface ChatBubbleProps {
  role: "user" | "assistant";
  content: string;
  sources?: ChatSource[] | null;
}

export default function ChatBubble({ role, content, sources }: ChatBubbleProps) {
  const navigate = useNavigate();
  const isUser = role === "user";

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 16,
      }}
    >
      <div
        style={{
          maxWidth: "75%",
          padding: "12px 16px",
          borderRadius: 12,
          background: isUser ? "#1a1a2e" : "#f5f5f5",
          color: isUser ? "#fff" : "#333",
        }}
      >
        <div style={{ marginBottom: 4, fontSize: 12, opacity: 0.7 }}>
          {isUser ? (
            <Space size={4}>
              <UserOutlined /> 你
            </Space>
          ) : (
            <Space size={4}>
              <RobotOutlined /> 佛津 AI
            </Space>
          )}
        </div>
        <Paragraph
          style={{
            margin: 0,
            color: isUser ? "#fff" : "#333",
            whiteSpace: "pre-wrap",
          }}
        >
          {content}
        </Paragraph>
        {sources && sources.length > 0 && (
          <div style={{ marginTop: 8, borderTop: "1px solid #e0e0e0", paddingTop: 8 }}>
            <Text style={{ fontSize: 12, color: "#999" }}>
              <BookOutlined /> 引用来源:
            </Text>
            <div style={{ marginTop: 4 }}>
              {sources.map((s, i) => (
                <Tag
                  key={i}
                  style={{ marginBottom: 4, cursor: "pointer" }}
                  onClick={() => navigate(`/texts/${s.text_id}`)}
                >
                  文本 #{s.text_id} 第{s.juan_num}卷
                  <Text style={{ fontSize: 11, color: "#999" }}>
                    {" "}
                    ({(s.score * 100).toFixed(0)}%)
                  </Text>
                </Tag>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
