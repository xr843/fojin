/**
 * 每日一段的分享图：浏览器里用 canvas 画一张 1080×1440 竖图（适合微信朋友圈/聊天）。
 * 不走服务器：零成本、不留读者数据。字体用站内已加载的 Noto Serif SC，画之前等它就绪，
 * 否则第一次生成会退回系统默认字体。
 */

export interface ShareCardInput {
  text: string;
  /** 出处一行，如「《金剛般若波羅蜜經》卷1」 */
  source: string;
  /** 顶部小标题，如「今日一段 · 2026-11-24」 */
  heading: string;
  /** 底部落款，如「佛津 fojin.app · 原文逐字可核对」 */
  footer: string;
}

const W = 1080;
const H = 1440;
const SERIF = '"Noto Serif SC", "Source Han Serif SC", "Songti SC", serif';

/** 按宽度把中文断行：逐字量宽，标点不放行首（避头）。 */
export function wrapCjk(measure: (s: string) => number, text: string, maxWidth: number): string[] {
  const NO_LINE_START = "，。、；：？！」』）》,.;:?!";
  const lines: string[] = [];
  let line = "";
  for (const ch of Array.from(text)) {
    if (measure(line + ch) > maxWidth && line) {
      if (NO_LINE_START.includes(ch)) {
        // 标点跟在上一行末尾，宁可略超一点也不让它开头
        line += ch;
        lines.push(line);
        line = "";
        continue;
      }
      lines.push(line);
      line = ch;
    } else {
      line += ch;
    }
  }
  if (line) lines.push(line);
  return lines;
}

export async function renderShareCard(input: ShareCardInput): Promise<Blob> {
  if (document.fonts?.load) {
    try {
      await Promise.all([document.fonts.load(`64px ${SERIF}`, input.text), document.fonts.load(`32px ${SERIF}`, input.source)]);
    } catch {
      /* 字体没加载出来就用回退字体，不阻塞生成 */
    }
  }
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas unavailable");

  // 纸色底 + 细边框
  ctx.fillStyle = "#f8f5ef";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "#d9d0c1";
  ctx.lineWidth = 2;
  ctx.strokeRect(48, 48, W - 96, H - 96);

  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";

  ctx.fillStyle = "#8b2500";
  ctx.font = `500 34px ${SERIF}`;
  ctx.fillText(input.heading, W / 2, 170);
  ctx.fillStyle = "#b08d57";
  ctx.fillRect(W / 2 - 40, 200, 80, 3);

  // 正文：长段落自动缩字号，保证落在中间区域
  // 短句（如「心為法本，心尊心使」）用大字，免得画面中间空一大片
  let size = Array.from(input.text).length <= 16 ? 88 : 64;
  let lines: string[] = [];
  for (; size >= 40; size -= 4) {
    ctx.font = `${size}px ${SERIF}`;
    lines = wrapCjk((s) => ctx.measureText(s).width, input.text, W - 240);
    if (lines.length * size * 1.75 <= 760) break;
  }
  const lineH = size * 1.75;
  let y = 300 + (760 - lines.length * lineH) / 2 + size;
  ctx.fillStyle = "#2b2318";
  for (const ln of lines) {
    ctx.fillText(ln, W / 2, y);
    y += lineH;
  }

  ctx.fillStyle = "#5c4f3d";
  ctx.font = `32px ${SERIF}`;
  ctx.fillText(`—— ${input.source}`, W / 2, 1160);

  ctx.fillStyle = "#746958";
  ctx.font = `26px ${SERIF}`;
  ctx.fillText(input.footer, W / 2, H - 110);

  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob failed"))), "image/png"),
  );
}
