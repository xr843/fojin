# backend/scripts/audio/ —— 在线读诵合成流水线

离线批量把经文合成为读诵音频。**不进 backend 运行时**：依赖单列在本目录的
`requirements.txt`，生产镜像不装。

设计与实施计划见 `docs/superpowers/specs/2026-08-11-reader-audio-design.md`
与 `docs/superpowers/plans/2026-08-11-reader-audio.md`。

## 文件

| 文件 | 职责 |
|---|---|
| `lexicon.tsv` | ⭐ 佛教异读词典 —— 本功能的真资产。词级条目 + 单字默认，繁体键 |
| `g2p.py` | 汉字 → 拼音 / SSML / IndexTTS 标注。词典优先，pypinyin 兜底 |
| `audit_pronunciation.py` | 在真实经文上扫描词典未覆盖的高频字，量化残余读音风险 |
| `tts_indextts.py` | **当前采用**：IndexTTS-2.5 本地适配器 |
| `tts_azure.py` | 备选：Azure Neural TTS 适配器（未启用，无账号） |
| `sample_voices.py` | 音色试听样本生成（Azure 路径） |
| `manifest.yml` | 待合成清单 |

## 为什么读音层要单独存在

pypinyin 在 CBETA 繁体语料上错得很系统（实测 T236a 卷1）：

- **`佛` 出现 123 次，只有 5 次读对**（其余读成 fú）—— 单字默认问题，词表补不了
- pypinyin 自带的佛教词表**只挂简体**：`南無`→`nan2 wu2`，而简体 `南无`→`na1 mo2`

词典因此是两层：词级条目 + 单字默认，统一最长匹配。`仿佛`/`彷彿` 这类
反向保护条目靠更长匹配压过 `佛→fo2`。

## ⚠️ IndexTTS-2.5 许可证义务

模型受 **bilibili 模型使用许可协议**约束（**非** MIT/Apache）。副本见本目录
`INDEXTTS_LICENSE_ZH.txt` / `INDEXTTS_LICENSE_EN.txt` —— 依协议 3.4 b) 必须
在所有副本中保留，**请勿删除**。

按协议 1.5 的定义，合成产出的音频属于「模型输出的修改/创作」，即**衍生品**，
因此三条义务成立：

| 条款 | 义务 | 落实位置 |
|---|---|---|
| 4.1 a) | 发布页面须声明「改动与原权利人无关，不背书不担保不担责」 | 前端 `reader.audio.model_disclaimer` |
| 3.4 b) | 保留原始版权声明及许可协议 | 本目录两份 LICENSE 副本 |
| 3.4 a) | 通过条款约束下游用户 | 站点使用条款 |

其他已核对的条款：**2.2** 商业许可门槛为月活 >1 亿 **或** 年收入 >1 亿人民币
（fojin 月活约 3,000，远低于阈值）；**4.2** 高风险场景禁令不涉及本用例；
**3.4 c)** 不得用于改进其他 AI 模型（我们只做推理，不训练）。

⚠️ **3.2 明确规定人格权侵权由使用方独自承担** —— IndexTTS 是零样本声音克隆，
参考音必须使用**有明确授权的声音**（首选合成方本人）。不得使用未授权的
他人录音，尤其不得克隆法师声音。

## 🛑 现状：2026-08-12 停在音色闸门，本地 IndexTTS 已删除

**这套流水线目前不可运行** —— IndexTTS 的本地安装（约 20 GB）已删，需按下面
「重建」一节恢复。停止的原因不是技术未完成，而是**合成质量没过闸门**。

### 实测记录（别重复这些实验）

参考音是使用者本人的诵经录音（11 秒，截自 24.8 秒原录）。全部用 whisper small
转录后做拼音层音节比对：

| 文本 | 合成命中率 | 该类文本的天花板 | 差距 |
|---|---:|---:|---|
| 文言经文（金剛經开经段，3 分钟） | **70%** | 78%（使用者本人朗读同段实测） | −8 |
| 繁體白话（同参考音同参数） | **74%** | 90%+（干净现代汉语常规水平） | **−16** |

⭐ **关键结论：换成白话没有改善，反而离应有水平更远。** 所以问题**不是**
「模型读不了文言」，而是这套零样本克隆在绝对意义上质量就不够。由此推论：
「拿它读 AI 问答的现代汉语答案」这个替代用途**同样不成立**。

⭐ **两把客观尺子都失效了**：音节命中率（74% vs 人声 78%）与谐噪比
（3.89 vs 人声 4.22）都显示「接近人声」，但使用者实听判定「很多字念错，
很不理想」。**ASR 命中率测不出读音是否正确、语流是否自然。**
将来若重启此方向，需先找到能对应人耳判断的客观判据，否则每轮迭代都要
占用人来听，效率极低。

### 唯一还没试的变量

参考音只用了 24.8 秒录音中的 11 秒。克隆质量对参考音长度敏感，用全长重试
是唯一明显未探索的方向 —— 但没有证据表明它会带来质变。

### 复活的最佳条件

拿到**授权的真人读诵录音**。数据层（`text_audio.engine` 字段）与整套读音层
本就为此预留，届时根本不需要合成模型。

## 环境（重建步骤）

IndexTTS 安装在本仓之外（独立第三方项目，约 20 GB：11 GB 权重 + 8.6 GB venv），
用 `INDEXTTS_DIR` 指路，默认 `~/projects/index-tts`。全程约 20 分钟。

```bash
# 一次性安装
git clone --depth 1 https://github.com/index-tts/index-tts.git ~/projects/index-tts
cd ~/projects/index-tts && uv sync            # 不要 --all-extras，deepspeed/flash-attn 要编译且用不上
uv run modelscope download --model IndexTeam/IndexTTS-2.5 --local_dir checkpoints
```

还要在该 venv 里补两个包（流水线用得到，IndexTTS 自己不装）：

```bash
cd ~/projects/index-tts && uv pip install pypinyin PyYAML
```

ModelScope 实测比 HuggingFace 快约 2.8 倍（国内）。⚠️ 别用 `uv sync --all-extras` ——
`deepspeed` 和 `flash-attn` 都要编译、且本流水线用不上，徒增失败风险。

### 本机实测（RTX 4060 Laptop 8GB / WSL2 / bf16）

| 项 | 值 |
|---|---|
| 权重驻留 | 4.94 GB |
| 推理峰值 | 5.51 GB（激活 0.57 GB）→ 未 OOM |
| 稳态 RTF | 2.78（首次调用 9.87，含约 70s 预热） |
| 模型加载 | 60~200 秒，进程内一次 |

### ⚠️ 两个必须显式关闭的默认值

```python
IndexTTS2(..., use_cuda_kernel=False)      # 默认 True 会触发 nvcc compute_70 编译失败
model.infer(..., text_normalization=False) # 默认 True 会把繁体转成简体
```

`text_normalization` 那条是**静默数据损坏**：实测 `如是我聞：一時，` → `如是我闻,一时,`。
多数繁简转换对读音无害，但简化字合并了不同的字会改读音（`乾闥婆` qián → `干闼婆`
可读 gān；`髮` fà / `發` fā 都变 `发`）。实测关闭后速度无差异。
