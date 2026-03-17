import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Typography, Spin, Row, Col, Card, Select, InputNumber, Space, Empty, Button, Result } from "antd";
import { SwapOutlined, ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { getParallelRead, getTextRelations } from "../api/client";
import "../styles/parallel.css";

const { Title, Paragraph } = Typography;

export default function ParallelReaderPage() {
  const { textId } = useParams<{ textId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const compareId = searchParams.get("compare");
  const juan = Number(searchParams.get("juan") || "1");

  const { data: relations } = useQuery({
    queryKey: ["relations", textId],
    queryFn: () => getTextRelations(Number(textId)),
    enabled: !!textId,
  });

  const { data: parallel, isLoading, isError, refetch } = useQuery({
    queryKey: ["parallel", textId, compareId, juan],
    queryFn: () => getParallelRead(Number(textId), Number(compareId), juan),
    enabled: !!textId && !!compareId,
  });

  const handleCompareChange = (value: number) => {
    setSearchParams({ compare: String(value), juan: String(juan) });
  };

  const handleJuanChange = (value: number | null) => {
    if (value && compareId) {
      setSearchParams({ compare: compareId, juan: String(value) });
    }
  };

  return (
    <div className="parallel-container">
      <div className="parallel-header">
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
          返回
        </Button>
        <Title level={3} style={{ margin: 0 }}>
          <SwapOutlined /> 平行对照阅读
        </Title>
      </div>

      <Card size="small" style={{ marginBottom: 16 }} className="parallel-controls">
        <Space wrap>
          <span>对照版本：</span>
          <Select
            placeholder="选择对照文本"
            value={compareId ? Number(compareId) : undefined}
            onChange={handleCompareChange}
            options={
              relations?.relations.map((r) => ({
                value: r.text_id,
                label: `${r.title_zh} (${r.translator || "佚名"} · ${r.dynasty || ""}) [${r.relation_type}]`,
              })) || []
            }
          />
          <span>卷：</span>
          <InputNumber min={1} value={juan} onChange={handleJuanChange} />
        </Space>
      </Card>

      {!compareId ? (
        <Empty description="请选择对照文本" />
      ) : isLoading ? (
        <div style={{ textAlign: "center", padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : isError ? (
        <Result
          status="error"
          title="加载失败"
          subTitle="对照内容加载出错，请稍后重试。"
          extra={<Button type="primary" onClick={() => refetch()}>重试</Button>}
        />
      ) : !parallel ? (
        <Empty description="对照内容未找到" />
      ) : (
        <Row gutter={[16, 12]} className="parallel-columns">
          <Col xs={24} md={12}>
            <Card
              title={
                <span>
                  {parallel.text_a.title_zh}
                  {parallel.text_a.translator && (
                    <span style={{ fontWeight: "normal", fontSize: 13, marginLeft: 8, color: "#888" }}>
                      {parallel.text_a.translator}
                    </span>
                  )}
                </span>
              }
              size="small"
            >
              <div className="parallel-reader-col">
                <div className="reader-content">
                  {parallel.text_a.content || <Paragraph type="secondary">暂无内容</Paragraph>}
                </div>
              </div>
            </Card>
          </Col>
          <Col xs={24} md={12}>
            <Card
              title={
                <span>
                  {parallel.text_b.title_zh}
                  {parallel.text_b.translator && (
                    <span style={{ fontWeight: "normal", fontSize: 13, marginLeft: 8, color: "#888" }}>
                      {parallel.text_b.translator}
                    </span>
                  )}
                </span>
              }
              size="small"
            >
              <div className="parallel-reader-col">
                <div className="reader-content">
                  {parallel.text_b.content || <Paragraph type="secondary">暂无内容</Paragraph>}
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      )}
    </div>
  );
}
