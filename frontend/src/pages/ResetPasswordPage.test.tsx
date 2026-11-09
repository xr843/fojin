import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import { resetPasswordWithToken } from "../api/client";
import ResetPasswordPage from "./ResetPasswordPage";

vi.mock("../api/client", () => ({ resetPasswordWithToken: vi.fn() }));

const TOKEN = "Abc_def-0123456789abcdefghijklmnopqrstuvwxyzAB";

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false, media: query, onchange: null,
        addListener: () => {}, removeListener: () => {},
        addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
  }
});

function renderAt(hash: string) {
  window.history.replaceState(null, "", `/reset-password${hash}`);
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={["/reset-password"]}>
        <ResetPasswordPage />
      </MemoryRouter>
    </HelmetProvider>,
  );
}

function fill(pw: string, confirm: string) {
  fireEvent.change(screen.getByPlaceholderText("新密码"), { target: { value: pw } });
  fireEvent.change(screen.getByPlaceholderText("再输入一次新密码"), { target: { value: confirm } });
  fireEvent.click(screen.getByRole("button", { name: "设置新密码" }));
}

describe("ResetPasswordPage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("zh");
    vi.mocked(resetPasswordWithToken).mockReset().mockResolvedValue(undefined);
  });
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("从 # 后读令牌提交，成功后把令牌从地址栏抹掉", async () => {
    renderAt(`#token=${TOKEN}`);
    fill("newpass123", "newpass123");
    await waitFor(() => expect(resetPasswordWithToken).toHaveBeenCalledWith(TOKEN, "newpass123"));
    expect(await screen.findByText(/新密码已设置/)).toBeInTheDocument();
    expect(window.location.hash).toBe("");
  });

  it("两次密码不一致不提交", async () => {
    renderAt(`#token=${TOKEN}`);
    fill("newpass123", "newpass124");
    expect(await screen.findByText("两次输入的密码不一致")).toBeInTheDocument();
    expect(resetPasswordWithToken).not.toHaveBeenCalled();
  });

  it("链接没带令牌：提示复制整条链接，不显示表单", () => {
    renderAt("");
    expect(screen.getByText(/链接不完整/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "设置新密码" })).toBeNull();
  });

  it("令牌失效时显示后端给的原因", async () => {
    vi.mocked(resetPasswordWithToken).mockRejectedValue(
      Object.assign(new Error("x"), { isAxiosError: true, response: { data: { detail: "链接无效或已过期，请重新申请" } } }),
    );
    renderAt(`#token=${TOKEN}`);
    fill("newpass123", "newpass123");
    expect(await screen.findByText("链接无效或已过期，请重新申请")).toBeInTheDocument();
  });
});
