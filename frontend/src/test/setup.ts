import "@testing-library/jest-dom/vitest";
// Initialize i18n for component tests — zh resources are bundled inline, so
// t() resolves synchronously. Pin the language so jsdom's navigator locale
// (en-US) can't flip tests to a backend-loaded locale.
import i18n from "../i18n";
i18n.changeLanguage("zh");
