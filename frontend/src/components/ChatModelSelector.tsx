import { useEffect, useMemo, useState } from "react";
import { Select, Tooltip } from "antd";
import { PictureOutlined, SettingOutlined } from "@ant-design/icons";
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
  /** 点「配置其他厂商模型」时调用（跳到个人中心的 API Key 面板）。 */
  onConfigureKey: () => void;
}

/** 末项的哨兵值。它不是一个模型 —— 选中它只跳转，不改变当前所选模型。 */
const CONFIGURE_KEY_VALUE = "__configure_key__";

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

/** 只列当前**真能用**的模型，末尾放一个通往 Key 配置页的入口。
 *
 * 不列不可用的，是因为它们占位却点不动：目录里多数厂商没有平台 Key，全列出来会
 * 变成「10 项里 2 项能点」。收进一个入口后，目录随便加厂商都不会撑长这个下拉，
 * 而「还能用别的」这件事仍然说得出来 —— 只是从一排灰条变成一句话。
 *
 * 也不按 provider 分组：分组标题显示的是原始 provider id（deepseek / dashscope
 * 这种机器名），且 antd 会给分组内的选项额外加一段左缩进
 * （.ant-select-item-option-grouped）。每个选项前面已有厂商 logo。 */
function buildOptions(models: ChatModelOption[], t: TFunction): SelectOption[] {
  const usable = models.filter((m) => m.available);
  return [
    ...usable.map((m) => ({
      value: m.id,
      label: buildLabel(m, t),
      title: m.description,
    })),
    {
      value: CONFIGURE_KEY_VALUE,
      label: (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <SettingOutlined />
          {t("chat.configure_other_models")}
        </span>
      ),
      title: t("chat.configure_other_models"),
    },
  ];
}

export default function ChatModelSelector({ value, onChange, onConfigureKey }: ChatModelSelectorProps) {
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
      // 末项不是模型：拦下来只跳转，不写进 value，也不落 localStorage。
      onChange={(next) => {
        if (next === CONFIGURE_KEY_VALUE) {
          onConfigureKey();
          return;
        }
        onChange(next);
      }}
      options={options}
    />
  );
}
