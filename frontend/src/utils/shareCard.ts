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
  /** 经句正文字体（CSS font-family 串）；不给就用衬线 */
  textFont?: string;
}

const W = 1080;
const H = 1440;
const SERIF = '"Noto Serif SC", "Source Han Serif SC", "Songti SC", serif';

/**
 * 按宽度把中文断行：优先在逗号、分号等处换行（「一切有為法，如夢幻泡影，」不把「如」孤零零留在
 * 行尾）；一行里没有合适的标点才逐字断。标点不放行首（避头）。
 */
export function wrapCjk(measure: (s: string) => number, text: string, maxWidth: number): string[] {
  const BREAK_AFTER = "，。；：？！、";
  const NO_LINE_START = "，。、；：？！」』）》”,.;:?!";
  const lines: string[] = [];
  let line = "";
  for (const ch of Array.from(text)) {
    if (!line && lines.length && NO_LINE_START.includes(ch)) {
      // 上一行刚以标点收尾（如「。」），紧跟的后引号「”」也挂在上一行
      lines[lines.length - 1] += ch;
      continue;
    }
    if (measure(line + ch) <= maxWidth || !line) {
      line += ch;
      continue;
    }
    if (NO_LINE_START.includes(ch)) {
      // 标点跟在上一行末尾，宁可略超一点也不让它开头
      lines.push(line + ch);
      line = "";
      continue;
    }
    const chars = Array.from(line);
    let cut = -1;
    for (let i = chars.length - 1; i >= 0; i--) {
      if (BREAK_AFTER.includes(chars[i])) {
        cut = i;
        break;
      }
    }
    // 标点太靠前（不到半行）就不在那儿断，免得一行只有两三个字
    if (cut >= 0 && cut + 1 >= chars.length / 2) {
      lines.push(chars.slice(0, cut + 1).join(""));
      line = chars.slice(cut + 1).join("") + ch;
    } else {
      lines.push(line);
      line = ch;
    }
  }
  if (line) lines.push(line);
  return lines;
}

export async function renderShareCard(input: ShareCardInput): Promise<Blob> {
  if (document.fonts?.load) {
    try {
      await Promise.all([
        document.fonts.load(`64px ${input.textFont ?? SERIF}`, input.text),
        document.fonts.load(`32px ${SERIF}`, input.source),
      ]);
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

  // 正文：长段落自动缩字号，保证落在中间区域
  // 经文 + 出处作为一组，在标题与落款之间居中（出处紧跟经文，不再钉在底部、中间空一大片）。
  // 短句（如「心為法本，心尊心使」）用大字。
  let size = Array.from(input.text).length <= 16 ? 88 : 64;
  let lines: string[] = [];
  for (; size >= 40; size -= 4) {
    ctx.font = `${size}px ${input.textFont ?? SERIF}`;
    lines = wrapCjk((s) => ctx.measureText(s).width, input.text, W - 240);
    if (lines.length * size * 1.75 <= 760) break;
  }
  const lineH = size * 1.75;
  const SOURCE_GAP = 70; // 末行经文底到出处基线
  const groupH = lines.length * lineH + SOURCE_GAP;
  const areaTop = 260;
  const areaBottom = H - 200;
  let y = areaTop + (areaBottom - areaTop - groupH) / 2 + size;
  ctx.fillStyle = "#2b2318";
  for (const ln of lines) {
    ctx.fillText(ln, W / 2, y);
    y += lineH;
  }

  ctx.fillStyle = "#5c4f3d";
  ctx.font = `32px ${SERIF}`;
  ctx.fillText(`—— ${input.source}`, W / 2, y - lineH + size * 0.75 + SOURCE_GAP);

  ctx.fillStyle = "#746958";
  ctx.font = `26px ${SERIF}`;
  ctx.fillText(input.footer, W / 2, H - 110);

  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob failed"))), "image/png"),
  );
}
