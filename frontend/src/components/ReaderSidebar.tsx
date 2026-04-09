import { useState, useEffect, memo } from "react";
import { Tabs, Drawer, Button, Badge } from "antd";
import {
  SwapOutlined,
  SearchOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { getTextRelations, getSimilarPassages } from "../api/client";
import RelatedTexts from "./RelatedTexts";
import SimilarPassages from "./SimilarPassages";
import ReaderAIPanel from "./ReaderAIPanel";

function ReaderSidebarInner({
  textId,
  juanNum,
  textTitle,
  selectedText,
  onSelectedTextConsumed,
  activeTab,
  onTabChange,
}: {
  textId: number;
  juanNum: number;
  textTitle: string;
  selectedText?: string;
  onSelectedTextConsumed?: () => void;
  activeTab?: string;
  onTabChange?: (key: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [localActiveTab, setLocalActiveTab] = useState("ai");

  const currentTab = activeTab ?? localActiveTab;
  const handleTabChange = (key: string) => {
    if (onTabChange) onTabChange(key);
    else setLocalActiveTab(key);
  };

  // Auto-expand sidebar and switch to AI tab when selectedText is set
  useEffect(() => {
    if (selectedText) {
      setCollapsed(false);
      handleTabChange("ai");
      setMobileOpen(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedText]);

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

  const tabItems = [
    {
      key: "ai",
      label: (
        <span>
          <RobotOutlined /> AI 解读
        </span>
      ),
      children: (
        <ReaderAIPanel
          textId={textId}
          juanNum={juanNum}
          textTitle={textTitle}
          selectedText={selectedText}
          onSelectedTextConsumed={onSelectedTextConsumed}
        />
      ),
    },
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
      activeKey={currentTab}
      onChange={handleTabChange}
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
          icon={<RobotOutlined />}
          className="reader-sidebar-fab"
          onClick={() => setMobileOpen(true)}
        />
        <Drawer
          title="AI 解读 & 相关内容"
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
