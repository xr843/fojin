import { describe, expect, it } from "vitest";
import { activeNavPath } from "./navActive";

describe("activeNavPath", () => {
  it.each([
    ["/read", "/read"],
    ["/texts/9", "/read"],
    ["/texts/9/read", "/read"],
    ["/collections/huayan", "/read"],
    ["/sutras/heart-sutra", "/read"],
    ["/chat", "/chat"],
    ["/share/qa/12", "/chat"],
    ["/dictionary", "/dictionary"],
    ["/sources", "/sources"],
    ["/kg", "/kg"],
    ["/person/3", "/kg"],
    ["/admin/users", "/admin"],
  ])("%s → %s", (path, nav) => {
    expect(activeNavPath(path)).toBe(nav);
  });

  it.each(["/", "/map", "/verify", "/search", "/reader", "/textsx"])("%s 不属于任何导航项", (path) => {
    expect(activeNavPath(path)).toBeNull();
  });
});
