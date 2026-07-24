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
      colorPrimary: "#e0754a",
      borderRadius: 2,
      // warm antd's dark neutrals to match the --fj-* palette (spec: antd dark neutrals note)
      colorBgBase: "#322920",
      colorBgContainer: "#423729",
      colorBgElevated: "#4a3f30",
      colorBorder: "#574c3a",
      colorText: "#ece4d6",
      colorTextSecondary: "#b8ad96",
    },
    components: {
      // antd's Layout Header/Footer do NOT follow colorBgBase — they need their
      // own tokens, or the top/bottom bars stay near-black. Give them a warm
      // elevated tone so the large chrome bars read soft, not oppressive.
      Layout: {
        headerBg: "#423729",
        footerBg: "#423729",
        bodyBg: "#322920",
      },
    },
  };
}
