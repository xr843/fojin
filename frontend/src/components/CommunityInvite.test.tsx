import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CommunityInvite from "./CommunityInvite";
import { dismissCommunityInvite, getCommunityInvite, getCommunityInviteQr } from "../api/client";

vi.mock("../api/client", () => ({
  getCommunityInvite: vi.fn(),
  getCommunityInviteQr: vi.fn(),
  dismissCommunityInvite: vi.fn(async () => undefined),
}));

function renderCard(userId: number | null = 650, qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return render(
    <QueryClientProvider client={qc}>
      <CommunityInvite userId={userId} />
    </QueryClientProvider>,
  );
}

const ASYNC = { timeout: 3000 };

describe("CommunityInvite", () => {
  beforeEach(() => {
    vi.mocked(getCommunityInvite).mockReset();
    vi.mocked(getCommunityInviteQr).mockReset();
    vi.mocked(dismissCommunityInvite).mockClear();
  });

  it("游客（未登录）不发任何请求、不渲染", () => {
    const { container } = renderCard(null);
    expect(getCommunityInvite).not.toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it("名单外的用户：后端说不邀请，就什么都不渲染，也不取二维码", async () => {
    vi.mocked(getCommunityInvite).mockResolvedValue({ invited: false });
    const { container } = renderCard();
    await waitFor(() => expect(getCommunityInvite).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
    expect(getCommunityInviteQr).not.toHaveBeenCalled();
  });

  it("名单里的用户：先只显示邀请，点「加开发者微信」才去取二维码", async () => {
    vi.mocked(getCommunityInvite).mockResolvedValue({ invited: true });
    vi.mocked(getCommunityInviteQr).mockResolvedValue(new Blob(["qr"], { type: "image/png" }));
    const user = userEvent.setup();
    renderCard();
    expect(await screen.findByText(/fojin研读交流群/, {}, ASYNC)).toBeInTheDocument();
    expect(getCommunityInviteQr).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /加开发者微信/ }));
    const img = await screen.findByRole("img", { name: /开发者微信二维码/ }, ASYNC);
    expect(img.getAttribute("src")).toMatch(/^data:image\/png/);
    expect(screen.getByText(/添加时请备注：佛津/)).toBeInTheDocument();
    expect(screen.getByText(/已经是开发者的微信好友/)).toBeInTheDocument();
  });

  it("「不了，谢谢」：通知后端并立刻隐藏", async () => {
    vi.mocked(getCommunityInvite).mockResolvedValue({ invited: true });
    const user = userEvent.setup();
    const { container } = renderCard();
    await screen.findByText(/fojin研读交流群/, {}, ASYNC);
    await user.click(screen.getByRole("button", { name: "不了，谢谢" }));
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(dismissCommunityInvite).toHaveBeenCalledTimes(1);
  });

  it("同一设备换账号：名单外的新用户不能沿用上一位的「受邀」缓存", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(getCommunityInvite).mockResolvedValueOnce({ invited: true });
    const first = renderCard(650, qc);
    await screen.findByText(/fojin研读交流群/, {}, ASYNC);
    first.unmount();
    vi.mocked(getCommunityInvite).mockResolvedValueOnce({ invited: false });
    const second = renderCard(999, qc);
    await waitFor(() => expect(getCommunityInvite).toHaveBeenCalledTimes(2));
    expect(second.container).toBeEmptyDOMElement();
  });
});
