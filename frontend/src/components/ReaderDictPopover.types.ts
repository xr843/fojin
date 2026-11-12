import type { DictGroupedSearchResponse } from "../api/client";

/** 划词查辞典浮层状态 */
export interface DictPopoverState {
  visible: boolean;
  text: string;
  x: number;
  /** 选区底边（视口坐标） */
  y: number;
  /** 选区顶边（视口坐标）；浮层翻到上方时锚在它之上，不盖住选中的那一行 */
  selTop: number;
  loading: boolean;
  result: DictGroupedSearchResponse | null;
}

export const DICT_POPOVER_INIT: DictPopoverState = {
  visible: false,
  text: "",
  x: 0,
  y: 0,
  selTop: 0,
  loading: false,
  result: null,
};

/** 超过此长度视为「整句选择」：只提供问小津，不查辞典 */
export const MAX_WORD_LEN = 20;

/** 浮层估计高度，须与 reader.css 的 .reader-dict-popover 一致（2026-11-08 字号放大后约 400） */
export const DICT_POPOVER_HEIGHT = 400;

/**
 * 选区下方放不下浮层时，浮层翻到选区上方。行号浮条（复制引用 / 行首 / SAT 原页）
 * 平时在选区上方，此时要改到选区下方让位——否则浮条正好压在浮层底部的释义上
 * （2026-11-12 用户截图：普賢菩薩一条被浮条盖住两行）。
 */
export function dictPopoverAbove(selBottom: number, viewportH: number): boolean {
  return selBottom + 8 + DICT_POPOVER_HEIGHT > viewportH - 8;
}
