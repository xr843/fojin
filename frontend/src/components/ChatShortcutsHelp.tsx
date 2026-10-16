import { Modal } from "antd";
import { useTranslation } from "react-i18next";
import { MOD_KEY_LABEL } from "../hooks/useChatShortcuts";

const ROWS: { keys: string[]; labelKey: string }[] = [
  { keys: ["Enter"], labelKey: "chat.shortcuts.send" },
  { keys: ["Shift", "Enter"], labelKey: "chat.shortcuts.newline" },
  { keys: ["Esc"], labelKey: "chat.shortcuts.stop" },
  { keys: [MOD_KEY_LABEL, "K"], labelKey: "chat.shortcuts.new_chat" },
  { keys: ["↑"], labelKey: "chat.shortcuts.recall" },
  { keys: ["/"], labelKey: "chat.shortcuts.focus_input" },
  { keys: ["?"], labelKey: "chat.shortcuts.show_help" },
];

/** 快捷键说明卡片（焦点不在输入框时按 ? 打开）。 */
export default function ChatShortcutsHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      title={t("chat.shortcuts.title")}
      width={360}
      centered
      destroyOnHidden
    >
      <dl className="chat-shortcuts-list">
        {ROWS.map((r) => (
          <div key={r.labelKey} className="chat-shortcuts-row">
            <dt>{t(r.labelKey)}</dt>
            <dd>
              {r.keys.map((k) => <kbd key={k}>{k}</kbd>)}
            </dd>
          </div>
        ))}
      </dl>
    </Modal>
  );
}
