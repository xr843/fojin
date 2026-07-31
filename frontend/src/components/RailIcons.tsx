/**
 * 收起态侧栏图标轨专用的描边图标。
 *
 * 为什么不用 @ant-design/icons：antd 的图标是**实心字形**（填充路径），
 * 同尺寸下比 ChatGPT 那套 1.75px 描边图标明显更重，四个并排时尤其扎眼。
 * 描边粗细是字形烘焙进去的，改不了 —— 只能换成 stroke 图标。
 *
 * 约定：24×24 视口、fill=none、stroke=currentColor，尺寸由 CSS 的 width/height
 * 控制（见 .chat-rail-btn svg），颜色随按钮的 color 走。
 */

const BASE = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
};

/** 侧栏面板：圆角矩形 + 左侧分栏线。对应 ChatGPT 的收起/展开图标。 */
export function RailSidebarIcon() {
  return (
    <svg {...BASE} data-rail-icon="sidebar">
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M9 4v16" />
    </svg>
  );
}

/** 铅笔方框：新对话。ChatGPT 用的就是这个字形。 */
export function RailNewChatIcon() {
  return (
    <svg {...BASE} data-rail-icon="new-chat">
      {/* 右上角故意留口，让铅笔从缺口穿出 */}
      <path d="M12.4 4.6H6.6A2.6 2.6 0 0 0 4 7.2v10.2A2.6 2.6 0 0 0 6.6 20h10.2a2.6 2.6 0 0 0 2.6-2.6v-5.8" />
      <path d="M16.6 3.95a1.9 1.9 0 1 1 2.69 2.69l-6.66 6.66-3.35.94.94-3.35z" />
    </svg>
  );
}

/** 放大镜：搜索会话。 */
export function RailSearchIcon() {
  return (
    <svg {...BASE} data-rail-icon="search">
      <circle cx="11" cy="11" r="6.4" />
      <path d="M15.8 15.8 20.4 20.4" />
    </svg>
  );
}

/** 对话气泡：最近聊天。ChatGPT 收起轨上的第四个就是它。 */
export function RailChatsIcon() {
  return (
    <svg {...BASE} data-rail-icon="chats">
      {/* 近圆形泡身 + 左下角小尾巴 */}
      <path d="M20 11.6c0 4.09-3.58 7.4-8 7.4a9 9 0 0 1-2.63-.38L5 20.2l1.32-3.4A7.1 7.1 0 0 1 4 11.6C4 7.51 7.58 4.2 12 4.2s8 3.31 8 7.4z" />
    </svg>
  );
}

/**
 * 齿轮：API Key 配置。
 *
 * 这一格 ChatGPT 没有对应物（它那里是会话气泡，语义完全不同，照搬会变成撒谎），
 * 所以只统一描边风格、保留"设置"语义。轮廓是 8 齿外/内半径交替算出来的
 * 32 点多边形，靠 stroke-linejoin=round 圆化齿尖。
 */
export function RailSettingsIcon() {
  return (
    <svg {...BASE} data-rail-icon="settings">
      <path d="M19.10 10.82 L21.33 10.90 L21.33 13.10 L19.10 13.18 L17.86 16.19 L19.38 17.82 L17.82 19.38 L16.19 17.86 L13.18 19.10 L13.10 21.33 L10.90 21.33 L10.82 19.10 L7.81 17.86 L6.18 19.38 L4.62 17.82 L6.14 16.19 L4.90 13.18 L2.67 13.10 L2.67 10.90 L4.90 10.82 L6.14 7.81 L4.62 6.18 L6.18 4.62 L7.81 6.14 L10.82 4.90 L10.90 2.67 L13.10 2.67 L13.18 4.90 L16.19 6.14 L17.82 4.62 L19.38 6.18 L17.86 7.81 Z" />
      <circle cx="12" cy="12" r="3.3" />
    </svg>
  );
}
