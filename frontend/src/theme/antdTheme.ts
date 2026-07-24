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
      colorBgBase: "#2f2820",
      colorBgContainer: "#4a4133",
      colorBgElevated: "#544a3a",
      colorBorder: "#60553f",
      colorText: "#efe8db",
      colorTextSecondary: "#c6bca6",
      // Text on SOLID primary (buttons): the dark accent is bright, so antd's
      // default white label only reaches 2.99:1. A deep warm ink gives 6.2:1 — and
      // still 4.6:1 on the duller #c16642 the dark algorithm derives for Search.
      colorTextLightSolid: "#17120d",
    },
    components: {
      // antd's Layout Header/Footer do NOT follow colorBgBase — they need their
      // own tokens, or the top/bottom bars stay near-black. Give them a warm
      // elevated tone so the large chrome bars read soft, not oppressive.
      Layout: {
        headerBg: "#4a4133",
        footerBg: "#4a4133",
        bodyBg: "#2f2820",
      },
    },
  };
}
