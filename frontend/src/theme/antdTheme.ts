import { theme as antdTheme, type ThemeConfig } from "antd";

export function buildAntdTheme(isDark: boolean): ThemeConfig {
  if (!isDark) {
    return {
      algorithm: antdTheme.defaultAlgorithm,
      token: { colorPrimary: "#8b2500", borderRadius: 2 },
    };
  }
  return {
    algorithm: antdTheme.darkAlgorithm,
    token: {
      colorPrimary: "#d9693c",
      borderRadius: 2,
      // warm antd's dark neutrals to match the --fj-* palette (spec: antd dark neutrals note)
      colorBgBase: "#221c14",
      colorBgContainer: "#2b241b",
      colorBgElevated: "#302921",
      colorBorder: "#423931",
      colorText: "#ece4d6",
      colorTextSecondary: "#a99d89",
    },
  };
}
