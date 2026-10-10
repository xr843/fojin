import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Checkbox } from "antd";
import { DownOutlined, FilterOutlined } from "@ant-design/icons";
import { useNarrowViewport } from "../../hooks/useNarrowViewport";
import { localizedSourceName } from "../../utils/sourceName";

/**
 * 搜索页的手机断点。与 search.css 的「响应式」块（max-width: 768px）同一个数，
 * 改一处必须改另一处——CSS 管排版，这里管「默认折叠」。
 */
export const SEARCH_NARROW_QUERY = "(max-width: 768px)";

/**
 * 可内滚的分面列表。内容还没滚到底时挂 data-more，CSS 据此在底部做渐隐遮罩：
 * 既提示「下面还有」，也不再把最后一行字横切成半截（生产 390px 实测「斯里兰卡」
 * 被 max-height 切掉一半）。滚到底时去掉遮罩，最后一项完整可读。
 *
 * 直接写 DOM 属性而不走 state：滚动是高频事件，没必要为一个遮罩开关重渲染整个侧栏。
 */
function FilterScroll({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const more = el.scrollHeight - el.scrollTop - el.clientHeight > 1;
      if (more) el.dataset.more = "1";
      else delete el.dataset.more;
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    // 数据源列表是异步到的、窗口也会变宽变窄：内容或容器尺寸一变就重判一次。
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(update) : null;
    ro?.observe(el);
    if (innerRef.current) ro?.observe(innerRef.current);
    return () => {
      el.removeEventListener("scroll", update);
      ro?.disconnect();
    };
  }, []);
  return (
    <div className="s-filter-scroll" ref={ref}>
      <div ref={innerRef}>{children}</div>
    </div>
  );
}

interface Props {
  regions: string[];
  regionCounts: Record<string, number>;
  regionFilter: Set<string>;
  onToggleRegion: (r: string) => void;
  institutions: Array<{ name: string; nameEn: string | null; count: number }>;
  institutionFilter: Set<string>;
  onToggleInstitution: (name: string) => void;
}

/**
 * 搜索页左侧分面（国家/地区、馆藏）。
 *
 * 桌面：与原来完全相同，侧栏常驻。
 * 手机（≤768px）：结果优先——默认折叠成一个「筛选」按钮（带已选条件数），点开在原地展开。
 * 选原地展开而不是 Drawer：这两组分面只筛下方的「外部数据源」区，Drawer 会把结果整个
 * 盖住、用户看不到勾选的效果；原地展开不抢焦点、不需要遮罩和关闭按钮，收起后已选条件
 * 仍保存在父组件的 state 里。
 */
export default function SearchFilterSidebar({
  regions,
  regionCounts,
  regionFilter,
  onToggleRegion,
  institutions,
  institutionFilter,
  onToggleInstitution,
}: Props) {
  const { t } = useTranslation();
  const narrow = useNarrowViewport(SEARCH_NARROW_QUERY);
  const [open, setOpen] = useState(false);
  const panelId = useId();

  const groups = (
    <>
      <div className="s-filter-group">
        <div className="s-filter-title">🌐 {t("search.filter_region")}</div>
        <FilterScroll>
          {regions.map((r) => (
            <label key={r} className="s-filter-item">
              <Checkbox checked={regionFilter.has(r)} onChange={() => onToggleRegion(r)} />
              <span className="s-filter-name">{t(`region.${r}`, r)}</span>
              <span className="s-filter-count">{regionCounts[r]}</span>
            </label>
          ))}
        </FilterScroll>
      </div>

      <div className="s-filter-group">
        <div className="s-filter-title">🏛 {t("search.filter_institution")}</div>
        <FilterScroll>
          {institutions.map(({ name, nameEn, count }) => (
            <label key={name} className="s-filter-item">
              <Checkbox checked={institutionFilter.has(name)} onChange={() => onToggleInstitution(name)} />
              <span className="s-filter-name">{localizedSourceName({ name_zh: name, name_en: nameEn })}</span>
              <span className="s-filter-count">{count}</span>
            </label>
          ))}
        </FilterScroll>
      </div>
    </>
  );

  if (!narrow) return <aside className="s-sidebar">{groups}</aside>;

  const selected = regionFilter.size + institutionFilter.size;
  return (
    <aside className="s-sidebar">
      <button
        type="button"
        className={`s-filter-toggle${selected > 0 ? " is-active" : ""}`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <FilterOutlined />
        <span>{selected > 0 ? t("search.filter_toggle_count", { n: selected }) : t("search.filter_toggle")}</span>
        <DownOutlined className="s-filter-toggle-caret" rotate={open ? 180 : 0} />
      </button>
      {open && (
        <div id={panelId} className="s-filter-panel">
          {groups}
        </div>
      )}
    </aside>
  );
}
