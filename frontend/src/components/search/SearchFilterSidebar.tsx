import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Checkbox } from "antd";
import { BookOutlined, ClockCircleOutlined, DownOutlined, FilterOutlined, PartitionOutlined, TranslationOutlined } from "@ant-design/icons";
import type { SearchFacets } from "../../api/client";
import { getDynastyLabel } from "../../data/dynasty_years";
import { useNarrowViewport } from "../../hooks/useNarrowViewport";
import {
  FACET_GROUPS,
  countSelected,
  facetItems,
  type FacetGroup,
  type FacetSelection,
} from "../../utils/searchFacets";

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
  /** 当前结果集的分面计数；旧后端 / 首次加载时为 undefined。 */
  facets: SearchFacets | null | undefined;
  selection: FacetSelection;
  onToggle: (group: FacetGroup, key: string) => void;
  onClear: () => void;
}

const SONG = "宋"; // i18n-exempt —— 后端朝代原值

const GROUP_ICON: Record<FacetGroup, ReactNode> = {
  canon: <BookOutlined className="s-head-icon" aria-hidden="true" />,
  lang: <TranslationOutlined className="s-head-icon" aria-hidden="true" />,
  dynasty: <ClockCircleOutlined className="s-head-icon" aria-hidden="true" />,
  section: <PartitionOutlined className="s-head-icon" aria-hidden="true" />,
};

/**
 * 搜索页左侧分面：藏经 / 语言 / 朝代 / 部类。组内多选为「或」，组间为「且」；
 * 每组的计数已扣除其它组的筛选、不扣本组（勾了大正藏，卍续藏的数字不会变 0）。
 * 某组在当前结果里一个取值都没有（如巴利文结果没有朝代、非大正藏没有部类）就整组不显示。
 *
 * 桌面：侧栏常驻。
 * 手机（≤768px）：结果优先——默认折叠成一个「筛选」按钮（带已选条件数），点开在原地展开。
 * 原地展开而不是 Drawer：勾选后下方结果即时刷新，Drawer 会把结果整个盖住、看不到效果；
 * 原地展开不抢焦点、不需要遮罩和关闭按钮；已选条件在 URL 里，收起、刷新、后退都保留。
 */
export default function SearchFilterSidebar({ facets, selection, onToggle, onClear }: Props) {
  const { t, i18n } = useTranslation();
  const narrow = useNarrowViewport(SEARCH_NARROW_QUERY);
  const [open, setOpen] = useState(false);
  const panelId = useId();

  const label = (group: FacetGroup, key: string): string => {
    if (group === "lang") return t(`lang.${key}`, key);
    if (group === "canon") return t(`search.canon.${key}`, key);
    if (group === "section") return t(`search.section.${key}`, key);
    // 后端「宋」含南宋；朝代表把它当北宋的别名，直接借用会显示成「北宋」。
    if (key === SONG) return t("search.facet_dynasty_song");
    return getDynastyLabel(key, i18n.language);
  };

  const selected = countSelected(selection);
  const visible = FACET_GROUPS.map((group) => ({ group, items: facetItems(group, facets, selection[group]) })).filter(
    (g) => g.items.length > 0,
  );

  const groups = (
    <>
      {visible.map(({ group, items }) => (
        <div className="s-filter-group" key={group}>
          <div className="s-filter-title">
            {GROUP_ICON[group]}
            {t(`search.facet_${group}`)}
          </div>
          <FilterScroll>
            {items.map(({ key, count }) => (
              <label key={key} className="s-filter-item">
                <Checkbox checked={selection[group].includes(key)} onChange={() => onToggle(group, key)} />
                <span className="s-filter-name">{label(group, key)}</span>
                {count !== null && <span className="s-filter-count">{count.toLocaleString()}</span>}
              </label>
            ))}
          </FilterScroll>
        </div>
      ))}
      {selected > 0 && (
        <button type="button" className="s-filter-clear" onClick={onClear}>
          {t("search.facet_clear")}
        </button>
      )}
    </>
  );

  if (!narrow) return <aside className="s-sidebar">{groups}</aside>;

  // 手机上没有任何可选项（旧后端 / 结果还没到）就不摆一个点开是空的按钮。
  if (visible.length === 0 && selected === 0) return null;

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
