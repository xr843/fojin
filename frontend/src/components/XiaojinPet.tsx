import { useState, useRef, useEffect, useCallback, lazy, Suspense } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../stores/authStore";
import { sendChatMessageStream } from "../api/client";
import { BG_NATURAL, PEAK_FRACTION, BG_OBJECT_POS, coverPoint } from "./xiaojinPeak";
import "../styles/xiaojin-pet.css";

/** 见 XiaojinMarkdown.tsx 顶部注释：懒加载是为了不把 152K 的 markdown chunk
 *  压进首页首屏。提问时预取，等首字的几秒里就下完了。 */
const XiaojinMarkdown = lazy(() => import("./XiaojinMarkdown"));
const prefetchMarkdown = () => { void import("./XiaojinMarkdown"); };

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

/**
 * 渲染前剥掉 [追问] 行 —— 后端在答案尾部附带的追问建议。/chat 与 ReaderAIPanel
 * 各有一份 parseFollowUps 把它们解析成按钮；气泡里按用户要求不展示追问，直接
 * 丢弃。逐行判断，流式中途「[追问] …」前缀一旦成形该行立即隐藏，不会先整段
 * 露出来再消失。
 */
function stripFollowUps(content: string): string {
  return content
    .split("\n")
    .filter((line) => !/^\[追问]/.test(line.trim()))
    .join("\n")
    .replace(/\n+$/, "");
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
 * 意见反馈入口已按用户要求整个移除（先是右下角浮球 FeedbackButton，后是气泡
 * 底部的文字入口）——气泡里只留对话本身，向 ryOS Rover 的极简形态看齐。
 *
 * 对话就在气泡里进行（ryOS Rover 形态）：回车直接调 /chat/stream，答案在气泡内
 * 流式渲染，不跳页。走的是与 /chat 完全同一条后端管线（检索 + 引文护栏 +
 * citation correction），所以答案与引文标记和 /chat 同源；气泡里只render纯文本，
 * 完整的引文核对 UI 在 /chat —— 登录用户会看到「查看完整引文」入口跳去同一会话。
 * 游客也能问（后端 get_optional_user + 匿名配额），配额用尽由 onError 文案兜底。
 *
 * 默认落点：背景山水图的山尖（cover 裁切实时换算，见 xiaojinPeak.ts；窄屏裁掉
 * 山尖时退回右下角 CSS 锚点）。用户拖过之后以拖为准并持久化。
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
  const user = useAuthStore((s) => s.user);
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const figureRef = useRef<HTMLDivElement>(null);

  // ---- 气泡内迷你对话 ----
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  // 多轮对话靠它串起同一个会话；也是「查看完整引文」跳 /chat?s= 的凭据。
  const [sessionId, setSessionId] = useState<number | undefined>(undefined);
  const sessionRef = useRef<number | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const msgsRef = useRef<HTMLDivElement>(null);
  // 本轮是否收到过任何 token —— onDone 用它判「空完成」，不在 updater 里做副作用。
  const gotTokenRef = useRef(false);
  // 本轮是否已走过 onError。客户端契约（api/client.ts）：每条错误路径 onError
  // 之后必补一次 onDone —— 不做这个标记，onDone 的空完成兜底会把配额/登录过期
  // 等真实错误文案覆盖成通用「回答中断了」（2026-08-06 生产实锤）。
  const erroredRef = useRef(false);

  // 离开首页时掐掉在途的流 —— 没人看的答案不必继续烧 token。
  useEffect(() => () => abortRef.current?.abort(), []);

  // 新 token 到达时贴底 —— 迷你窗口，永远跟随最新内容。
  useEffect(() => {
    const el = msgsRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // null = 没拖过，走 CSS 默认的右下角锚点；有值 = 用户拖过，left/top 直定。
  // 惰性初始化直接恢复上次位置（夹取用兜底尺寸 80×100 —— 此刻还没有 rect，
  // 而小津本体最大也就 76px 宽；resize 监听会用真实尺寸再夹一次）。
  const [pos, setPos] = useState<Pos | null>(() => {
    const saved = readPos();
    return saved ? clampPos(saved, 80, 100) : null;
  });
  // 山尖锚点（无拖动记录时的默认落点）。null = 山尖被裁出视口/测不到，退回 CSS 右下角。
  const [anchor, setAnchor] = useState<Pos | null>(null);
  // 首帧定位完成前隐藏，避免「右下角闪现一帧再跳上山顶」。拖过的（pos 有值）直接可见。
  const [placed, setPlaced] = useState(() => readPos() !== null);

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

  /** 山尖的视口坐标 → 小津左上角（悬浮在尖上方：水平居中）。
   *  返回三态：Pos = 算出来了；null = 山尖被 cover 裁出视口（窄屏）→ 回退右下角；
   *  undefined = hero 还没排版好（rect≈0，dev 下样式异步加载时必现）→ 下一帧重试。
   *  三态是 2026-08-06 的实锤修复：之前把「没排好版」也当 null 一锤定音，
   *  小津就永远落在右下角兜底位了。 */
  const computePeakAnchor = useCallback((): Pos | null | undefined => {
    const hero = document.querySelector(".home-hero-bg");
    if (!hero) return null;
    const r = hero.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return undefined;
    const pt = coverPoint(r.width, r.height, BG_NATURAL, PEAK_FRACTION, BG_OBJECT_POS);
    const { w, h } = figureSize();
    const px = r.left + pt.x;
    const py = r.top + pt.y;
    if (px - w / 2 < EDGE || px + w / 2 > window.innerWidth - EDGE || py - h < EDGE) return null;
    // +6：让小津悬浮在山尖上方 ~30px —— 打坐悬空的意境，用户对比过贴地版
    // （+28，SVG 底部留白+雾冠+叠坐的实测和）后拍板选了悬空。要改回贴地就
    // 把叠入量调回 +28。
    return { x: px - w / 2, y: py - h + 6 };
  }, []);

  // 首帧定位：rAF 回调里测 DOM 再 setState（effect 体内同步 setState 会被
  // react-hooks/set-state-in-effect 判硬错，rAF 回调不在此列）。hero 未排版
  // （undefined）就逐帧重试，封顶 ~1s —— 已排版但山尖被裁（null）立即落定，
  // 不让窄屏用户白等一秒的隐身。
  useEffect(() => {
    let raf = 0;
    let tries = 0;
    const attempt = () => {
      const a = computePeakAnchor();
      if (a !== undefined || tries++ > 60) {
        setAnchor(a ?? null);
        setPlaced(true);
        return;
      }
      raf = requestAnimationFrame(attempt);
    };
    raf = requestAnimationFrame(attempt);
    return () => cancelAnimationFrame(raf);
  }, [computePeakAnchor]);

  // 窗口尺寸变化：拖过的夹回视口；没拖过的重算山尖锚点（cover 裁切随尺寸变）。
  // pos 进依赖：监听器随之重挂，闭包里永远是当前值，不必维护一个渲染期 ref。
  useEffect(() => {
    const onResize = () => {
      if (pos) {
        const { w, h } = figureSize();
        setPos(clampPos(pos, w, h));
      } else {
        setAnchor(computePeakAnchor() ?? null);
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [pos, computePeakAnchor]);

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

  const ask = useCallback((text: string) => {
    const term = text.trim();
    if (!term || abortRef.current) return; // 流式进行中不重入
    setQuery("");
    setChatError(null);
    gotTokenRef.current = false;
    erroredRef.current = false;
    prefetchMarkdown(); // 与 LLM 首字并行下载，用户感知不到
    setMessages((m) => [...m, { role: "user", content: term }, { role: "assistant", content: "" }]);
    setStreaming(true);

    const ac = new AbortController();
    abortRef.current = ac;
    const appendToLast = (chunk: string) => {
      gotTokenRef.current = true;
      setMessages((m) => {
        const next = m.slice();
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + chunk };
        return next;
      });
    };
    const finish = () => {
      abortRef.current = null;
      setStreaming(false);
    };

    sendChatMessageStream(term, sessionRef.current, null, {
      onToken: appendToLast,
      onSources: () => {},
      onSessionId: (sid) => {
        sessionRef.current = sid;
        setSessionId(sid);
      },
      // 护栏改写过引文锚点时，用改写后的全文替换 —— 与 /chat 落库的版本保持一致。
      onCitationCorrection: (corrected) => {
        gotTokenRef.current = true;
        setMessages((m) => {
          const next = m.slice();
          next[next.length - 1] = { role: "assistant", content: corrected };
          return next;
        });
      },
      onError: (msg, code) => {
        erroredRef.current = true; // 含 cancelled：onDone 不得再伪造空完成错误
        if (code === "cancelled") return; // 自己 abort 的，不是故障
        // 失败的空气泡不留着，错误行来说话
        setMessages((m) => (m[m.length - 1]?.content === "" ? m.slice(0, -1) : m));
        setChatError(msg);
        finish();
      },
      onDone: () => {
        // 流正常结束但一个 token 都没来：按失败兜底，别留无字空泡。
        // erroredRef 守卫：onError 之后客户端必补一次 onDone，真实错误文案
        // （配额/登录过期/上游故障）不能被这里覆盖成通用兜底。
        if (!gotTokenRef.current && !erroredRef.current) {
          setMessages((m) => (m[m.length - 1]?.content === "" ? m.slice(0, -1) : m));
          setChatError(t("xiaojin.error"));
        }
        // cancelled 后残留的空泡也要撤（onError 分支 return 得早，没走撤泡）
        if (!gotTokenRef.current && erroredRef.current) {
          setMessages((m) => (m[m.length - 1]?.content === "" ? m.slice(0, -1) : m));
        }
        finish();
      },
    }, { signal: ac.signal }).catch(() => {
      // sendChatMessageStream 内部已把错误送进 onError；这里只兜 Promise 链
      finish();
    });
  }, [t]);

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
      style={{
        ...((pos ?? anchor)
          ? { left: (pos ?? anchor)!.x, top: (pos ?? anchor)!.y, right: "auto", bottom: "auto" }
          : {}),
        ...(placed ? {} : { visibility: "hidden" as const }),
      }}
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
          {messages.length === 0 && <p className="xiaojin-greeting">{t("xiaojin.greeting")}</p>}
          {messages.length > 0 && (
            <div className="xiaojin-msgs" ref={msgsRef}>
              {messages.map((m, i) => (
                <div key={i} className={m.role === "user" ? "xiaojin-msg-user" : "xiaojin-msg-assistant"}>
                  {!m.content ? (
                    <span className="xiaojin-thinking">{t("xiaojin.thinking")}</span>
                  ) : m.role === "assistant" ? (
                    // fallback 是纯文本：chunk 万一没到（或加载失败）答案照样读得了，
                    // 只是 markdown 语法裸露——不会白屏。
                    <Suspense fallback={<span className="xiaojin-md-plain">{stripFollowUps(m.content)}</span>}>
                      <XiaojinMarkdown content={stripFollowUps(m.content)} />
                    </Suspense>
                  ) : (
                    m.content
                  )}
                </div>
              ))}
            </div>
          )}
          {chatError && <p className="xiaojin-error" role="alert">{chatError}</p>}
          {user && sessionId !== undefined && (
            <button
              type="button"
              className="xiaojin-continue"
              onClick={() => {
                setOpen(false);
                navigate(`/chat?s=${sessionId}`);
              }}
            >
              {t("xiaojin.continue")}
            </button>
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
              disabled={!query.trim() || streaming}
              aria-label={t("xiaojin.send")}
            >
              ↑
            </button>
          </div>
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
