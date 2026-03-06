import { useState } from "react";
import { Tag, Button } from "antd";
import type { DictEntry } from "../../api/client";

export default function DictCard({ hit, rank }: { hit: DictEntry; rank: number }) {
  const [expanded, setExpanded] = useState(false);
  const needsTruncate = hit.definition.length > 300;
  const displayDef = needsTruncate && !expanded ? hit.definition.slice(0, 300) + "..." : hit.definition;
  const langLabel: Record<string, string> = { zh: "中文", pi: "巴利文", sa: "梵文", en: "英文" };

  return (
    <div className="s-card">
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title">
          {hit.headword}
          {hit.reading && <span style={{ fontSize: 14, fontWeight: 400, color: "var(--fj-ink-light)", marginLeft: 8 }}>({hit.reading})</span>}
        </div>
        <div className="s-card-tags">
          <Tag color="green" style={{ fontSize: 11 }}>{langLabel[hit.lang] || hit.lang}</Tag>
          {hit.source_name && <Tag color="volcano" style={{ fontSize: 11 }}>{hit.source_name}</Tag>}
        </div>
        <div className="s-card-meta">
          <div className="s-dict-def">{displayDef}</div>
          {needsTruncate && (
            <Button type="link" size="small" onClick={() => setExpanded(!expanded)} style={{ padding: 0, fontSize: 12 }}>
              {expanded ? "收起" : "展开全文"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
