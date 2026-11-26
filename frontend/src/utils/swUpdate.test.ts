import { afterEach, describe, expect, it, vi } from "vitest";
import { handleControllerChange, handlePreloadError, isUpdateReady, onUpdateReady } from "./swUpdate";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("部署后换新版", () => {
  it("刚打开不久、没在打字：新版接管后直接刷新", () => {
    const reload = vi.fn();
    expect(handleControllerChange(90_000, 0, reload)).toBe("reloaded"); // 大陆网络重下新版约一分钟
    expect(reload).toHaveBeenCalledOnce();
  });

  it("正在输入框里打字：不刷新，只提示", () => {
    const ta = document.createElement("textarea");
    ta.value = "我正在问小津";
    document.body.appendChild(ta);
    ta.focus();
    const reload = vi.fn();
    const seen = vi.fn();
    const off = onUpdateReady(seen);
    expect(handleControllerChange(5_000, 0, reload)).toBe("deferred");
    expect(reload).not.toHaveBeenCalled();
    expect(seen).toHaveBeenCalledOnce();
    expect(isUpdateReady()).toBe(true);
    off();
  });

  it("刚打开但读者已经操作过（如问答页提交后输入框已清空、小津正在答）：不刷新，只提示", () => {
    const reload = vi.fn();
    expect(handleControllerChange(30_000, 0, reload, true)).toBe("deferred");
    expect(reload).not.toHaveBeenCalled();
  });

  it("页面已开了一阵：不刷新，只提示", () => {
    const reload = vi.fn();
    expect(handleControllerChange(150_000, 0, reload)).toBe("deferred");
    expect(reload).not.toHaveBeenCalled();
  });

  it("旧代码块加载失败：刷新一次，60 秒内不再刷（防死循环）", () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    } as unknown as Storage;
    const reload = vi.fn();
    expect(handlePreloadError(100_000, reload, storage)).toBe(true);
    expect(handlePreloadError(130_000, reload, storage)).toBe(false);
    expect(handlePreloadError(200_000, reload, storage)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });
});
