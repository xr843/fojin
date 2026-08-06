import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../stores/authStore";
import FeedbackModal from "./FeedbackModal";
import "../styles/xiaojin-pet.css";

/** 用户主动赶走小津后不再出现。私密模式下 localStorage 会抛，一律当没隐藏。 */
const HIDDEN_KEY = "fojin_xiaojin_hidden";
/** 用户把小津拖到哪，下次进来还在哪。 */
const POS_KEY = "fojin_xiaojin_pos";
/** 指针位移超过这个像素数才算拖动，否则算点击。 */
const DRAG_THRESHOLD = 5;
/** 夹取时给视口四边留的呼吸边距。 */
const EDGE = 8;

type Pos = { x: number; y: number };

function readHidden(): boolean {
  try {
    return localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function readPos(): Pos | null {
  try {
    const raw = localStorage.getItem(POS_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw) as Pos;
    return typeof p?.x === "number" && typeof p?.y === "number" ? p : null;
  } catch {
    return null;
  }
}

function writePos(p: Pos) {
  try {
    localStorage.setItem(POS_KEY, JSON.stringify(p));
  } catch {
    // 私密模式：本次会话内有效即可
  }
}

/** 把位置夹回视口内 —— 换了窗口尺寸/分辨率后，存下来的坐标可能已在屏幕外。 */
function clampPos(p: Pos, w: number, h: number): Pos {
  return {
    x: Math.min(Math.max(p.x, EDGE), Math.max(EDGE, window.innerWidth - w - EDGE)),
    y: Math.min(Math.max(p.y, EDGE), Math.max(EDGE, window.innerHeight - h - EDGE)),
  };
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
 *
 * 可拖动：按住小津本体拖到页面任意位置（pointer events，鼠标/触屏同一套），
 * 位移超过 5px 算拖动并吞掉随后的 click，否则算点击开气泡。位置持久化到
 * localStorage，恢复与窗口 resize 时都夹回视口。气泡朝向按小津当前位置自动
 * 选（上下取空间大的一侧、左右取够放 272px 的一侧），拖到页面顶上气泡开在
 * 下方，不会伸出屏幕外。
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
  const figureRef = useRef<HTMLDivElement>(null);

  // null = 没拖过，走 CSS 默认的右下角锚点；有值 = 用户拖过，left/top 直定。
  // 惰性初始化直接恢复上次位置（夹取用兜底尺寸 80×100 —— 此刻还没有 rect，
  // 而小津本体最大也就 76px 宽；resize 监听会用真实尺寸再夹一次）。
  const [pos, setPos] = useState<Pos | null>(() => {
    const saved = readPos();
    return saved ? clampPos(saved, 80, 100) : null;
  });
  // 气泡朝向：above/below 是相对小津的垂直方向，right/left 是气泡贴齐小津的哪条边。
  const [placement, setPlacement] = useState<{ v: "above" | "below"; h: "right" | "left" }>({
    v: "above",
    h: "right",
  });
  // 一次拖动的起点快照；active 在越过阈值后置真。
  const dragRef = useRef<{ px: number; py: number; x: number; y: number; active: boolean } | null>(null);
  // 拖动结束后浏览器仍会补发一次 click —— 用这个标记吞掉它，别让拖完弹气泡。
  const draggedRef = useRef(false);

  const figureSize = () => {
    const r = figureRef.current?.getBoundingClientRect();
    return { w: r?.width || 80, h: r?.height || 100 };
  };

  // 窗口尺寸变化时把小津夹回视口，别让它留在屏幕外找不回来。
  useEffect(() => {
    const onResize = () => {
      setPos((p) => {
        if (!p) return p;
        const { w, h } = figureSize();
        return clampPos(p, w, h);
      });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /** 按小津当前位置选气泡朝向：垂直取空间大的一侧，水平取够放气泡的一侧。 */
  const computePlacement = useCallback(() => {
    const r = figureRef.current?.getBoundingClientRect();
    if (!r) return;
    setPlacement({
      v: r.top >= window.innerHeight - r.bottom ? "above" : "below",
      h: r.right >= window.innerWidth - r.left ? "right" : "left",
    });
  }, []);

  const onFigurePointerDown = (e: React.PointerEvent) => {
    if (!e.isPrimary) return;
    const r = rootRef.current?.getBoundingClientRect();
    if (!r) return;
    dragRef.current = { px: e.clientX, py: e.clientY, x: r.left, y: r.top, active: false };
    // jsdom 没有 setPointerCapture —— 可选调用
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  };

  const onFigurePointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.px;
    const dy = e.clientY - d.py;
    if (!d.active) {
      if (Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
      d.active = true;
      draggedRef.current = true;
    }
    const { w, h } = figureSize();
    setPos(clampPos({ x: d.x + dx, y: d.y + dy }, w, h));
  };

  const onFigurePointerUp = () => {
    const d = dragRef.current;
    dragRef.current = null;
    if (!d?.active) return;
    // 落定：存位置，并按新位置重算气泡该往哪边开。
    setPos((p) => {
      if (p) writePos(p);
      return p;
    });
    computePlacement();
  };

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
    <div
      className="xiaojin-pet"
      ref={rootRef}
      data-open={open ? "" : undefined}
      data-v={placement.v}
      data-h={placement.h}
      style={pos ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" } : undefined}
    >
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

      <div className="xiaojin-figure" ref={figureRef}>
        <button
          type="button"
          className="xiaojin-body"
          onPointerDown={onFigurePointerDown}
          onPointerMove={onFigurePointerMove}
          onPointerUp={onFigurePointerUp}
          onClick={() => {
            // 刚拖完：这次 click 是拖动的尾巴，不是点击意图。
            if (draggedRef.current) {
              draggedRef.current = false;
              return;
            }
            setOpen((o) => {
              const next = !o;
              if (next) computePlacement();
              return next;
            });
          }}
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
