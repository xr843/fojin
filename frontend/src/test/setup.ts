import "@testing-library/jest-dom/vitest";
// Mirror main.tsx: bridge antd v5's static message/Modal/notification methods
// to React 19's render API. Without it these render nothing (see
// src/test/antdStaticMethods.test.tsx and main.tsx).
import "@ant-design/v5-patch-for-react-19";
// Initialize i18n for component tests — zh resources are bundled inline, so
// t() resolves synchronously. Pin the language so jsdom's navigator locale
// (en-US) can't flip tests to a backend-loaded locale.
import i18n from "../i18n";
i18n.changeLanguage("zh");

// jsdom ships no matchMedia. Any component tree containing CursorGlow (i.e.
// anything rendering Layout) throws on mount without this.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}
