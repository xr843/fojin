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

## 环境

IndexTTS 安装在本仓之外（独立第三方项目 + 5.2 GB 权重），用 `INDEXTTS_DIR`
指路，默认 `~/projects/index-tts`。

```bash
# 一次性安装
git clone --depth 1 https://github.com/index-tts/index-tts.git ~/projects/index-tts
cd ~/projects/index-tts && uv sync            # 不要 --all-extras，deepspeed/flash-attn 要编译且用不上
uv run modelscope download --model IndexTeam/IndexTTS-2.5 --local_dir checkpoints
```

ModelScope 实测比 HuggingFace 快约 2.8 倍（国内）。

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
