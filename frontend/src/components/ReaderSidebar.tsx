import { useState, memo } from "react";
import { Tabs, Drawer, Button, Badge } from "antd";
import {
  SwapOutlined,
  SearchOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { getTextRelations, getSimilarPassages } from "../api/client";
import RelatedTexts from "./RelatedTexts";
import SimilarPassages from "./SimilarPassages";

function ReaderSidebarInner({
  textId,
  juanNum,
}: {
  textId: number;
  juanNum: number;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Prefetch counts for badge display
  const { data: relData } = useQuery({
    queryKey: ["relations", textId],
    queryFn: () => getTextRelations(textId),
    enabled: !!textId,
  });

  const { data: simData } = useQuery({
    queryKey: ["similarPassages", textId, juanNum],
    queryFn: () => getSimilarPassages(textId, juanNum),
    enabled: !!textId && !!juanNum,
    staleTime: 600_000,
  });

  const relCount = relData?.relations.length || 0;
  const simCount = simData?.passages.length || 0;
  const totalCount = relCount + simCount;

  if (totalCount === 0 && relData && simData) {
    return null; // No data to show
  }

  const tabItems = [
    {
      key: "related",
      label: (
        <span>
          <SwapOutlined /> 相关经典
          {relCount > 0 && (
            <Badge
              count={relCount}
              size="small"
              style={{ marginLeft: 6, backgroundColor: "var(--fj-gold)" }}
            />
          )}
        </span>
      ),
      children: <RelatedTexts textId={textId} />,
    },
    {
      key: "similar",
      label: (
        <span>
          <SearchOutlined /> 相似段落
          {simCount > 0 && (
            <Badge
              count={simCount}
              size="small"
              style={{ marginLeft: 6, backgroundColor: "#1677ff" }}
            />
          )}
        </span>
      ),
      children: <SimilarPassages textId={textId} juanNum={juanNum} />,
    },
  ];

  const sidebarContent = (
    <Tabs
      defaultActiveKey="similar"
      items={tabItems}
      size="small"
      style={{ height: "100%" }}
    />
  );

  return (
    <>
      {/* Desktop: inline sidebar */}
      <div className="reader-sidebar-desktop">
        {collapsed ? (
          <Button
            type="text"
            icon={<MenuUnfoldOutlined />}
            onClick={() => setCollapsed(false)}
            className="reader-sidebar-toggle"
            title="展开侧边栏"
          />
        ) : (
          <div className="reader-sidebar-panel">
            <div className="reader-sidebar-header">
              <Button
                type="text"
                size="small"
                icon={<MenuFoldOutlined />}
                onClick={() => setCollapsed(true)}
              />
            </div>
            {sidebarContent}
          </div>
        )}
      </div>

      {/* Mobile: bottom drawer trigger */}
      <div className="reader-sidebar-mobile">
        <Button
          shape="circle"
          type="primary"
          icon={<SearchOutlined />}
          className="reader-sidebar-fab"
          onClick={() => setMobileOpen(true)}
        >
          {totalCount > 0 && (
            <Badge
              count={totalCount}
              size="small"
              offset={[8, -8]}
              style={{ backgroundColor: "var(--fj-accent)" }}
            />
          )}
        </Button>
        <Drawer
          title="相关内容"
          placement="bottom"
          height="70vh"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
        >
          {sidebarContent}
        </Drawer>
      </div>
    </>
  );
}

export default memo(ReaderSidebarInner);
