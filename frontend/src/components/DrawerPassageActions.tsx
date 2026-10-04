import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { SimilarPassages, VernacularPanel } from "./ReaderSelectionExtras";
import { drawerTargetText, type SelectionContext } from "./ReaderSelectionExtras.types";

type Mode = "vernacular" | "similar";

/**
 * 引文抽屉的「白话 / 全藏出处」。抽屉才是 /chat 读者真正读经的地方（点开引文
 * 509 次里 479 次留在抽屉，不跳阅读页），阅读页划词覆盖不到他们。
 * 包住经文正文以接收抽屉内的划词；没有选区时作用于定位到的被引那句。
 */
export default function DrawerPassageActions({
  textId,
  juanNum,
  title,
  passage,
  quoteSpans,
  children,
}: {
  textId: number;
  juanNum: number;
  title: string;
  passage: string;
  quoteSpans: [number, number][];
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [selection, setSelection] = useState("");
  // 模式跟着目标文字走：换一段选区自动收起
  const [modeFor, setModeFor] = useState<{ text: string; mode: Mode | null }>({ text: "", mode: null });

  const target = drawerTargetText(passage, quoteSpans, selection);
  const mode = target && modeFor.text === target.text ? modeFor.mode : null;

  const readSelection = () => {
    const sel = window.getSelection()?.toString() ?? "";
    setSelection(sel.trim());
  };

  const toggle = (m: Mode) => {
    if (!target) return;
    const next = mode === m ? null : m;
    setModeFor({ text: target.text, mode: next });
    if (next && typeof umami !== "undefined") {
      umami.track(next === "similar" ? "reader_similar" : "drawer_vernacular_open", {
        id: textId,
        surface: "drawer",
        from: target.from,
      });
    }
  };

  const context: SelectionContext = {
    textId,
    juanNum,
    title,
    cbetaId: "",
    lineRef: null,
    juanText: passage,
    surface: "drawer",
  };

  return (
    <>
      <div onMouseUp={readSelection} onTouchEnd={() => setTimeout(readSelection, 100)}>
        {children}
      </div>
      <div className="drawer-passage-actions">
        {target ? (
          <>
            <div className="drawer-passage-actions-row">
              <span className="drawer-passage-actions-target">
                {t(target.from === "selection" ? "reader.drawer_actions.on_selection" : "reader.drawer_actions.on_quote")}
                「{target.text.length > 18 ? `${target.text.slice(0, 18)}…` : target.text}」
              </span>
              <button
                type="button"
                className={`reader-dict-popover-tab${mode === "vernacular" ? " is-active" : ""}`}
                onClick={() => toggle("vernacular")}
              >
                {t("reader.vernacular.button")}
              </button>
              <button
                type="button"
                className={`reader-dict-popover-tab${mode === "similar" ? " is-active" : ""}`}
                onClick={() => toggle("similar")}
              >
                {t("reader.canonrefs.button")}
              </button>
            </div>
            {mode === "vernacular" && (
              <div className="drawer-passage-actions-panel">
                <VernacularPanel text={target.text} context={context} />
              </div>
            )}
            {mode === "similar" && (
              <div className="drawer-passage-actions-panel">
                <SimilarPassages text={target.text} context={context} />
              </div>
            )}
          </>
        ) : (
          <div className="drawer-passage-actions-hint">{t("reader.drawer_actions.hint")}</div>
        )}
      </div>
    </>
  );
}
