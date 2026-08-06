import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../stores/authStore";
import FeedbackModal from "./FeedbackModal";
import "../styles/xiaojin-pet.css";

/** 用户主动赶走小津后不再出现。私密模式下 localStorage 会抛，一律当没隐藏。 */
const HIDDEN_KEY = "fojin_xiaojin_hidden";

function readHidden(): boolean {
  try {
    return localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * 首页右下角的小津 —— 一个通往 /chat 的迷你问答入口。
 *
 * 「小津」是 /chat 里既有的问答人格（chat.title、dict.ask_ai 都在用这个名字），
 * 这里只是给它一个身相：打坐僧相。全站同一个名字，别再造第二个称呼。
 *
 * 原先占右下角的意见反馈浮球（FeedbackButton）已删除，反馈入口收进气泡底部
 * （登录用户可见，与原浮球同门槛）——一个角落一个角色，别再放第二个浮动物。
 *
 * 问题不在这里作答：回车后跳 `/chat?q=`，由 ChatPage 既有的深链逻辑接管并自动发问。
 * 这样它始终只有一条真相来源（/chat 的检索与引文护栏），首页不复制一套流式渲染。
 */
export default function XiaojinPet() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [hidden, setHidden] = useState(readHidden);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const user = useAuthStore((s) => s.user);
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const rawPrompts = t("xiaojin.prompts", { returnObjects: true });
  const prompts: string[] = Array.isArray(rawPrompts) ? rawPrompts : [];

  const ask = useCallback(
    (text: string) => {
      const term = text.trim();
      if (!term) return;
      setOpen(false);
      setQuery("");
      // send=1：ChatPage 会直接发送并从 URL 抹掉参数。裸 ?q= 是只填不发的
      // （收藏/分享场景），但这里用户已经在气泡里按过回车，意图是问、不是编辑。
      navigate(`/chat?q=${encodeURIComponent(term)}&send=1`);
    },
    [navigate],
  );

  // 开合气泡时把焦点送进输入框，键盘用户不必再 Tab 一轮。
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Esc 关闭；点到气泡与小津之外也关闭。
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  const dismiss = () => {
    try {
      localStorage.setItem(HIDDEN_KEY, "1");
    } catch {
      // 私密模式：这次会话内隐藏即可，不必persist
    }
    setHidden(true);
  };

  if (hidden) return null;

  return (
    <div className="xiaojin-pet" ref={rootRef} data-open={open ? "" : undefined}>
      {open && (
        <div className="xiaojin-bubble" role="dialog" aria-label={t("xiaojin.bubble_label")}>
          <button
            type="button"
            className="xiaojin-bubble-close"
            onClick={() => setOpen(false)}
            aria-label={t("xiaojin.close")}
          >
            ✕
          </button>
          <p className="xiaojin-greeting">{t("xiaojin.greeting")}</p>
          {prompts.length > 0 && (
            <div className="xiaojin-chips">
              {prompts.map((p) => (
                <button type="button" key={p} className="xiaojin-chip" onClick={() => ask(p)}>
                  {p}
                </button>
              ))}
            </div>
          )}
          <div className="xiaojin-input-row">
            <input
              ref={inputRef}
              className="xiaojin-input"
              value={query}
              maxLength={200}
              placeholder={t("xiaojin.placeholder")}
              aria-label={t("xiaojin.placeholder")}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") ask(query);
              }}
            />
            <button
              type="button"
              className="xiaojin-send"
              onClick={() => ask(query)}
              disabled={!query.trim()}
              aria-label={t("xiaojin.send")}
            >
              ↑
            </button>
          </div>
          {/* 意见反馈入口 —— 原右下角浮球的替身，同样只对登录用户开放
              （submitFeedback 需要登录态）。 */}
          {user && (
            <button
              type="button"
              className="xiaojin-feedback"
              onClick={() => {
                setOpen(false);
                setFeedbackOpen(true);
              }}
            >
              {t("feedback.title")}
            </button>
          )}
        </div>
      )}

      <div className="xiaojin-figure">
        <button
          type="button"
          className="xiaojin-body"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-label={t("xiaojin.open")}
        >
          <XiaojinFigure />
        </button>
        <button
          type="button"
          className="xiaojin-dismiss"
          onClick={dismiss}
          aria-label={t("xiaojin.dismiss")}
        >
          ✕
        </button>
      </div>

      {/* Modal 挂在气泡外：入口点击时气泡随即关闭，弹窗不能跟着一起卸载。 */}
      <FeedbackModal open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
    </div>
  );
}

/**
 * 小津的身相：打坐僧相。汉传衣制——正金黄海青（#d6a13c）+ 赭红祖衣斜披左肩，结跏趺坐、手结定印。
 * 一切颜色走 CSS 变量，深色模式由 xiaojin-pet.css 整体提亮，避免暗底上发闷。
 * 平时垂目，鼠标靠近或气泡展开时睁眼——闭着的眼睛「眨」不出效果，睁眼才读得出反应。
 */
function XiaojinFigure() {
  return (
    <svg viewBox="0 0 100 112" width="76" aria-hidden="true" focusable="false">
      <ellipse className="xiaojin-shadow" cx="50" cy="104" rx="31" ry="4" />
      <g className="xiaojin-torso">
        {/* 结跏趺坐 */}
        <path
          d="M50 48 c-12.5 0-21 8.5-27 25 -4 11-6.2 20-6.2 24.5 q33 6 66.4 0 C83.2 93 81 84 77 73 71 56.5 62.5 48 50 48z"
          fill="var(--xiaojin-robe)"
        />
        {/* 双膝 */}
        <ellipse cx="26" cy="92" rx="12.5" ry="7.5" fill="var(--xiaojin-robe-d)" />
        <ellipse cx="74" cy="92" rx="12.5" ry="7.5" fill="var(--xiaojin-robe-d)" />
        {/* 祖衣斜披 */}
        <path d="M40 50 L66.5 88 l-12 4.5 L31.5 57z" fill="var(--xiaojin-kesa)" opacity="0.92" />
        {/* 交领 */}
        <path
          d="M43 49.5 l7 11.5 7-11.5"
          fill="none"
          stroke="var(--xiaojin-collar)"
          strokeWidth="3.2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* 定印 */}
        <ellipse cx="50" cy="88.5" rx="11.5" ry="5" fill="var(--xiaojin-skin)" />
        <ellipse cx="50" cy="85.2" rx="8.2" ry="3.6" fill="var(--xiaojin-skin-d)" />
      </g>
      <g>
        <ellipse cx="26" cy="35" rx="3.7" ry="6" fill="var(--xiaojin-skin)" />
        <ellipse cx="74" cy="35" rx="3.7" ry="6" fill="var(--xiaojin-skin)" />
        <circle cx="50" cy="31" r="24.5" fill="var(--xiaojin-skin)" />
        {/* 垂目 */}
        <g className="xiaojin-eyes-closed">
          <path
            d="M38.5 32 q4.6 3.4 9.2 0"
            stroke="var(--xiaojin-line)"
            strokeWidth="1.9"
            fill="none"
            strokeLinecap="round"
          />
          <path
            d="M52.3 32 q4.6 3.4 9.2 0"
            stroke="var(--xiaojin-line)"
            strokeWidth="1.9"
            fill="none"
            strokeLinecap="round"
          />
        </g>
        {/* 睁眼（hover / 展开时显形） */}
        <g className="xiaojin-eyes-open">
          <ellipse cx="43" cy="31.5" rx="3" ry="3.4" fill="var(--xiaojin-line)" />
          <ellipse cx="57" cy="31.5" rx="3" ry="3.4" fill="var(--xiaojin-line)" />
          <circle cx="44.1" cy="30.3" r="1" fill="#fff" opacity="0.85" />
          <circle cx="58.1" cy="30.3" r="1" fill="#fff" opacity="0.85" />
        </g>
        <ellipse cx="34" cy="39" rx="5" ry="3" fill="var(--xiaojin-blush)" opacity="0.4" />
        <ellipse cx="66" cy="39" rx="5" ry="3" fill="var(--xiaojin-blush)" opacity="0.4" />
        <path
          d="M46 40 q4 3.6 8 0"
          stroke="var(--xiaojin-line)"
          strokeWidth="1.7"
          fill="none"
          strokeLinecap="round"
        />
      </g>
    </svg>
  );
}
