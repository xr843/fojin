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
      colorBgBase: "#3a3126",
      colorBgContainer: "#4c4030",
      colorBgElevated: "#554837",
      colorBorder: "#635641",
      colorText: "#ece4d6",
      colorTextSecondary: "#c0b6a0",
    },
    components: {
      // antd's Layout Header/Footer do NOT follow colorBgBase — they need their
      // own tokens, or the top/bottom bars stay near-black. Give them a warm
      // elevated tone so the large chrome bars read soft, not oppressive.
      Layout: {
        headerBg: "#4c4030",
        footerBg: "#4c4030",
        bodyBg: "#3a3126",
      },
    },
  };
}
