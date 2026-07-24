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
      colorTextSecondary: "#bdb29b",
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
