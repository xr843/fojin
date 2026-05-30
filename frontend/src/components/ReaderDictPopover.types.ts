import type { DictGroupedSearchResponse } from "../api/client";

/** 划词查辞典浮层状态 */
export interface DictPopoverState {
  visible: boolean;
  text: string;
  x: number;
  y: number;
  loading: boolean;
  result: DictGroupedSearchResponse | null;
}

export const DICT_POPOVER_INIT: DictPopoverState = {
  visible: false,
  text: "",
  x: 0,
  y: 0,
  loading: false,
  result: null,
};

/** 超过此长度视为「整句选择」：只提供问小津，不查辞典 */
export const MAX_WORD_LEN = 20;
