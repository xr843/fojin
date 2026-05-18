/**
 * KGPathQuery — 两实体间最短关系路径查询面板
 *
 * 起点：当前已选实体（由父页面通过 fromEntity prop 传入）。
 * 终点：本组件内置的搜索框（复用 searchKGEntities）。
 * 结果：调用 getKGPath，用 ForceGraph 渲染路径子图。
 */
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Spin, Empty, Alert, Select } from "antd";
import { SwapRightOutlined, SearchOutlined } from "@ant-design/icons";
import ForceGraph from "../ForceGraph";
import { searchKGEntities, getKGPath } from "../../api/client";
import type { KGEntity, KGPathResponse } from "../../api/client";

interface KGPathQueryProps {
  /** 起始实体（当前已选）。null 时面板显示提示，禁用查询按钮。 */
  fromEntity: KGEntity | null;
  /** 点击路径节点时通知父页面（同步主图选中状态） */
  onNodeClick?: (node: { id: number }) => void;
}

// 路径图高度固定，较主图小，嵌入面板用
const PATH_GRAPH_HEIGHT = 320;

export default function KGPathQuery({ fromEntity, onNodeClick }: KGPathQueryProps) {
  const [toQuery, setToQuery] = useState("");
  const [toEntity, setToEntity] = useState<KGEntity | null>(null);
  // 当前提交的查询参数；null = 尚未提交
  const [pendingQuery, setPendingQuery] = useState<{
    fromId: number;
    toId: number;
    maxHops: number;
  } | null>(null);

  // 搜索终点实体
  const { data: searchResults, isFetching: searching } = useQuery({
    queryKey: ["kg-path-search", toQuery],
    queryFn: () => searchKGEntities(toQuery, undefined, 10),
    enabled: toQuery.trim().length > 0,
    staleTime: 30_000,
  });

  // 执行路径查询（仅在 pendingQuery 非 null 时触发）
  const {
    data: pathResult,
    isFetching: loadingPath,
    error: pathError,
  } = useQuery<KGPathResponse>({
    queryKey: [
      "kg-path",
      pendingQuery?.fromId,
      pendingQuery?.toId,
      pendingQuery?.maxHops,
    ],
    queryFn: () =>
      getKGPath(pendingQuery!.fromId, pendingQuery!.toId, pendingQuery!.maxHops),
    enabled: pendingQuery !== null,
    staleTime: 0,
  });

  const handleSearch = useCallback((value: string) => {
    setToQuery(value.trim());
    setToEntity(null); // 重置已选终点
  }, []);

  const handleSelectTo = useCallback((entity: KGEntity) => {
    setToEntity(entity);
    setToQuery(entity.name_zh);
  }, []);

  const handleSubmit = useCallback(() => {
    if (!fromEntity || !toEntity) return;
    setPendingQuery({ fromId: fromEntity.id, toId: toEntity.id, maxHops: 6 });
  }, [fromEntity, toEntity]);

  const canSubmit = !!fromEntity && !!toEntity;

  // 下拉选项：搜索结果列表（排除起点自身）
  const options = (searchResults?.results || [])
    .filter((e) => e.id !== fromEntity?.id)
    .map((e) => ({
      value: e.id,
      label: (
        <span>
          {e.name_zh}
          <span style={{ color: "#9a8e7a", fontSize: 11, marginLeft: 6 }}>
            {e.entity_type}
          </span>
        </span>
      ),
    }));

  return (
    <div className="kg-path-panel">
      <div className="kg-path-title">路径查询</div>

      {/* 起终点选择行 */}
      <div className="kg-path-row">
        {/* 起点 — 固定为当前选中实体 */}
        <div className="kg-path-endpoint">
          <span className="kg-path-label">起点</span>
          <span className="kg-path-entity-name">
            {fromEntity ? fromEntity.name_zh : <em style={{ color: "#bbb5a6" }}>请先选择实体</em>}
          </span>
        </div>

        <SwapRightOutlined className="kg-path-arrow" />

        {/* 终点 — 搜索选择 */}
        <div className="kg-path-endpoint">
          <span className="kg-path-label">终点</span>
          <Select
            showSearch
            value={toEntity ? toEntity.name_zh : undefined}
            placeholder="搜索目标实体…"
            filterOption={false}
            notFoundContent={
              searching
                ? <Spin size="small" />
                : toQuery.length
                ? "未找到匹配实体"
                : null
            }
            options={options}
            onSearch={handleSearch}
            onSelect={(_val, opt) => {
              const found = (searchResults?.results || []).find(
                (e) => e.id === (opt as { value: number }).value,
              );
              if (found) handleSelectTo(found);
            }}
            style={{ width: 200 }}
            suffixIcon={<SearchOutlined />}
          />
        </div>

        <Button
          type="primary"
          disabled={!canSubmit}
          loading={loadingPath}
          onClick={handleSubmit}
          style={{ marginLeft: "auto" }}
        >
          查找路径
        </Button>
      </div>

      {/* 结果区域 */}
      {loadingPath && (
        <div className="kg-path-result-empty">
          <Spin />
        </div>
      )}

      {!loadingPath && pathError && (
        <Alert
          type="error"
          showIcon
          message="路径查询失败，请稍后重试"
          style={{ marginTop: 12 }}
        />
      )}

      {!loadingPath && pathResult && (
        pathResult.found ? (
          <div className="kg-path-result">
            <div className="kg-path-meta">
              找到路径：{pathResult.hops} 跳，共 {pathResult.nodes.length} 个实体
            </div>
            <ForceGraph
              nodes={pathResult.nodes}
              links={pathResult.links}
              height={PATH_GRAPH_HEIGHT}
              onNodeClick={onNodeClick}
            />
          </div>
        ) : (
          <div className="kg-path-result-empty">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={`未找到 6 跳以内的路径`}
            />
          </div>
        )
      )}
    </div>
  );
}
