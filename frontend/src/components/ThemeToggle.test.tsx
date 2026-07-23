import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ThemeToggle from "./ThemeToggle";
import { useThemeStore } from "../stores/themeStore";

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    useThemeStore.setState({ mode: "system" });
  });

  it("reflects current mode and switches on click", () => {
    render(<ThemeToggle />);
    expect(screen.getByLabelText("theme-light")).toBeTruthy();
    expect(screen.getByLabelText("theme-dark")).toBeTruthy();
    expect(screen.getByLabelText("theme-system")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("theme-dark"));
    expect(useThemeStore.getState().mode).toBe("dark");
  });
});
