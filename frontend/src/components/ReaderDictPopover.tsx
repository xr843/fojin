import { useState } from "react";
import { Link } from "react-router";
import { Spin } from "antd";
import { useTranslation } from "react-i18next";
import { MessageOutlined } from "@ant-design/icons";
import type { DictGroupedSearchResponse, DictEntry } from "../api/client";
import { MAX_WORD_LEN, type DictPopoverState } from "./ReaderDictPopover.types";
import { ReportErrorForm, SimilarPassages, VernacularPanel } from "./ReaderSelectionExtras";
import type { SelectionContext } from "./ReaderSelectionExtras.types";

type PopoverMode = "dict" | "vernacular" | "similar" | "report";

/** 中文释义类辞典优先（释义信息量大），多语对照类短释义靠后 */
const HIGH_QUALITY_SOURCES = [
  "dila-dfb", "foguang", "nti-reader", "bs-faxiang", "bs-changjianci",
  "zhonghua-baike", "bs-yiqiejing-yinyi", "bs-agama", "weishi",
  "abhidharma", "tiantai", "sanzang-fashu",
];

/** 把分组结果排序：中文释义类在前，其余在后 */
function orderedGroups(result: DictGroupedSearchResponse | null) {
  if (!result?.groups?.length) return [];
  const hq: DictGroupedSearchResponse["groups"] = [];
  const rest: DictGroupedSearchResponse["groups"] = [];
  for (const g of result.groups) {
    (HIGH_QUALITY_SOURCES.includes(g.source_code) ? hq : rest).push(g);
  }
  return [...hq, ...rest];
}

/**
 * 阅读器划词浮层：短词显示多部辞典释义（全文可滚动）+ 发音，长选择只显示问小津。
 * 取代了旧的「截断 30 字、只显示一部辞典」实现，并合并了原 AskXiaojinButton。
 */
export function ReaderDictPopover({
  state,
  onClose,
  onAsk,
  context,
  loggedIn = false,
}: {
  state: DictPopoverState;
  onClose: () => void;
  onAsk: (text: string) => void;
  /** 划词所在经文位置；给了才显示「全藏出处」「报错」 */
  context?: SelectionContext;
  loggedIn?: boolean;
}) {
  const { t } = useTranslation();
  // 模式跟着选中文字走：换一段选区自动回到辞典模式
  const [modeFor, setModeFor] = useState<{ text: string; mode: PopoverMode }>({ text: "", mode: "dict" });
  if (!state.visible) return null;
  const mode: PopoverMode = modeFor.text === state.text ? modeFor.mode : "dict";
  const setMode = (m: PopoverMode) => {
    setModeFor({ text: state.text, mode: m });
    if ((m === "similar" || m === "report") && typeof umami !== "undefined") {
      umami.track(m === "similar" ? "reader_similar" : "reader_report_open", { id: context?.textId ?? 0 });
    }
  };

  const isWord = state.text.length > 0 && state.text.length <= MAX_WORD_LEN;
  const groups = orderedGroups(state.result);
  // 发音：取所有词典里第一个非空 reading（首选词典常无注音，音义类词典才有）
  let reading: string | null = null;
  for (const g of groups) {
    const hit = g.entries.find((e) => e.reading);
    if (hit?.reading) {
      reading = hit.reading;
      break;
    }
  }

  // 计算浮层位置（fixed 定位，避开视口边缘）
  const popW = 300;
  let left = state.x - popW / 2;
  let top = state.y + 8;
  if (left < 8) left = 8;
  if (left + popW > window.innerWidth - 8) left = window.innerWidth - popW - 8;
  if (top + 280 > window.innerHeight - 8) {
    top = state.y - 288;
    if (top < 8) top = 8;
  }

  const handleAsk = () => {
    onAsk(state.text);
    onClose();
  };

  return (
    <div
      className="reader-dict-popover"
      style={{ left, top }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="reader-dict-popover-header">
        <span className="reader-dict-popover-keyword">
          {state.text}
          {reading && <span className="reader-dict-popover-reading">{reading}</span>}
        </span>
        <button className="reader-dict-popover-close" onClick={onClose} aria-label={t("reader.dict.close")}>
          ✕
        </button>
      </div>

      {mode === "vernacular" && context && (
        <div className="reader-dict-popover-body">
          <VernacularPanel text={state.text} context={context} />
        </div>
      )}

      {mode === "similar" && context && (
        <div className="reader-dict-popover-body">
          <SimilarPassages text={state.text} context={context} />
        </div>
      )}

      {mode === "report" && context && (
        <div className="reader-dict-popover-body">
          <ReportErrorForm text={state.text} context={context} loggedIn={loggedIn} onDone={onClose} />
        </div>
      )}

      {mode === "dict" && isWord && (
        <div className="reader-dict-popover-body">
          {state.loading ? (
            <div style={{ textAlign: "center", padding: 12 }}>
              <Spin size="small" />
            </div>
          ) : groups.length ? (
            <div className="reader-dict-popover-groups">
              {groups.map((g) => (
                <div key={g.source_code} className="reader-dict-popover-group">
                  <div className="reader-dict-popover-source">{g.source_name}</div>
                  {g.entries.slice(0, 2).map((e: DictEntry) => (
                    <div key={String(e.id)} className="reader-dict-popover-def">
                      {e.definition}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <div className="reader-dict-popover-empty">{t("reader.dict.empty")}</div>
          )}
        </div>
      )}

      <div className="reader-dict-popover-footer">
        <button className="reader-dict-popover-ask" onClick={handleAsk}>
          <MessageOutlined style={{ fontSize: 12, marginRight: 3 }} />
          {t("dict.ask_ai")}
        </button>
        {context && (
          <>
            <button
              type="button"
              className={`reader-dict-popover-tab${mode === "vernacular" ? " is-active" : ""}`}
              onClick={() => setMode(mode === "vernacular" ? "dict" : "vernacular")}
            >
              {t("reader.vernacular.button")}
            </button>
            <button
              type="button"
              className={`reader-dict-popover-tab${mode === "similar" ? " is-active" : ""}`}
              onClick={() => setMode(mode === "similar" ? "dict" : "similar")}
            >
              {t("reader.canonrefs.button")}
            </button>
            <button
              type="button"
              className={`reader-dict-popover-tab${mode === "report" ? " is-active" : ""}`}
              onClick={() => setMode(mode === "report" ? "dict" : "report")}
            >
              {t("reader.report.button")}
            </button>
          </>
        )}
        {mode === "dict" && isWord && (
          <Link to={`/dictionary?q=${encodeURIComponent(state.text)}`} onClick={onClose}>
            {t("reader.dict.view_all")}
          </Link>
        )}
      </div>
    </div>
  );
}

export default ReaderDictPopover;
