// 必须在 import i18n 之前执行（见 setup.ts 的 import 顺序）。
//
// i18n 初始化时按 querystring → localStorage → navigatorChinese → navigator 检测语言。
// jsdom 的 navigator 是 en-US，于是初始化检测到 en；en 不随包内联，只能走 HttpBackend
// 去取，而这个请求在 jsdom 里要过一段不定的时间才失败——失败那一刻 i18next 才完成
// 「切到 en」，把正在跑的某个用例的界面整个换成英文。全量并发跑时这个时刻随机，
// 表现为 CollectionsPage「1 部经」读到「1 texts」、XiaojinPet 找不到中文文案之类的
// 偶发红（2026-11-05 查实）。先把界面语言写进 localStorage，检测在第二步就落到
// 内联的 zh，根本不发那次请求。
import { UI_LANG_STORAGE_KEY } from "../i18nDetect";

try {
  localStorage.setItem(UI_LANG_STORAGE_KEY, "zh");
} catch {
  /* 没有 localStorage 的环境按原样走 */
}
