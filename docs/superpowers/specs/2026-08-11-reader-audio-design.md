# 在线读诵（阅读页音频播放）设计

日期：2026-08-11
状态：已定稿，待实施
分支：`feat/reader-audio`

## 1. 目标

在「在线阅读」页（`/texts/:id/read`）加入音频朗读，让用户不仅能看佛经，也能听佛经。

**使用场景锁定为「听经」（有声书式）**：用户不盯屏幕 —— 通勤路上、做事时、睡前闭眼听。因此锁屏/后台播放、跨卷连续播放、进度记忆是核心需求；逐句高亮跟随是加分项，不是主线。

**明确不做**「跟读」场景（对着屏幕出声念、需要匀速与语速精调）。两者是不同产品，混在一起会两边都做不好。

## 2. 关键事实（实测，2026-08-11）

| 事实 | 数值 | 来源 |
|---|---|---|
| 语料规模 | 10,531 部 / 617 来源 | 生产 API `/api/stats` |
| 全仓音频基础设施 | **零** | 全库 grep 无 audio/TTS 相关代码 |
| pypinyin 佛教词正确率 | **13/24** | 本地实测，见 §5.1 |
| 辞典 `reading` 字段 | 747,539 条**全空** | 生产 API 抽查 4 词 × 3 源 |
| 金剛經(T236a)卷1 缺字 | gaiji 0 / PUA 0 / 扩展B 0 | 生产 API `/api/texts/10036/juans/1` |
| 金剛經(T236a)卷1 标点 | 句号 245 / 逗号 469 | 同上 |
| `TextReaderPage.tsx` 行数 | 1,092 | 本地 |

**成本量级（估算，总字数未取到实数）**

| 范围 | 字数 | 音频时长(4字/秒) | 存储(64k MP3) | 云 TTS 一次性合成费 |
|---|---|---|---|---|
| 全量 10,531 部 | 5000万 ~ 2亿 | 3,500 ~ 14,000 h | 100 ~ 400 GB | ¥7,500 ~ ¥30,000 |
| **常诵经典 ~50 部** | ~100 万 | **~70 h** | **~2 GB** | **~¥150** |

**全量预合成出局，但这不重要** —— 听经需求分布极度集中，真会有人想听的就是金刚经、心经、地藏经、普门品、阿弥陀经、药师经、楞严咒、法华经、楞严经这几十部。其余一万部论疏、密教仪轨、阿含单品无人会想「听」。**「覆盖率」在本功能上是伪问题。**

## 3. 关键决策

### 3.1 音源：云 TTS 合成（无真人录音）

用户确认拿不到授权的真人读诵录音，因此只能合成。

**由此推论：本功能的成败 100% 押在读音正确性上**（§5）。

### 3.2 生成方式：离线预生成固定清单

人工维护清单 → 本地脚本批量合成 → 上传服务器当静态文件。

**否决「用户点播即合成」的决定性理由**：2026-07 起已有隐身爬虫僵尸网络枚举本站词典接口，把 CF 流量刷到虚高 99.7%。按需合成会让同一批爬虫去枚举 `/api/audio/{text_id}`，**每次枚举都是真金白银的 TTS 调用**，一部百卷的论就是几十元。这个风险必须在架构上堵死，不能靠事后限流。

离线预生成的收益：零任务队列、零后端生成逻辑、账单封顶、爬虫刷不动。代价是加一部经要手动跑一次脚本 —— 在「清单只有 50 部且极少变动」的前提下，这个代价可以接受。

### 3.3 合成引擎：云 TTS（Azure 优先），**不自训模型**、**不自建本地 TTS**

#### 否决「自己训练佛典 TTS 模型」

用户提出训练自有 TTS 以保证佛教用词读音、同时控制成本。三条理由否决：

1. **读音根本不在模型里。** 中文 TTS 流水线是 `文本 → G2P(汉字→拼音) → 声学模型 → 声码器`。「般若→bō rě」是**词典条目**，不是声学参数。训练声学模型学到的是音色与韵律，读音仍由前端 G2P 决定 —— **训练完读音问题原封不动**。要让模型自己学会「迦叶→jiā shè」需端到端字符级 TTS，那撞到第 2 条。

2. **缺的正是拿不到的那个东西。** TTS 微调需 (音频, 文本) 配对：同说话人、干净、5~20 小时。**训练数据和音源是同一个东西**，没有授权音源就没有训练数据。而爬取未授权的法师读诵来训练已不是版权问题，是**声音克隆** —— 合成出的声音听着是某位法师，在念他从未念过的经文。在佛教语境下此路必须封死。

3. **同域三次实测无收益。** 佛典标点项目中「训练自有模型」路线已连续三次无收益：混合域微调（CBETA+佛光各半）0.8248 vs 基线 0.8280，体例偏向几乎不动；引号修复重训 v6 在跨域评测上核心与引号双双输给 v5，域内 macro +13.6pp 系过拟合假象。而 TTS 的数据条件远差于标点 —— 标点尚有海量标注文本，TTS 连一小时授权音频都没有。

**成本动机在离线预生成架构下已消失**：TTS 调用只发生一次，之后全是静态文件。¥150 是一次性总额，不随用户量增长。用数周人力去省 ¥150 不成立。

#### 否决「本地开源 TTS 推理（CosyVoice2/IndexTTS）」

曾一度推荐（理由：读音在 G2P 层可控、边际成本 0、用户有 RTX 4060 与现成 MMS_FA 对齐代码），**已撤回**。撤回理由：

- 与否决训练用的是同一笔账。花 1~2 天搭本地 TTS 环境去省同一笔 ¥150，和花数周训练去省 ¥150 是同一个错误。
- 曾用「用户有 whisper-audit 可出时间戳」为它背书 —— 这是把 whisper-audit 的价值放错了层。**验收层与合成引擎正交**：whisper-audit 验 Azure 的输出和验本地模型的输出一样好用，它不构成换引擎的理由。
- 风险不对称：本地 TTS 环境搭建（CUDA/torch/权重依赖）风险**无界**；Azure 风险**有界**（¥150 + 一个 API 调用）。单人个人项目应选有界风险。
- 本地开源 TTS 的中文音色并不优于 Azure/阿里云 neural voice，B 方案在音色上不占优。

若第 0 步音色试听中云 TTS 全数出局，本地方案可作为退路重新评估（`engine` 字段已为此预留，见 §4.1）。

#### 否决「浏览器 Web Speech API」

零成本零后端、可全覆盖 10,531 部，但对**听经**场景直接出局：不支持 `<phoneme>`（读音完全失控）、iOS 切后台/锁屏即停、无 MediaSession 锁屏控制、音色随设备天差地别。

### 3.4 音色期望管理（诚信约束）

TTS 念佛经，无论哪家，**都不会有法师读诵那个味道**。诵经有腔调、接近吟诵，合成音只能做到「字正腔圆地念」。

因此：**UI 必须明确标注「AI 合成朗读」**，不得让用户以为是法师读的。这与本项目「答案不得含错误或虚假信息」是同一条线。

## 4. 架构

### 4.1 数据模型（2 张新表）

```python
class TextAudio(Base):
    __tablename__ = "text_audio"
    __table_args__ = (
        UniqueConstraint("text_id", "juan_num", "lang", "voice_id",
                         name="uq_text_audio_text_juan_lang_voice"),
    )
    id: int
    text_id: int          # FK buddhist_texts.id
    juan_num: int
    lang: str             # default "zh"
    voice_id: str         # 如 "azure-zh-CN-YunzeNeural"
    engine: str           # "azure" | "aliyun" | "local-cosyvoice" —— 可插拔预留
    audio_path: str       # 相对路径，含 content_hash 前 8 位
    duration_ms: int
    byte_size: int
    format: str           # "mp3"
    char_count: int
    content_hash: str     # ⭐ text_contents.content 的 sha256
    created_at / updated_at

class TextAudioCue(Base):
    __tablename__ = "text_audio_cues"
    __table_args__ = (
        # 前端按 currentTime 二分查找当前 cue，须按时间有序取整卷
        Index("ix_text_audio_cues_audio_time", "audio_id", "time_ms"),
    )
    id: int
    audio_id: int         # FK text_audio.id
    char_start: int       # ⭐ code-point offset into text_contents.content
    char_end: int
    time_ms: int
```

**两个关键设计点：**

1. **`content_hash` 是必需的，不是锦上添花。** 经文被修订后音频即过期。没有它，文本改了音频还在念旧的 —— 那就是「听觉上的错误信息」，违反项目最高准则。

2. **cue 的 `char_start` 用 code-point offset，与现有 `apparatus.char_start` / `line_anchors.char_offset` 完全同一坐标系。** 前端 `cpToU16Map()` 可直接复用，对齐层零成本。

规模（实测）：金剛經卷 1 共 8,353 字 → **574 句**（最长 66 字、最短 2 字）。50 部经约 300 卷 → cue 表约 17 万行。仍可忽略。

> 逐句合成意味着每卷约 574 次 TTS 调用。Azure 按**字符**计费，故调用次数不影响费用；但需注意并发/速率限制，`build_audio.py` 已做断点续传（分片存在即跳过），重跑不重复付费。

⚠️ 建表前须 `\dt` 确认真实表名（本仓存在 model 类名 ≠ 表名的历史，如 `BuddhistSource` → `data_sources`）。迁移编号须核对 `backend/alembic/versions/` 现有链，避免 `down_revision` 冲撞。

### 4.2 离线流水线（不进 backend 运行时）

```
tools/audio/
  manifest.yml       # 清单：text_id + juan 范围 + 音色
  lexicon.tsv        # ⭐ 佛教异读词典 —— 本功能的真资产
  g2p.py             # 文本 → SSML（词典优先，pypinyin 兜底）
  build_audio.py     # 分句 → SSML → TTS → mp3 + cues
  verify.py          # whisper-audit 回验（§6）
```

流程：拉 juan content → 按 CBETA 标点分句 → 词典匹配打 `<phoneme>` → 生成 SSML → 调 TTS（须支持 word boundary 事件）→ 得 mp3 + cue 列表 → 写文件 + 生成导入数据。

**分句直接吃 CBETA 已有标点**（金剛經 245 句号 + 469 逗号），不需要断句模型。

### 4.3 交付

静态文件 `/audio/{text_id}/{juan}-{hash8}.mp3`，nginx 直出，Cloudflare 按扩展名自动缓存。

**文件名带 `content_hash` 前 8 位**，直接绕开已知陷阱：CF 边缘缓存会跨部署存活，重生成音频后旧 URL 会持续命中旧缓存。带 hash 即「重生成 = 新 URL」，永不需要 purge。

API（只读）：`GET /api/texts/{id}/juans/{juan}/audio` → `{url, duration_ms, voice_id, engine, cues[]}`。无音频返回 404。

前端据 `engine`/`voice_id` 渲染「AI 合成朗读」标注（§3.4）—— 标注文案由前端 i18n key 决定，不由后端下发，避免文案散落两端。

### 4.4 前端

```
frontend/src/audio/
  AudioPlayerProvider.tsx   # ⭐ 挂在 app layout 层，持有唯一 <audio>
  useAudioPlayback.ts       # 订阅 currentTime → 当前 cue index（二分查找）
  PlayerBar.tsx             # 底部播放条：播放/暂停/倍速/进度/关闭
  mediaSession.ts           # 锁屏元数据 + 上/下一卷
```

**`TextReaderPage.tsx`（已 1,092 行）只加两处**：

1. 顶栏一个「读诵」按钮（置于 校勘 / 跨藏对照 旁），无音频则不渲染
2. 订阅当前 cue → 给对应 `.cbeta-line` 加持续高亮 class + 自动滚屏

高亮直接复用现有机制：URN 深链已在做 `scrollIntoView` + `cbeta-line-flash`，从瞬时态改为持续态即可。

**播放器住 layout 层是硬约束**：跨卷连续播放是听经场景刚需，而切卷会重挂载页面组件 —— 播放器住在页面里必断。

MediaSession：

```js
navigator.mediaSession.metadata = new MediaMetadata({
  title: `${title_zh} 第${juan}卷`,
  artist: "AI 合成朗读",     // ⭐ 锁屏上也要诚实标注
  album: "佛津",
});
navigator.mediaSession.setActionHandler("nexttrack", → 下一卷);
```

## 5. 读音方案（本功能的核心）

### 5.1 pypinyin 基线实测

24 个高频佛教词，pypinyin 0.55.0 **对 13 / 错 11**：

对：般若 bo re、南无 na mo、摩诃 mo he、伽蓝 qie lan、阿兰若 a lan re、阿僧祇 a seng qi、阿耨多罗三藐三菩提、恒河沙、比丘、那由他、由旬、旃陀罗、覆

错：迦叶（jia ye→**jia she**）、阿闍世/阿闍梨（a du→**a she**）、僧伽（seng ga→**seng qie**）、和南（he nan→**he na**）、瑜伽（yu jia→**yu qie**）、般涅槃（ban→**bo**）、祇树给孤独园（**qi shu ji gu du yuan**）、给孤独（gei→**ji**）、阇维（du wei→**she wei**）、阿鞞跋致（a bing→**a pi**）

pypinyin 确实自带一份佛教词表（般若/南无/摩诃/阿兰若均正确），但覆盖不足。

### 5.2 `lexicon.tsv`：本功能的真资产

约 500 条人工审定的佛教异读表，格式 `词\t拼音(带调)\t备注`。pypinyin 打底，词典优先覆盖。

**这就是「训练一个佛典 TTS 模型」真正想要的东西 —— 只不过它是一个文件，不是一次训练。** 一次投入永久有效，且可直接反哺经论跟读项目。

补充材料：本站辞典库已收《一切經音義》（慧琳音義，唐代佛经注音专书）与《翻梵語》。原始音韵材料在库内，但记的是反切与中古音，**不能即插即用**（现代佛教读音有相当部分是习惯读法，不可由反切直接推导）。可作为人工整理时的参考，不作为自动化数据源。

### 5.3 SSML 注入

Azure：`<phoneme alphabet="sapi" ph="bo1 re3">般若</phoneme>`。

⚠️ **未验证项**：Azure zh-CN 对 `sapi` alphabet 的支持程度需在第 0 步实测确认。若 `<phoneme>` 不可靠，退路是 Azure Custom Lexicon（PLS 格式），或改用支持自定义读音词典的国内厂商（阿里云/火山）。**此项在第 0 步必须验通，否则整个方案不成立。**

## 6. 验收：whisper-audit 当自动读音质检关

`github.com/xr843/whisper-audit`（用户自有）：3 引擎（faster-whisper / FunASR Paraformer / Qwen3-ASR），FunASR 干净普通话 **2.06% CER**，输出**词级 + 字符级时间戳**，自带 CER harness 且**已含同音错误率指标**，离线运行，RTX 4060 Laptop 8GB 实测 24.5x 实时（turbo 62x）。

```
TTS 合成 → whisper-audit 转录 → 转拼音 → 与期望拼音比对 → 不符则挑出人工听
```

三条理由说明此处适用，且不会重蹈法堂那次覆辙：

1. 法堂那次 sherpa-onnx 唱诵文言音节错误率 74.1%，成因是**声学条件**（大殿混响 + 众声嘈杂）；TTS 输出为干净语音，正是 FunASR 2.06% CER 的主场。
2. **同音改词在拼音层无损**（已在经论跟读项目验证：ASR 把「阿賴耶識」认成「阿来耶是」，转拼音同为 `a lai ye shi`）—— **即使 whisper 认错字，拼音比对照样成立**，而此处要检测的正是读音而非字形。
3. whisper-audit 的 CER harness 已含同音错误率一栏，指标现成。

**没有这道关就无法验收**：¥150 合成出 70 小时音频，人不可能自己听完。有了它，24.5x 实时 → 70 小时约 3 小时跑完（turbo 约 1 小时）。

## 7. 分期与终止判据

### 第 0 步：音色定夺（半天，不写生产代码）

合成金剛經开头两分钟，Azure / 阿里云 / 火山各一版，由用户试听定夺。同时验通 §5.3 的 `<phoneme>` 注入。

**判据：放给一位法师听，他会不会皱眉。**

**⛔ 终止判据（真实存在，非走过场）**：若三家音色均不可接受，**整个功能停止**，或退回等待真人录音。**宁可不做，也不要往佛典平台上放一个念经像播新闻的东西** —— 这不是技术债，是失了庄重，比功能缺失严重。

### 第 1 步：`lexicon.tsv`（~500 条）

### 第 2 步：单部经全链路 + whisper-audit 验收关

金剛經一部打通：G2P → SSML → TTS(带 word boundary) → mp3 + cues → 静态交付 → layout 层播放器 → 行级高亮 → 真机验收。

### 第 3 步：扩至清单 ~50 部，¥150 封顶

## 8. 硬约束与已知陷阱

1. **UI 与锁屏元数据必须标「AI 合成朗读」**（§3.4）
2. **播放器住 app layout 层**，不进 `TextReaderPage.tsx`（§4.4）
3. **iOS 锁屏 / 后台播放必须真机验收** —— `<audio>` 在 iOS Safari 上行为特殊，需用户手势启动，CDP 与桌面浏览器均验不出
4. **自动滚屏必须真机验收** —— `behavior:'smooth'` 在 Claude in Chrome (CDP) 中完全不推进（疑 rAF 节流），动画类结论不得由 CDP 外推
5. **PWA 旧壳** —— 部署后首访拿到的是旧 Service Worker 壳；用户报「没生效」先怀疑这个
6. **i18n ratchet** —— 播放器所有文案走 translation key，禁止硬编码中文；插值用 `{{n}}` 不是 `{{count}}`
7. **迁移** —— 建表前 `\dt` 确认真实表名；核对 `down_revision` 链

## 9. 测试策略

- `g2p.py`：以 §5.1 的 24 词为 golden case 做单测。**每条新用例须先实测「无修复时会红」**（本仓有过一天内三次写出恒真断言的记录）
- cue 坐标：断言 `char_start/char_end` 落在 `text_contents.content` 内可取到对应文字（防坐标系错位）
- `content_hash`：文本变更后音频被判定过期的用例
- 前端：cue 二分查找单测；`PlayerBar` 渲染；`ChatPage.test` 式的 mock 陷阱注意（缺 mock 会 CI 全绿仍 exit 1）
- 真机验收清单：iOS 锁屏播放、切后台不断、跨卷续播、自动滚屏

## 10. 未决问题

1. **⚠️ 阅读页真实使用量未知。** 板块使用排名中 chat 715 / dict 428 / kg 219 / parallel 17，**阅读页不在该统计内**。若阅读页本身月活极低，本功能等于给空房间装音响。**建议在第 1 步之前查 Umami，十分钟可得。**
2. **公开流通授权的真人读诵未核实。** 用户「拿不到授权录音」指自有渠道；CC 授权或明确「歡迎流通」的佛教团体音频是另一回事，未核实、不做断言。**一部真人读诵的金剛經价值大于五十部合成音**，值得花半小时查证后再定。查证无果则按本方案执行，不影响架构（`engine` 字段与 `text_audio` 表对真人录音同样适用）。
3. **语料总字数未取到实数**（生产库 SSH 超时，Tailscale 需 sudo 重启）。§2 成本表为估算，但结论在整个估算区间内均成立。
4. **Azure `<phoneme alphabet="sapi">` 对 zh-CN 的实际支持度未验**，见 §5.3，第 0 步必须验通。
5. **清单具体篇目未定**（~50 部常诵经典的确切列表），第 1 步前需人工敲定。
