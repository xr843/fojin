import { useState } from "react";
import { useParams, useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Layout, Menu, Typography, Spin, Button, Space, Tooltip, Result, Breadcrumb } from "antd";
import {
  LeftOutlined,
  RightOutlined,
  LinkOutlined,
  HighlightOutlined,
  HomeOutlined,
} from "@ant-design/icons";
import { getJuanList, getJuanContent, getTextIdentifiers } from "../api/client";
import { buildSourceReadUrl, getSourceLabel } from "../utils/sourceUrls";
import BookmarkButton from "../components/BookmarkButton";
import AnnotationPanel from "../components/AnnotationPanel";
import "../styles/reader.css";

const { Sider, Content } = Layout;

export default function ReaderPage() {
  const { textId } = useParams<{ textId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const tid = Number(textId);
  const juanParam = searchParams.get("juan");
  const currentJuan = juanParam ? Number(juanParam) : 1;
  const [annotationOpen, setAnnotationOpen] = useState(false);

  const { data: juanList, isLoading: listLoading } = useQuery({
    queryKey: ["juanList", tid],
    queryFn: () => getJuanList(tid),
    enabled: !!tid,
  });

  const { data: content, isLoading: contentLoading, isError: contentError, refetch: refetchContent } = useQuery({
    queryKey: ["juanContent", tid, currentJuan],
    queryFn: () => getJuanContent(tid, currentJuan),
    enabled: !!tid && currentJuan > 0,
  });

  const { data: identifiers } = useQuery({
    queryKey: ["textIdentifiers", tid],
    queryFn: () => getTextIdentifiers(tid),
    enabled: !!tid,
  });

  const goToJuan = (num: number) => {
    setSearchParams({ juan: String(num) });
  };

  if (listLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  const primaryIdentifier = identifiers?.[0];
  const sourceCode = primaryIdentifier?.source_code || "cbeta";
  const sourceLabel = getSourceLabel(sourceCode);
  // Prefer the identifier's explicit source_url; fall back to building from source_uid.
  // Only fall back to cbeta_id for cbeta sources where it's a valid identifier.
  const sourceReadUrl = content
    ? (primaryIdentifier?.source_url
      || (primaryIdentifier?.source_uid && buildSourceReadUrl(sourceCode, primaryIdentifier.source_uid))
      || (sourceCode === "cbeta" && buildSourceReadUrl("cbeta", content.cbeta_id))
      || null)
    : null;

  return (
    <div style={{ maxWidth: 1200, margin: "16px auto" }}>
      <Space direction="vertical" style={{ marginBottom: 12, width: "100%" }}>
        <Breadcrumb
          items={[
            { title: <span style={{ cursor: "pointer" }} onClick={() => navigate("/")}><HomeOutlined /> 首页</span> },
            { title: <span style={{ cursor: "pointer" }} onClick={() => navigate(`/texts/${tid}`)}>经典详情</span> },
            { title: "阅读" },
          ]}
        />
        {content && (
          <Typography.Title level={4} style={{ margin: 0 }}>
            {content.title_zh}
          </Typography.Title>
        )}
      </Space>

      <Layout style={{ background: "#fff", borderRadius: 8, overflow: "hidden" }}>
        {/* Sider: juan list */}
        <Sider
          width={180}
          style={{ background: "#fafafa", borderRight: "1px solid #f0f0f0" }}
          breakpoint="md"
          collapsedWidth={0}
        >
          <div style={{ padding: "12px 0", fontWeight: 600, textAlign: "center", borderBottom: "1px solid #f0f0f0" }}>
            卷目录
          </div>
          <Menu
            mode="inline"
            selectedKeys={[String(currentJuan)]}
            style={{ border: "none", background: "transparent" }}
            onClick={({ key }) => goToJuan(Number(key))}
            items={
              juanList?.juans.map((j) => ({
                key: String(j.juan_num),
                label: `第${j.juan_num}卷`,
              })) ?? []
            }
          />
        </Sider>

        {/* Content area */}
        <Content style={{ minHeight: 500 }}>
          {/* Top toolbar */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 16px", borderBottom: "1px solid #f0f0f0" }}>
            <Typography.Text type="secondary">
              {content ? `第 ${content.juan_num} / ${content.total_juans} 卷` : ""}
              {content ? ` · ${content.char_count.toLocaleString()} 字` : ""}
            </Typography.Text>
            <Space>
              {tid && <BookmarkButton textId={tid} />}
              <Tooltip title="标注">
                <Button
                  type="text"
                  icon={<HighlightOutlined />}
                  onClick={() => setAnnotationOpen(true)}
                  aria-label="标注"
                />
              </Tooltip>
              {sourceReadUrl && (
                <Tooltip title={`${sourceLabel} 原站阅读`}>
                  <a href={sourceReadUrl} target="_blank" rel="noopener noreferrer">
                    <Button type="text" icon={<LinkOutlined />} aria-label="前往原站阅读" />
                  </a>
                </Tooltip>
              )}
            </Space>
          </div>

          {/* Content */}
          {contentLoading ? (
            <div style={{ textAlign: "center", padding: 80 }}>
              <Spin size="large" />
            </div>
          ) : contentError ? (
            <Result
              status="error"
              title="加载失败"
              subTitle="经文内容加载出错，请稍后重试。"
              extra={<Button type="primary" onClick={() => refetchContent()}>重试</Button>}
            />
          ) : content ? (
            <div className="reader-content">{content.content}</div>
          ) : (
            <div style={{ textAlign: "center", padding: 80 }}>
              <Typography.Text type="secondary">暂无内容</Typography.Text>
            </div>
          )}

          {/* Bottom navigation */}
          {content && (
            <div className="reader-nav" style={{ padding: "12px 16px", borderTop: "1px solid #f0f0f0" }}>
              <Button
                icon={<LeftOutlined />}
                disabled={!content.prev_juan}
                onClick={() => content.prev_juan && goToJuan(content.prev_juan)}
              >
                上一卷
              </Button>
              <Typography.Text type="secondary">
                第 {content.juan_num} 卷
              </Typography.Text>
              <Button
                disabled={!content.next_juan}
                onClick={() => content.next_juan && goToJuan(content.next_juan)}
              >
                下一卷 <RightOutlined />
              </Button>
            </div>
          )}
        </Content>
      </Layout>

      {tid && (
        <AnnotationPanel
          textId={tid}
          juanNum={currentJuan}
          visible={annotationOpen}
          onClose={() => setAnnotationOpen(false)}
        />
      )}
    </div>
  );
}
