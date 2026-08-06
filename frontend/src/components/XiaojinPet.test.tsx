import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import XiaojinPet from "./XiaojinPet";

const HIDDEN_KEY = "fojin_xiaojin_hidden";

/** 用真 router，把落点摊到 DOM 上断言，而不是 mock useNavigate。 */
function LocationProbe() {
  const loc = useLocation();
  return (
    <>
      <div data-testid="path">{loc.pathname}</div>
      <div data-testid="q">{new URLSearchParams(loc.search).get("q") ?? ""}</div>
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

  it("回车把问题带去 /chat，且 q 能原样解回来", () => {
    renderPet();
    openBubble();
    const question = "什么是缘起？";
    const input = screen.getByLabelText("问我任何问题…");
    fireEvent.change(input, { target: { value: question } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByTestId("path").textContent).toBe("/chat");
    expect(screen.getByTestId("q").textContent).toBe(question);
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

  it("已被赶走过就整个不渲染", () => {
    localStorage.setItem(HIDDEN_KEY, "1");
    renderPet();
    expect(screen.queryByLabelText("问小津")).toBeNull();
  });
});
