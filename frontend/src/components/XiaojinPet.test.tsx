import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import XiaojinPet from "./XiaojinPet";
import { useAuthStore } from "../stores/authStore";
import { sendChatMessageStream } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, sendChatMessageStream: vi.fn() };
});

const HIDDEN_KEY = "fojin_xiaojin_hidden";

type Callbacks = Parameters<typeof sendChatMessageStream>[3];

/** 用真 router，把落点摊到 DOM 上断言，而不是 mock useNavigate。 */
function LocationProbe() {
  const loc = useLocation();
  return (
    <>
      <div data-testid="path">{loc.pathname}</div>
      <div data-testid="q">{new URLSearchParams(loc.search).get("q") ?? ""}</div>
      <div data-testid="send">{new URLSearchParams(loc.search).get("send") ?? ""}</div>
      <div data-testid="s">{new URLSearchParams(loc.search).get("s") ?? ""}</div>
    </>
  );
}

function renderPet() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <XiaojinPet />
      <LocationProbe />
    </MemoryRouter>,
  );
}

const openBubble = () => fireEvent.click(screen.getByLabelText("问小津"));

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  useAuthStore.setState({ token: null, user: null });
  vi.clearAllMocks();
  vi.mocked(sendChatMessageStream).mockResolvedValue(undefined);
  // 首帧定位在 rAF 回调里 setPlaced(true)；jsdom 的 rAF 不随断言推进，
  // visibility:hidden 会把可访问性树整个藏掉（getByRole 全灭）。打成同步。
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0);
    return 0;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {});
});

/** 发一问并拿到本轮的流式回调（问题进入迷你对话，不发生任何跳转）。 */
async function askAndGetCallbacks(question: string): Promise<Callbacks> {
  const input = screen.getByLabelText("问我任何问题…");
  fireEvent.change(input, { target: { value: question } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect(sendChatMessageStream).toHaveBeenCalled());
  const calls = vi.mocked(sendChatMessageStream).mock.calls;
  return calls[calls.length - 1][3];
}

describe("XiaojinPet", () => {
  it("默认收起：只有小津，没有输入框；首帧定位完成后不再隐藏", () => {
    renderPet();
    expect(screen.getByLabelText("问小津")).toBeTruthy();
    expect(screen.queryByLabelText("问我任何问题…")).toBeNull();
    // jsdom 无山水背景 → 锚点回退 CSS 右下角，但 placed 必须置真（不能永远藏着）
    const root = document.querySelector<HTMLElement>(".xiaojin-pet")!;
    expect(root.style.visibility).not.toBe("hidden");
    expect(root.style.left).toBe(""); // 无锚点 → 不写内联坐标，走 CSS 默认
  });

  it("点一下展开气泡，焦点落进输入框", () => {
    renderPet();
    openBubble();
    const input = screen.getByLabelText("问我任何问题…");
    expect(input).toBeTruthy();
    expect(document.activeElement).toBe(input);
  });

  it("回车就地作答：问题进对话流、答案流式渲染、全程不跳页", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("什么是缘起？");

    // 用户消息立即上屏，助手侧先是思索占位
    expect(screen.getByText("什么是缘起？")).toBeTruthy();
    expect(screen.getByText(/小津思索中/)).toBeTruthy();

    act(() => {
      cb.onToken("诸法因缘生，");
      cb.onToken("诸法因缘灭。");
      cb.onDone();
    });
    expect(await screen.findByText("诸法因缘生，诸法因缘灭。")).toBeTruthy();
    // 关键不变式：始终没离开首页
    expect(screen.getByTestId("path").textContent).toBe("/");
    // 问候语让位给对话流
    expect(screen.queryByText(/阿弥陀佛/)).toBeNull();
  });

  it("citation correction 到达时整段替换为改写后的全文（与 /chat 落库版本一致）", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("《心经》谁译的？");
    act(() => {
      cb.onToken("玄奘译【《心经》第1卷】");
      cb.onCitationCorrection?.("玄奘译【《般若波罗蜜多心经》第1卷】");
      cb.onDone();
    });
    expect(await screen.findByText(/般若波罗蜜多心经/)).toBeTruthy();
    expect(screen.queryByText(/^玄奘译【《心经》第1卷】$/)).toBeNull();
  });

  it("答案尾部的 [追问] 建议行不展示（正文保留）", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("什么是三法印？");
    act(() => {
      cb.onToken("三法印者，诸行无常、诸法无我、涅槃寂静。\n\n");
      cb.onToken("[追问] 三法印与一实相印有何异同？\n");
      cb.onToken("[追问] 如何理解诸法无我？");
      cb.onDone();
    });
    expect(await screen.findByText(/涅槃寂静/)).toBeTruthy();
    expect(screen.queryByText(/追问/)).toBeNull();
    expect(screen.queryByText(/一实相印/)).toBeNull();
  });

  it("答案里的 markdown 渲染成富文本，不再裸露 ** 与 -", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("你能帮我做什么？");
    act(() => {
      cb.onToken("我可以协助您：\n\n- **解读佛典义理**：结合原文与注疏。\n- **查询经文出处**：定位到卷。");
      cb.onDone();
    });
    // 懒加载的 markdown chunk 到位后才有 <strong>
    const strongs = await screen.findAllByText("解读佛典义理");
    expect(strongs[0].tagName).toBe("STRONG");
    expect(document.querySelectorAll(".xiaojin-md li").length).toBe(2);
    // 星号与减号不再作为字面量出现在正文里
    const md = document.querySelector(".xiaojin-md")!;
    expect(md.textContent).not.toContain("**");
    expect(md.textContent).not.toContain("- ");
  });

  it("流式出错：错误文案上屏、空气泡撤掉、可以再问", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("什么是无我？");
    act(() => {
      // 真实客户端契约（api/client.ts）：每条错误路径 onError 之后必补一次
      // onDone（401/非200/网络/超时/取消全如此）。用例必须照这个顺序打，
      // 否则「onDone 把真实错误改写成通用兜底」这类 bug 测不出来——
      // 2026-08-06 生产实锤：配额/登录过期的具体文案全被盖成「回答中断了」。
      cb.onError("今日提问次数已用完", "quota");
      cb.onDone();
    });
    expect(screen.getByRole("alert").textContent).toBe("今日提问次数已用完");
    expect(screen.queryByText(/小津思索中/)).toBeNull();

    // 还能继续发第二问（流已收尾、发送不再被锁）
    const cb2 = await askAndGetCallbacks("再问一次");
    act(() => {
      cb2.onToken("好。");
      cb2.onDone();
    });
    expect(await screen.findByText("好。")).toBeTruthy();
    // 新一轮开始时旧错误行已清掉
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("cancelled（用户自己停的）后跟 onDone：不显示任何错误", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("被中断的一问");
    act(() => {
      cb.onError("已停止", "cancelled");
      cb.onDone();
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("空完成（onDone 但一个 token 没来）：撤空泡并给兜底错误", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("测试空完成");
    act(() => {
      cb.onDone();
    });
    expect(screen.queryByText(/小津思索中/)).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("回答中断了");
  });

  it("多轮对话把 session id 串给下一问", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("第一问");
    act(() => {
      cb.onSessionId(42);
      cb.onToken("答一");
      cb.onDone();
    });
    await askAndGetCallbacks("第二问");
    const calls = vi.mocked(sendChatMessageStream).mock.calls;
    expect(calls[0][1]).toBeUndefined();
    expect(calls[1][1]).toBe(42);
  });

  it("流式进行中发送被锁，onDone 后解锁", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("第一问");
    // 流未结束：再回车不产生第二次调用
    const input = screen.getByLabelText("问我任何问题…");
    fireEvent.change(input, { target: { value: "抢答" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(vi.mocked(sendChatMessageStream).mock.calls.length).toBe(1);

    act(() => {
      cb.onToken("答");
      cb.onDone();
    });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(vi.mocked(sendChatMessageStream).mock.calls.length).toBe(2));
  });

  it("空输入不发送", () => {
    renderPet();
    openBubble();
    const send = screen.getByLabelText("发送") as HTMLButtonElement;
    expect(send.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("问我任何问题…"), { target: { value: "   " } });
    fireEvent.keyDown(screen.getByLabelText("问我任何问题…"), { key: "Enter" });
    expect(sendChatMessageStream).not.toHaveBeenCalled();
  });

  it("没有推荐问题（chips 已按需求移除）", () => {
    renderPet();
    openBubble();
    expect(document.querySelector(".xiaojin-chip")).toBeNull();
  });

  it("登录用户拿到 session 后出现「查看完整引文」，点击落到 /chat?s=", async () => {
    useAuthStore.setState({
      token: "t",
      user: {
        id: 1, username: "reader", email: "r@example.com", display_name: null,
        role: "user", is_active: true, created_at: "2026-01-01T00:00:00Z",
      },
    });
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("第一问");
    act(() => {
      cb.onSessionId(77);
      cb.onToken("答");
      cb.onDone();
    });
    fireEvent.click(screen.getByText(/查看完整引文/));
    expect(screen.getByTestId("path").textContent).toBe("/chat");
    expect(screen.getByTestId("s").textContent).toBe("77");
  });

  it("游客不显示「查看完整引文」（游客会话不落库，跳过去只会 404）", async () => {
    renderPet();
    openBubble();
    const cb = await askAndGetCallbacks("第一问");
    act(() => {
      cb.onSessionId(77);
      cb.onToken("答");
      cb.onDone();
    });
    expect(screen.queryByText(/查看完整引文/)).toBeNull();
  });

  it("Esc 关闭气泡", () => {
    renderPet();
    openBubble();
    expect(screen.getByLabelText("问我任何问题…")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByLabelText("问我任何问题…")).toBeNull();
  });

  it("点到外面关闭气泡", () => {
    renderPet();
    openBubble();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByLabelText("问我任何问题…")).toBeNull();
  });

  it("按 ✕ 立刻消失，但不落任何存储（刷新即回，不是单向门）", () => {
    renderPet();
    fireEvent.click(screen.getByLabelText("暂时关闭小津（刷新后回来）"));
    expect(screen.queryByLabelText("问小津")).toBeNull();
    // 落 localStorage = 永久单向门；落 sessionStorage 同标签页刷新照样还在
    // （实测），两者都不满足「刷新回来」。
    expect(localStorage.getItem(HIDDEN_KEY)).toBeNull();
    expect(sessionStorage.getItem(HIDDEN_KEY)).toBeNull();
  });

  it("关掉后重新挂载（等价于刷新）小津就回来", () => {
    const { unmount } = renderPet();
    fireEvent.click(screen.getByLabelText("暂时关闭小津（刷新后回来）"));
    expect(screen.queryByLabelText("问小津")).toBeNull();
    unmount();
    renderPet();
    expect(screen.getByLabelText("问小津")).toBeTruthy();
  });

  it("迁移：旧的永久隐藏键被清掉，小津回来", () => {
    localStorage.setItem(HIDDEN_KEY, "1");
    sessionStorage.setItem(HIDDEN_KEY, "1");
    renderPet();
    expect(screen.getByLabelText("问小津")).toBeTruthy();
    expect(localStorage.getItem(HIDDEN_KEY)).toBeNull();
    expect(sessionStorage.getItem(HIDDEN_KEY)).toBeNull();
  });

  it("气泡里没有意见反馈入口（2026-08-06 用户要求整个移除，含登录态）", () => {
    useAuthStore.setState({
      token: "t",
      user: {
        id: 1, username: "reader", email: "r@example.com", display_name: null,
        role: "user", is_active: true, created_at: "2026-01-01T00:00:00Z",
      },
    });
    renderPet();
    openBubble();
    expect(screen.queryByText("意见反馈")).toBeNull();
    expect(document.querySelector(".xiaojin-feedback")).toBeNull();
  });


});

describe("XiaojinPet 拖动", () => {
  const POS_KEY = "fojin_xiaojin_pos";

  function body() {
    return screen.getByLabelText("问小津");
  }

  /** jsdom 里 rect 全零，拖动位移即最终坐标（起点 0,0 + delta）。 */
  function drag(from: [number, number], to: [number, number]) {
    const el = body();
    fireEvent.pointerDown(el, { pointerId: 1, isPrimary: true, clientX: from[0], clientY: from[1] });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: to[0], clientY: to[1] });
    fireEvent.pointerUp(el, { pointerId: 1, clientX: to[0], clientY: to[1] });
    // 浏览器在 pointerup 后必补发一次 click —— 模拟它来验证吞掉逻辑
    fireEvent.click(el);
  }

  it("拖过阈值：位置更新为 left/top、写入 localStorage，且拖完不弹气泡", () => {
    renderPet();
    drag([10, 10], [110, 60]);

    const root = document.querySelector<HTMLElement>(".xiaojin-pet")!;
    expect(root.style.left).toBe("100px");
    expect(root.style.top).toBe("50px");
    expect(JSON.parse(localStorage.getItem(POS_KEY)!)).toEqual({ x: 100, y: 50 });
    // 拖动的收尾 click 被吞掉，气泡不弹
    expect(screen.queryByLabelText("问我任何问题…")).toBeNull();
    // 再点一下（真点击）气泡照常打开 —— 吞 click 只吞一次
    fireEvent.click(body());
    expect(screen.getByLabelText("问我任何问题…")).toBeTruthy();
  });

  it("位移小于阈值算点击：气泡打开、位置不动", () => {
    renderPet();
    const el = body();
    fireEvent.pointerDown(el, { pointerId: 1, isPrimary: true, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 12, clientY: 12 });
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 12, clientY: 12 });
    fireEvent.click(el);

    expect(screen.getByLabelText("问我任何问题…")).toBeTruthy();
    expect(document.querySelector<HTMLElement>(".xiaojin-pet")!.style.left).toBe("");
    expect(localStorage.getItem(POS_KEY)).toBeNull();
  });

  it("下次进来恢复上次拖到的位置", () => {
    localStorage.setItem(POS_KEY, JSON.stringify({ x: 50, y: 80 }));
    renderPet();
    const root = document.querySelector<HTMLElement>(".xiaojin-pet")!;
    expect(root.style.left).toBe("50px");
    expect(root.style.top).toBe("80px");
  });

  it("存的位置在屏幕外时夹回视口", () => {
    localStorage.setItem(POS_KEY, JSON.stringify({ x: 99999, y: 99999 }));
    renderPet();
    const root = document.querySelector<HTMLElement>(".xiaojin-pet")!;
    const left = parseInt(root.style.left, 10);
    const top = parseInt(root.style.top, 10);
    expect(left).toBeGreaterThanOrEqual(0);
    expect(left).toBeLessThanOrEqual(window.innerWidth);
    expect(top).toBeGreaterThanOrEqual(0);
    expect(top).toBeLessThanOrEqual(window.innerHeight);
  });

  // 气泡朝向（data-v/data-h）依赖真实布局的 getBoundingClientRect，jsdom 里
  // rect 全零测不出翻转 —— 朝向逻辑在真浏览器里人工验证（拖到顶部气泡开脚下）。
});
