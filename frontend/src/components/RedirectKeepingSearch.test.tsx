import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router";
import RedirectKeepingSearch from "./RedirectKeepingSearch";

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{`${loc.pathname}${loc.search}${loc.hash}`}</div>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/collections" element={<Where />} />
        <Route path="/topics" element={<RedirectKeepingSearch to="/collections" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RedirectKeepingSearch", () => {
  it("把 /topics 换成 /collections", () => {
    renderAt("/topics");
    expect(screen.getByTestId("where").textContent).toBe("/collections");
  });

  it("保留查询串与锚点（?lang=en 不能丢）", () => {
    renderAt("/topics?lang=en#x");
    expect(screen.getByTestId("where").textContent).toBe("/collections?lang=en#x");
  });
});
