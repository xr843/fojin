import { useEffect, useMemo, useState } from "react";
import { Select, Tooltip } from "antd";
import { PictureOutlined } from "@ant-design/icons";
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
    id: "deepseek:v4-flash",
    provider: "deepseek",
    label: "DeepSeek V4 Flash",
    description: "默认模型",
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

interface SelectGroup {
  label: string;
  title: string;
  options: SelectOption[];
}

function buildLabel(model: ChatModelOption): React.ReactNode {
  const suffix = model.available ? "" : "（需配置 Key）";
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

function groupByProvider(models: ChatModelOption[]): SelectGroup[] {
  const groups = new Map<string, ChatModelOption[]>();
  for (const m of models) {
    const arr = groups.get(m.provider) ?? [];
    arr.push(m);
    groups.set(m.provider, arr);
  }
  const result: SelectGroup[] = [];
  for (const [provider, items] of groups) {
    result.push({
      label: provider,
      title: provider,
      options: items.map((m) => ({
        value: m.id,
        label: buildLabel(m),
        title: m.description,
        disabled: !m.available,
      })),
    });
  }
  return result;
}

export default function ChatModelSelector({ value, onChange }: ChatModelSelectorProps) {
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

  const groupedOptions = useMemo<SelectGroup[]>(() => {
    if (!models) return [];
    return groupByProvider(models);
  }, [models]);

  return (
    <Select
      size="small"
      style={{ minWidth: 180 }}
      loading={loading}
      disabled={loading}
      value={value}
      onChange={onChange}
      options={groupedOptions}
    />
  );
}
