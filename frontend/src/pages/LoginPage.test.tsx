import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import LoginPage from "./LoginPage";

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
  }
  i18n.addResourceBundle("en", "translation", enTranslation, true, true);
});

describe("LoginPage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  afterEach(async () => {
    await i18n.changeLanguage("zh");
  });

  it("renders social login copy in the active UI language", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("or continue with a third-party account")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Log in with GitHub/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Log in with Google/ })).toBeInTheDocument();
  });
});
