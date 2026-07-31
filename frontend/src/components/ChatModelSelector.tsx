import { useEffect, useMemo, useState } from "react";
import { Select, Tooltip } from "antd";
import { PictureOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { fetchChatModels, type ChatModelOption } from "../api/chatModels";
import deepseekLogo from "../assets/llm-logos/deepseek.svg";
import qwenLogo from "../assets/llm-logos/qwen.svg";
import kimiLogo from "../assets/llm-logos/kimi.svg";
import zhipuLogo from "../assets/llm-logos/zhipu.svg";

// Provider → brand logo (lobehub/lobe-icons, MIT). dashscope is Alibaba's
// hosting platform for Qwen, so it shares the Qwen mark; moonshot ships
// Kimi.
const PROVIDER_LOGO: Record<string, string> = {
  deepseek: deepseekLogo,
  dashscope: qwenLogo,
  moonshot: kimiLogo,
  zhipu: zhipuLogo,
};

interface ChatModelSelectorProps {
  value: string;
  onChange: (modelId: string) => void;
}

const FALLBACK_OPTIONS: ChatModelOption[] = [
  {
    id: "deepseek:v4-pro",
    provider: "deepseek",
    label: "DeepSeek V4 Pro",
    description: "默认模型", // i18n-exempt — mirrors the backend catalog payload; real descriptions arrive from the API as data
    vision: false,
    available: true,
    requires_byok: false,
  },
];

interface SelectOption {
  value: string;
  label: React.ReactNode;
  title: string;
  disabled?: boolean;
}

function buildLabel(model: ChatModelOption, t: TFunction): React.ReactNode {
  const suffix = model.available ? "" : t("chat.model_requires_key");
  const text = `${model.label}${suffix}`;
  const logoSrc = PROVIDER_LOGO[model.provider];
  return (
    <Tooltip title={model.description} placement="left" mouseEnterDelay={0.2}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        {logoSrc && (
          <img
            src={logoSrc}
            alt=""
            aria-hidden
            style={{ width: 16, height: 16, flexShrink: 0 }}
          />
        )}
        <span>{text}</span>
        {model.vision && (
          <PictureOutlined style={{ marginLeft: 2, color: "#8b7355" }} />
        )}
      </span>
    </Tooltip>
  );
}

/** 扁平列表，不按 provider 分组。
 *
 * 原先分组的两个代价都不小：分组标题直接显示的是原始 provider id（deepseek /
 * dashscope 这种机器名），5 个模型要占 9 行；而 antd 会给分组内的选项额外加一段
 * 左缩进（.ant-select-item-option-grouped），那正是下拉左侧那条空白。
 * 每个选项前面已经有厂商 logo，provider 这一层信息并没有丢。 */
function buildOptions(models: ChatModelOption[], t: TFunction): SelectOption[] {
  return models.map((m) => ({
    value: m.id,
    label: buildLabel(m, t),
    title: m.description,
    disabled: !m.available,
  }));
}

export default function ChatModelSelector({ value, onChange }: ChatModelSelectorProps) {
  const { t } = useTranslation();
  const [models, setModels] = useState<ChatModelOption[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchChatModels()
      .then((list) => {
        if (cancelled) return;
        const next = list.length > 0 ? list : FALLBACK_OPTIONS;
        setModels(next);
        // Reconcile a stale localStorage choice (e.g. a model that's
        // since been removed from the catalog) so the dropdown never
        // displays a blank value while still POSTing the stale id.
        if (!next.some((m) => m.id === value)) {
          const firstAvailable = next.find((m) => m.available) ?? next[0];
          if (firstAvailable) onChange(firstAvailable.id);
        }
      })
      .catch((err) => {
        // Fallback so chat keeps working when /chat/models is unavailable.
        console.error("[ChatModelSelector] fetchChatModels failed", err);
        if (!cancelled) setModels(FALLBACK_OPTIONS);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // value/onChange intentionally excluded — we only reconcile once per fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const options = useMemo<SelectOption[]>(() => {
    if (!models) return [];
    return buildOptions(models, t);
  }, [models, t]);

  return (
    <Select
      size="small"
      style={{ minWidth: 180 }}
      // 弹层不跟随触发器宽度：触发器只有 180px，跟随会把「通义千问 Qwen3.6 Plus」
      // 「Kimi K2.6（需配置 Key）」这类较长的标签截断。
      popupMatchSelectWidth={false}
      classNames={{ popup: { root: "chat-model-popup" } }}
      loading={loading}
      disabled={loading}
      value={value}
      onChange={onChange}
      options={options}
    />
  );
}
