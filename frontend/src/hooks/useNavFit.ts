import { useLayoutEffect, useState, type RefObject } from "react";

/** 左侧（站名 + 导航）与右侧（主题 / 通知 / 语言 / 登录）之间至少留出的空隙。 */
export const NAV_MIN_GROUP_GAP = 16;

export interface NavFitRefs {
  header: RefObject<HTMLElement | null>;
  /** 站名与导航所在的左侧 Space —— 读它的 column-gap */
  leftGroup: RefObject<HTMLElement | null>;
  logo: RefObject<HTMLElement | null>;
  nav: RefObject<HTMLElement | null>;
  actions: RefObject<HTMLElement | null>;
}

/**
 * 顶栏导航整排展开放不放得下。返回 true 表示应收成汉堡。
 *
 * 为什么不用一个写死的断点：展开所需宽度随语言、角色、用户名变化（2026-10-10
 * 实测：中文游客 1002px、中文登录 1057px、英文游客 1254px、英文管理员约
 * 1470px）。断点取小了，英文与管理员在 1200–1470 照样溢出、站名被挤成竖排；
 * 取大了，中文用户在本来放得下的笔记本宽度也看不到导航。
 *
 * 判据只用各块的**自然宽度**：导航收起后并不 display:none，而是在一个零尺寸、
 * overflow:hidden 的外壳里以 max-content 宽度隐身（见 global.css 的
 * .header-nav.is-collapsed），所以收起前后量到的是同一个数 —— 判据与当前状态
 * 无关，不会在临界宽度来回抖。
 *
 * 量不到排版（jsdom、宽度为 0）时保持展开，≤768px 由 CSS 强制收起兜底。
 */
export function useNavFit(refs: NavFitRefs): boolean {
  const [collapsed, setCollapsed] = useState(false);
  const { header, leftGroup, logo, nav, actions } = refs;

  useLayoutEffect(() => {
    const measure = () => {
      const h = header.current;
      if (!h || h.clientWidth === 0) {
        setCollapsed(false);
        return;
      }
      const cs = getComputedStyle(h);
      const available =
        h.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0);
      const gap = leftGroup.current ? parseFloat(getComputedStyle(leftGroup.current).columnGap) || 0 : 0;
      const needed =
        (logo.current?.offsetWidth ?? 0) +
        gap +
        (nav.current?.offsetWidth ?? 0) +
        NAV_MIN_GROUP_GAP +
        (actions.current?.offsetWidth ?? 0);
      setCollapsed(needed > available);
    };
    measure();
    if (typeof ResizeObserver !== "function") return;
    // 头部本身（视口变宽变窄）、导航（切语言、管理员菜单出现）、右侧（登录 / 用户名、
    // 切语言）、站名（Web 字体加载完）任何一个尺寸变了都重算。
    const ro = new ResizeObserver(measure);
    for (const r of [header, nav, actions, logo]) if (r.current) ro.observe(r.current);
    return () => ro.disconnect();
  }, [header, leftGroup, logo, nav, actions]);

  return collapsed;
}
