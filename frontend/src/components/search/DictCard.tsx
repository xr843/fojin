import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Tag, Button } from "antd";
import type { DictEntry } from "../../api/client";

const LANG_KEYS: Record<string, string> = { zh: "lang.zh", pi: "lang.pi", sa: "lang.sa", en: "lang.en" };

export default function DictCard({ hit, rank }: { hit: DictEntry; rank: number }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const needsTruncate = hit.definition.length > 300;
  const displayDef = needsTruncate && !expanded ? hit.definition.slice(0, 300) + "..." : hit.definition;

  return (
    <div className="s-card">
      <div className="s-card-rank">{t("search.rank")}<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title">
          {hit.headword}
          {hit.reading && <span style={{ fontSize: 14, fontWeight: 400, color: "var(--fj-ink-light)", marginLeft: 8 }}>({hit.reading})</span>}
        </div>
        <div className="s-card-tags">
          <Tag color="green" style={{ fontSize: 11 }}>{LANG_KEYS[hit.lang] ? t(LANG_KEYS[hit.lang]) : hit.lang}</Tag>
          {hit.source_name && <Tag color="volcano" style={{ fontSize: 11 }}>{hit.source_name}</Tag>}
        </div>
        <div className="s-card-meta">
          <div className="s-dict-def">{displayDef}</div>
          {needsTruncate && (
            <Button type="link" size="small" onClick={() => setExpanded(!expanded)} style={{ padding: 0, fontSize: 12 }}>
              {expanded ? t("search.collapse") : t("search.expand_fulltext")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
