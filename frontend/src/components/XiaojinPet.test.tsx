import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import XiaojinPet from "./XiaojinPet";
import { useAuthStore } from "../stores/authStore";

const HIDDEN_KEY = "fojin_xiaojin_hidden";

/** 用真 router，把落点摊到 DOM 上断言，而不是 mock useNavigate。 */
function LocationProbe() {
  const loc = useLocation();
  return (
    <>
      <div data-testid="path">{loc.pathname}</div>
      <div data-testid="q">{new URLSearchParams(loc.search).get("q") ?? ""}</div>
      <div data-testid="send">{new URLSearchParams(loc.search).get("send") ?? ""}</div>
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
  useAuthStore.setState({ token: null, user: null });
});

describe("XiaojinPet", () => {
  it("默认收起：只有小津，没有输入框", () => {
    renderPet();
    expect(screen.getByLabelText("问小津")).toBeTruthy();
    expect(screen.queryByLabelText("问我任何问题…")).toBeNull();
  });

  it("点一下展开气泡，焦点落进输入框", () => {
    renderPet();
    openBubble();
    const input = screen.getByLabelText("问我任何问题…");
    expect(input).toBeTruthy();
    expect(document.activeElement).toBe(input);
  });

  it("回车把问题带去 /chat 并带上 send=1（用户已按过回车，落地要直接发送）", () => {
    renderPet();
    openBubble();
    const question = "什么是缘起？";
    const input = screen.getByLabelText("问我任何问题…");
    fireEvent.change(input, { target: { value: question } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByTestId("path").textContent).toBe("/chat");
    expect(screen.getByTestId("q").textContent).toBe(question);
    // 没有 send=1 就退化成「只填不发」，吞掉用户在气泡里那次回车
    expect(screen.getByTestId("send").textContent).toBe("1");
  });

  // 不编码的话 & 会把 query 截成两段、# 会变成 hash，深链静默丢内容。
  // 上一版用例只测了纯汉字问题，去掉 encodeURIComponent 照样全绿 —— 所以专挑
  // 会撕裂 query string 的字符。
  it("问题里带 & 与 # 也能完整送达", () => {
    renderPet();
    openBubble();
    const question = "空 & 有 #不二";
    fireEvent.change(screen.getByLabelText("问我任何问题…"), { target: { value: question } });
    fireEvent.keyDown(screen.getByLabelText("问我任何问题…"), { key: "Enter" });

    expect(screen.getByTestId("path").textContent).toBe("/chat");
    expect(screen.getByTestId("q").textContent).toBe(question);
  });

  it("点发送按钮与回车等效", () => {
    renderPet();
    openBubble();
    const question = "唯识三性是什么";
    fireEvent.change(screen.getByLabelText("问我任何问题…"), { target: { value: question } });
    fireEvent.click(screen.getByLabelText("发送"));

    expect(screen.getByTestId("path").textContent).toBe("/chat");
    expect(screen.getByTestId("q").textContent).toBe(question);
  });

  it("空输入不跳转，发送按钮是禁用的", () => {
    renderPet();
    openBubble();
    const send = screen.getByLabelText("发送") as HTMLButtonElement;
    expect(send.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("问我任何问题…"), { target: { value: "   " } });
    fireEvent.keyDown(screen.getByLabelText("问我任何问题…"), { key: "Enter" });
    expect(screen.getByTestId("path").textContent).toBe("/");
  });

  it("点推荐问题直接带该问题跳转", () => {
    renderPet();
    openBubble();
    const chip = screen.getByText("什么是三法印？");
    fireEvent.click(chip);

    expect(screen.getByTestId("path").textContent).toBe("/chat");
    expect(screen.getByTestId("q").textContent).toBe("什么是三法印？");
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

  it("赶走它之后本次立刻消失，并记进 localStorage", () => {
    renderPet();
    fireEvent.click(screen.getByLabelText("不再显示小津"));
    expect(screen.queryByLabelText("问小津")).toBeNull();
    expect(localStorage.getItem(HIDDEN_KEY)).toBe("1");
  });

  it("登录后气泡里有意见反馈入口，点开弹窗", () => {
    useAuthStore.setState({
      token: "t",
      user: {
        id: 1, username: "reader", email: "r@example.com", display_name: null,
        role: "user", is_active: true, created_at: "2026-01-01T00:00:00Z",
      },
    });
    renderPet();
    openBubble();
    fireEvent.click(screen.getByText("意见反馈"));
    // 弹窗开出（antd Modal 渲染在 portal 里）
    expect(screen.getByText("反馈内容")).toBeTruthy();
    // 气泡随手收起
    expect(screen.queryByLabelText("问我任何问题…")).toBeNull();
  });

  it("匿名用户看不到意见反馈入口（提交反馈需要登录态）", () => {
    renderPet();
    openBubble();
    expect(screen.queryByText("意见反馈")).toBeNull();
  });

  it("已被赶走过就整个不渲染", () => {
    localStorage.setItem(HIDDEN_KEY, "1");
    renderPet();
    expect(screen.queryByLabelText("问小津")).toBeNull();
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
