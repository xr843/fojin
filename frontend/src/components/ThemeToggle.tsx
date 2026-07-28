import { Segmented } from "antd";
import { SunOutlined, MoonOutlined, DesktopOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useThemeStore, type ThemeMode } from "../stores/themeStore";

export default function ThemeToggle() {
  const { t } = useTranslation();
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  return (
    <Segmented
      size="small"
      value={mode}
      onChange={(v) => setMode(v as ThemeMode)}
      aria-label={t("theme.toggle", "主题")}
      options={[
        { value: "light", icon: <span aria-label="theme-light"><SunOutlined /></span> },
        { value: "dark", icon: <span aria-label="theme-dark"><MoonOutlined /></span> },
        { value: "system", icon: <span aria-label="theme-system"><DesktopOutlined /></span> },
      ]}
    />
  );
}
