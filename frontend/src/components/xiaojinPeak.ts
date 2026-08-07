/**
 * 小津默认落点 = 首页背景山水图的山尖。
 *
 * 背景图是 object-fit: cover + object-position: center 70%（home.css），山尖在
 * **视口**里的坐标随窗口尺寸/裁切变动 —— 固定坐标必然跑偏，必须按 cover 的
 * 数学实时换算。这里放纯函数与常量，DOM 测量留在组件里，便于单测。
 *
 * PEAK_FRACTION 是脚本实测：对 public/landscape-bg.webp 右半幅逐列扫「连续
 * 8 像素山体色」的最高点，apex 在 (1046, 287)，即 (0.8172, 0.4003)。换图必须
 * 重测这组常量。
 */

export const BG_NATURAL = { w: 1280, h: 717 };
/** fx 说明：0.8172 是「最高像素」所在列（左肩），0.826 是一次目测误标——
 *  目测值不锚定图像特征，误差会随窗口宽度漂移（用户两次方向相反的投诉
 *  ±0.327 袍宽完美对称，中点 0.8216 与原图山脊中线扫描 0.822 汇合）。
 *  0.822 = apex 下方 16-32px 处山体左右边界的中点，是稳定的图像特征；
 *  0.819 是在它基础上按用户目视微调两轮的终值：先 -2px（0.822→0.821），
 *  再 -4px（0.821→0.819），累计左移 ~6px。换算按 Δpx ÷ 渲染宽 1920px。 */
export const PEAK_FRACTION = { fx: 0.819, fy: 0.4003 };
/** home.css `.home-hero-bg img { object-position: center 70% }` */
export const BG_OBJECT_POS = { x: 0.5, y: 0.7 };

/**
 * cover 裁切下，图内比例点 → 容器内像素坐标。
 *
 * cover 的定义：scale = max(cw/iw, ch/ih)，溢出的那一轴按 object-position
 * 分配裁掉的部分（0.5 = 两边均裁，0.7 = 上边裁 70%）。
 */
export function coverPoint(
  cw: number,
  ch: number,
  natural: { w: number; h: number },
  frac: { fx: number; fy: number },
  objPos: { x: number; y: number },
): { x: number; y: number } {
  const s = Math.max(cw / natural.w, ch / natural.h);
  const rw = natural.w * s;
  const rh = natural.h * s;
  const ox = (cw - rw) * objPos.x;
  const oy = (ch - rh) * objPos.y;
  return { x: ox + frac.fx * rw, y: oy + frac.fy * rh };
}
