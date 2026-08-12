# 在线读诵（阅读页音频播放）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `/texts/:id/read` 加入「听经」式音频朗读 —— 离线预生成的合成读诵，锁屏可播，跨卷连续，逐句高亮。

**Architecture:** 三层解耦。① **离线流水线**（`backend/scripts/audio/`）把经文经「佛教读音层」转成 SSML，调云 TTS 产出 mp3 + 句级时间戳；② **数据层**（`text_audio` / `text_audio_cues` 两表 + 一个只读 API）；③ **前端**播放器挂在 app layout 层（不进阅读页组件），阅读页只订阅当前 cue 做高亮。音频文件走宿主机静态目录，不进 git、不进 Docker 镜像。

**Tech Stack:** Python 3.12 / pypinyin / Azure Speech SDK（可换）/ SQLAlchemy async + Alembic / FastAPI / React 18 + TypeScript + antd 5 / MediaSession API / whisper-audit（回验）

**Spec:** `docs/superpowers/specs/2026-08-11-reader-audio-design.md`

---

## Global Constraints

以下为全局要求，**每个任务都隐含包含本节**：

- **诚信标注**：所有面向用户的位置（播放条、锁屏 MediaSession `artist`）必须标注「AI 合成朗读」，不得让用户以为是法师读诵。
- **⚖️ 许可证义务（非可选）**：IndexTTS-2.5 受 **bilibili 模型使用许可协议**约束（非 MIT/Apache）。按协议 1.5，合成产出的音频属「模型输出的修改/创作」= **衍生品**，触发三条义务：
  - **4.1 a)** 发布页面须声明「改动与原权利人无关，不背书、不担保、不承担责任」→ 文案键 `reader.audio.model_disclaimer`，**必须真实渲染出来**，不能只放在 JSON 里
  - **3.4 b)** 保留原始版权声明及许可协议 → `backend/scripts/audio/INDEXTTS_LICENSE_{ZH,EN}.txt`，**勿删**
  - **3.4 a)** 通过条款约束下游用户 → 站点使用条款（见 Task 16）
  - 已核对无碍：2.2 商业门槛为月活 >1 亿 **或** 年收 >1 亿（fojin 月活约 3,000）；4.2 高风险场景不涉及；3.4 c) 不得改进其他 AI 模型（我们只推理不训练）
  - ⚠️ **3.2 规定人格权（声音权）侵权由使用方独自承担** → 参考音必须用有明确授权的声音，首选合成方本人；**不得克隆法师声音**
- **i18n 键是扁平点号形式**（`"reader.audio.button"`），不是嵌套对象 —— 实测 1,525 键全部含点号、零嵌套。
- **播放器不进阅读页**：`frontend/src/pages/TextReaderPage.tsx` 已 1,092 行；跨卷续播要求 `<audio>` 元素挂在 `frontend/src/components/Layout.tsx` 的 `<Outlet />` 之上，切卷时不重挂载。阅读页只允许新增「读诵按钮」与「高亮订阅」两处。
- **音频禁止入 git**：`.pre-commit-config.yaml:18` 设 `check-added-large-files --maxkb=500`；一卷 mp3 约 17 MB。音频只能通过 rsync 上传到宿主机路径，由 host nginx 直出。
- **i18n ratchet**：CI 的 `npm run i18n:check` 拦截**新增**硬编码中文。所有前端文案走 translation key，三份 locale 同步：`frontend/public/locales/{zh,zh-Hant,en}/translation.json`。插值用 `{{n}}`，**不是** `{{count}}`。
- **繁体优先**：语料是 CBETA 繁体（`金剛般若波羅蜜經`）。词典键一律用繁体形；pypinyin 的佛教词表**只挂在简体上**，繁体走不到（实测：`南無`→`nan2 wu2` ❌ / `南无`→`na1 mo2` ✅）。
- **ruff**：CI 固定 `ruff==0.9.7`，检查范围 `app/ eval/`（`scripts/` 不在内，但仍应跑 `ruff check scripts/audio/` 保持整洁）。
  - ⚠️ 本仓 `select` 只有 `E,F,I,UP,B,SIM,RUF`，**没有 `S`（flake8-bandit）** —— 所以 `# noqa: S310` 是无效指令，会被 RUF100 判为「未使用的 noqa」。不要写。
  - ⚠️ isort 的 `known-first-party = ["app"]` **不含 `scripts`** —— 故 `from scripts.audio.g2p import ...` 与 `pypinyin` 同属第三方组，中间不空行。
  - ⚠️ 本机 ruff 若高于 0.9.7，`ruff check app/ eval/` 可能报 CI 上不存在的新规则（实测 0.15.6 会报一条 `UP047`）。判断"是不是我引入的"以 CI 版本为准。
- **前端 lint**：CI 跑 `eslint --max-warnings 0`，一条 warning 即失败。
- **commit**：conventional commits（`feat:`/`fix:`/`docs:`/`refactor:`），**不加任何 Claude 署名 trailer**；作者邮箱用 `137012659+xr843@users.noreply.github.com`（与本仓既有 commit 一致，本地 repo config 是 protonmail，需显式覆盖）。
- **分支**：`feat/reader-audio`（已创建）。

---

## File Structure

**新建 —— 离线流水线（Python，不进 backend 运行时）**

| 路径 | 职责 |
|---|---|
| `backend/scripts/audio/lexicon.tsv` | 佛教异读词典。词级条目 + 单字默认。本功能的真资产 |
| `backend/scripts/audio/g2p.py` | 汉字 → 拼音 / SSML。词典优先，pypinyin 兜底 |
| `backend/scripts/audio/audit_pronunciation.py` | 在真实经文上扫描残余高危读音，产出报告 |
| `backend/scripts/audio/segment.py` | 按 CBETA 标点分句，产出 (句文, char_start, char_end) |
| `backend/scripts/audio/tts_azure.py` | Azure TTS 适配器：SSML → mp3 + word boundary |
| `backend/scripts/audio/sample_voices.py` | 音色试听样本生成（KILL GATE 用） |
| `backend/scripts/audio/build_audio.py` | 编排：拉正文 → 分句 → SSML → TTS → mp3 + cues.json |
| `backend/scripts/audio/import_audio.py` | mp3 + cues.json → 落盘 + 写库 |
| `backend/scripts/audio/verify_audio.py` | whisper-audit 回验，拼音层比对 |
| `backend/scripts/audio/manifest.yml` | 待合成清单 |
| `backend/scripts/audio/requirements.txt` | 流水线专属依赖（不污染 backend 运行时） |

**新建 —— 后端**

| 路径 | 职责 |
|---|---|
| `backend/app/models/audio.py` | `TextAudio` / `TextAudioCue` ORM |
| `backend/app/services/audio.py` | `get_juan_audio()` 读取逻辑 |
| `backend/alembic/versions/0176_add_text_audio.py` | 建表迁移 |

**新建 —— 前端**

| 路径 | 职责 |
|---|---|
| `frontend/src/audio/AudioPlayerProvider.tsx` | 唯一 `<audio>` + context + MediaSession |
| `frontend/src/audio/useAudioPlayback.ts` | `useAudioPlayer()` hook + cue 二分查找 |
| `frontend/src/audio/PlayerBar.tsx` | 底部播放条 UI |
| `frontend/src/audio/cues.ts` | 纯函数：`findCueIndex()` |

**新建 —— 测试**

| 路径 |
|---|
| `backend/tests/test_audio_g2p.py` |
| `backend/tests/test_audio_segment.py` |
| `backend/tests/test_audio_api.py` |
| `frontend/src/audio/cues.test.ts` |
| `frontend/src/audio/PlayerBar.test.tsx` |

**修改**

| 路径 | 改动 |
|---|---|
| `backend/app/models/__init__.py` | 注册两个新模型 |
| `backend/app/api/texts.py` | 新增 `GET /texts/{id}/juans/{juan}/audio`（router 已在 `main.py:465` 注册，无需改 main.py） |
| `frontend/src/api/client.ts` | 新增 `TextAudioResponse` 类型 + `getJuanAudio()` |
| `frontend/src/components/Layout.tsx` | 用 `AudioPlayerProvider` 包住 `<Outlet />`（第 383 行） |
| `frontend/src/pages/TextReaderPage.tsx` | 顶栏加「读诵」按钮（第 838 行 跨藏对照 旁）+ 高亮订阅 |
| `frontend/public/locales/{zh,zh-Hant,en}/translation.json` | `reader.audio.*` 文案 |
| `frontend/src/styles/*` | `.cbeta-line-playing` 高亮样式 |
| `deploy/host-nginx/fojin.conf` | `location /audio/` 静态直出 |

---

# Phase A — 读音层

> **本阶段无需任何外部凭证，完全离线可测。即使 Phase B 的音色闸门未通过、功能终止，`lexicon.tsv` 仍是可独立复用的资产（可迁至经论跟读项目）。**

## Task 1: 佛教读音层（词典 + G2P）

**Files:**
- Create: `backend/scripts/audio/lexicon.tsv`
- Create: `backend/scripts/audio/g2p.py`
- Create: `backend/scripts/audio/requirements.txt`
- Test: `backend/tests/test_audio_g2p.py`

**Interfaces:**
- Consumes: 无（本任务是根）
- Produces:
  - `load_lexicon(path: Path = LEXICON_PATH) -> dict[str, str]` — 词/字 → 空格分隔带调拼音（数字调，如 `"bo1 re3"`）
  - `segment(text: str, lexicon: dict[str, str]) -> list[tuple[str, str | None]]` — 切成 `[(片段, 拼音 or None)]`，最长匹配优先
  - `to_pinyin(text: str, lexicon: dict[str, str] | None = None) -> str` — 整段 → 空格分隔拼音（供 Task 9 回验比对）
  - `to_ssml(text: str, voice: str, lexicon: dict[str, str] | None = None) -> str` — 整段 → Azure SSML

**背景（实测数据，决定了本任务的设计）：**

在真实语料（`金剛般若波羅蜜經` T236a 卷 1，6,212 汉字）上实测 pypinyin 0.55.0：

- **`佛` 出现 123 次，只有 5 处得到 `fo2`，其余 118 处读成 `fu2`**（95.9% 错）。这是**单字默认读音**问题，词表补不了 —— 必须有单字默认层。
- pypinyin 的佛教词表**只挂简体**：`南無`→`nan2 wu2` ❌ 而 `南无`→`na1 mo2` ✅；`伽藍`→`ga1 lan2` ❌ 而 `伽蓝`→`qie2 lan2` ✅。语料是繁体，所以这些词表等于没有。
- 繁体的一个便宜：繁体中 `舍`(shè) 与 `捨`(shě) 是两个字，因此 `舍 → she4` 可以安全地做**单字默认**；简体做不到。

因此词典是两层结构：**词级条目（最长匹配优先）+ 单字默认**。`仿佛`/`彷彿` 作为词级条目，靠最长匹配压过 `佛 → fo2` 的单字默认。

- [ ] **Step 1: 写下会红的测试**

创建 `backend/tests/test_audio_g2p.py`：

```python
"""佛教读音层 golden 测试。

读音是「在线读诵」的成败点 —— 合成音里读错字，用户听不出来也纠正不了，
比文字错更隐蔽。本文件把已实测的错读钉成回归用例。

基线（pypinyin 0.55.0，繁体，实测 2026-08-11）：
* 佛 → fu2（应 fo2）。金剛經卷1 中 123 次「佛」只有 5 次读对。
* pypinyin 佛教词表只挂简体，繁体全部走不到。
"""

from pathlib import Path

import pytest

from scripts.audio.g2p import load_lexicon, segment, to_pinyin, to_ssml

LEXICON = load_lexicon()

# (文本, 期望拼音) —— 全部用 CBETA 繁体形
GOLDEN = [
    # ① 单字默认层：pypinyin 单字读音在佛典中系统性错误
    ("佛", "fo2"),
    ("伽", "qie2"),
    ("舍", "she4"),
    ("闍", "she2"),
    # ② 词级层：pypinyin 繁体下读错
    ("般若", "bo1 re3"),
    ("般涅槃", "bo1 nie4 pan2"),
    ("南無", "na1 mo2"),
    ("迦葉", "jia1 she4"),
    ("阿闍世", "a1 she2 shi4"),
    ("闍維", "she2 wei2"),
    ("僧伽", "seng1 qie2"),
    ("瑜伽", "yu2 qie2"),
    ("和南", "he2 na2"),
    ("給孤獨", "ji3 gu1 du2"),
    ("阿鞞跋致", "a1 pi2 ba2 zhi4"),
    ("辟支佛", "bi4 zhi1 fo2"),
    ("薄伽梵", "bo2 qie2 fan4"),
    ("阿蘭若", "a1 lan2 re3"),
    ("伽藍", "qie2 lan2"),
    ("剎那", "cha4 na4"),
    ("兜率", "dou1 shuai4"),
    ("羅剎", "luo2 cha4"),
    ("舍利弗", "she4 li4 fu2"),
    ("舍衛", "she4 wei4"),
    ("王舍城", "wang2 she4 cheng2"),
    # ③ 反向保护：最长匹配必须让「仿佛」压过单字默认 佛→fo2
    ("仿佛", "fang3 fu2"),
    ("彷彿", "pang2 fu2"),
    # ④ 真实句子：单字默认在句中生效
    ("佛告須菩提", "fo2 gao4 xu1 pu2 ti2"),
    ("爾時佛", "er3 shi2 fo2"),
]


@pytest.mark.parametrize(("text", "expected"), GOLDEN)
def test_golden_pronunciation(text: str, expected: str) -> None:
    assert to_pinyin(text, LEXICON) == expected


def test_segment_longest_match_wins() -> None:
    """「仿佛」是词级条目，必须整体命中，不能被单字 佛 拆开。"""
    assert segment("仿佛", LEXICON) == [("仿佛", "fang3 fu2")]


def test_segment_passes_through_unknown_text() -> None:
    """词典未收的片段交回 None，由 pypinyin 兜底。"""
    parts = segment("如是我聞", LEXICON)
    assert all(py is None for _, py in parts)
    assert "".join(frag for frag, _ in parts) == "如是我聞"


def test_punctuation_is_not_pronounced() -> None:
    """标点不产生音节 —— 否则 cue 与音频会整体错位。"""
    assert to_pinyin("佛言：「善哉！」", LEXICON) == "fo2 yan2 shan4 zai1"


def test_to_ssml_wraps_lexicon_hits_only() -> None:
    ssml = to_ssml("佛告須菩提", "zh-CN-YunzeNeural", LEXICON)
    assert '<phoneme alphabet="sapi" ph="fo 2">佛</phoneme>' in ssml  # ⚠️ 声调前有空格
    assert "須菩提" in ssml
    assert ssml.startswith("<speak")
    assert 'name="zh-CN-YunzeNeural"' in ssml


def test_to_ssml_escapes_xml() -> None:
    """经文含「」『』等，且 CBETA 校勘串可能带 & < >；未转义会让 SSML 解析失败。"""
    ssml = to_ssml("A<B&C", "zh-CN-YunzeNeural", LEXICON)
    assert "A&lt;B&amp;C" in ssml


def test_lexicon_is_traditional_and_wellformed() -> None:
    """词典自身的完整性：非空、无重复键、拼音格式合法。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / "audio" / "lexicon.tsv"
    seen: set[str] = set()
    rows = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        assert len(cols) >= 2, f"第 {lineno} 行列数不足: {line!r}"
        word, pinyin = cols[0], cols[1]
        assert word not in seen, f"第 {lineno} 行重复键: {word}"
        seen.add(word)
        for syl in pinyin.split():
            assert syl[-1] in "12345", f"第 {lineno} 行 {word} 拼音缺声调: {syl}"
        rows += 1
    assert rows >= 60
```

- [ ] **Step 2: 跑测试，确认它是红的**

```bash
cd backend && pytest tests/test_audio_g2p.py -q
```

预期：`ModuleNotFoundError: No module named 'scripts.audio'` —— 全部 FAIL。

- [ ] **Step 3: 建词典 `backend/scripts/audio/lexicon.tsv`**

⚠️ 内容按 CBETA **繁体**。第三列 `status` 供人工审定用：`seed` = 本次种入待审，`confirmed` = 已由人工/法师确认。

```tsv
# 佛教异读词典 —— 「在线读诵」读音层的真资产
#
# 格式：词或字 \t 空格分隔的带调拼音（数字调，Azure sapi alphabet 格式）\t 状态 \t 备注
# 状态：seed = 机器种入待人工审定 / confirmed = 已确认
#
# ⚠️ 键一律用 CBETA 繁体形。pypinyin 的佛教词表只挂简体，繁体走不到。
# ⚠️ 与 pypinyin 一致的条目也保留 —— 目的是「钉住」读音，防 pypinyin 版本漂移。
# ⚠️ 匹配规则为最长优先，故「仿佛」必须在表内，才能压过单字默认「佛→fo2」。
#
# ── 单字默认层 ──────────────────────────────────────────────
# 这些字在佛典中的读音与通用汉语默认读音系统性不同。
佛	fo2	seed	实测：金剛經卷1 中 123 次「佛」pypinyin 仅 5 次读对
伽	qie2	seed	僧伽/伽藍/瑜伽/摩睺羅伽 皆 qié；pypinyin 默认 ga1
舍	she4	seed	繁体中「捨」(shě) 与「舍」(shè) 分立，故可安全做单字默认
闍	she2	seed	阿闍世/闍維；pypinyin 默认 du1
# ── 词级层 ──────────────────────────────────────────────────
般若	bo1 re3	seed	
般涅槃	bo1 nie4 pan2	seed	
南無	na1 mo2	seed	⚠️ 各地有 ná/nā 之别，取 pypinyin 佛教词表值，待法师审定
摩訶	mo2 he1	seed	
迦葉	jia1 she4	seed	摩訶迦葉
阿闍世	a1 she2 shi4	seed	
阿闍梨	a1 she2 li2	seed	
闍維	she2 wei2	seed	
僧伽	seng1 qie2	seed	
瑜伽	yu2 qie2	seed	
和南	he2 na2	seed	vandana
祇樹	qi2 shu4	seed	
給孤獨	ji3 gu1 du2	seed	
阿鞞跋致	a1 pi2 ba2 zhi4	seed	avaivartika
辟支佛	bi4 zhi1 fo2	seed	pypinyin 作 pi4 zhi1 fu2，两字皆错
薄伽梵	bo2 qie2 fan4	seed	
阿蘭若	a1 lan2 re3	seed	
伽藍	qie2 lan2	seed	
優婆塞	you1 po2 sai1	seed	
優婆夷	you1 po2 yi2	seed	
比丘	bi3 qiu1	seed	
比丘尼	bi3 qiu1 ni2	seed	
乾闥婆	qian2 ta4 po2	seed	
緊那羅	jin3 na4 luo2	seed	
那由他	na2 you2 ta1	seed	
由旬	you2 xun2	seed	
旃陀羅	zhan1 tuo2 luo2	seed	
仿佛	fang3 fu2	seed	⚠️ 反向保护，勿删：压过单字默认 佛→fo2
彷彿	pang2 fu2	seed	⚠️ 反向保护，勿删
阿耨多羅三藐三菩提	a1 nou4 duo1 luo2 san1 miao3 san1 pu2 ti2	seed	
須菩提	xu1 pu2 ti2	seed	
舍利弗	she4 li4 fu2	seed	
目犍連	mu4 jian1 lian2	seed	
迦旃延	jia1 zhan1 yan2	seed	
憍陳如	jiao1 chen2 ru2	seed	
羅睺羅	luo2 hou2 luo2	seed	
波羅蜜	bo1 luo2 mi4	seed	
涅槃	nie4 pan2	seed	
剎那	cha4 na4	seed	pypinyin 作 sha1 na4
兜率	dou1 shuai4	seed	pypinyin 作 dou1 lv4
閻浮提	yan2 fu2 ti2	seed	
阿修羅	a1 xiu1 luo2	seed	
夜叉	ye4 cha1	seed	
羅剎	luo2 cha4	seed	pypinyin 作 luo2 sha1
迦樓羅	jia1 lou2 luo2	seed	
摩睺羅伽	mo2 hou2 luo2 qie2	seed	
毘盧遮那	pi2 lu2 zhe1 na4	seed	
阿彌陀	a1 mi2 tuo2	seed	
陀羅尼	tuo2 luo2 ni2	seed	
三昧	san1 mei4	seed	
舍衛	she4 wei4	seed	
王舍城	wang2 she4 cheng2	seed	
祇園	qi2 yuan2	seed	
苾芻	bi4 chu2	seed	
阿賴耶	a1 lai4 ye2	seed	
末那	mo4 na4	seed	
楞嚴	leng2 yan2	seed	
揭諦	jie1 di4	seed	
菩提薩埵	pu2 ti2 sa4 duo3	seed	
```

- [ ] **Step 4: 建依赖清单 `backend/scripts/audio/requirements.txt`**

```
# 「在线读诵」离线流水线专属依赖 —— 刻意与 backend/requirements.txt 分开，
# 不进 backend 运行时镜像（TTS SDK 体积大且生产环境用不到）。
pypinyin>=0.55.0
azure-cognitiveservices-speech>=1.40.0
PyYAML>=6.0
```

- [ ] **Step 5: 实现 `backend/scripts/audio/g2p.py`**

```python
"""汉字 → 拼音 / SSML，佛教异读以人工词典优先。

读音是「在线读诵」功能的成败点：合成音里读错字，用户听不出来也无从纠正，
比页面上的错字更隐蔽。

为什么不能只靠 pypinyin（均为 2026-08-11 在 T236a 卷1 上实测）：

1. 单字默认读音在佛典中系统性错误。「佛」pypinyin 作 fu2，全卷 123 次
   出现仅 5 次得到 fo2 —— 文言佛典中「佛」大量单用（佛言／爾時佛／白佛言），
   词表补不了，必须有单字默认层。
2. pypinyin 自带的佛教词表只挂在**简体**上。语料是 CBETA 繁体，
   「南無」→ nan2 wu2（简体「南无」→ na1 mo2），等于该词表不存在。

因此词典是两层：词级条目 + 单字默认，统一走最长匹配 —— 单字只是长度为 1
的条目，「仿佛」这类反向保护条目靠更长的匹配自然压过「佛→fo2」。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pypinyin import Style, lazy_pinyin

LEXICON_PATH = Path(__file__).with_name("lexicon.tsv")

# CJK 统一表意文字（含扩展 A/B+ 与兼容区）。非汉字（标点、拉丁、空白）不产生音节。
_HAN_RE = re.compile(
    r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003ffff]"
)

_XML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _escape(text: str) -> str:
    return "".join(_XML_ESCAPES.get(ch, ch) for ch in text)


def _is_han(ch: str) -> bool:
    return bool(_HAN_RE.match(ch))


@lru_cache(maxsize=4)
def load_lexicon(path: Path = LEXICON_PATH) -> dict[str, str]:
    """读词典。返回 {词或字: "空格分隔的带调拼音"}。

    用 lru_cache 是因为流水线会对上千句反复调用；词典只有几百行，常驻无压力。
    """
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        word, pinyin = cols[0].strip(), cols[1].strip()
        if word and pinyin:
            entries[word] = pinyin
    return entries


def segment(text: str, lexicon: dict[str, str]) -> list[tuple[str, str | None]]:
    """最长匹配切分。命中给拼音，未命中的连续片段合并后给 None。

    单字条目与词条目在同一张表里，靠「先试长的」自然让「仿佛」压过「佛」。
    """
    if not text:
        return []
    if not lexicon:
        return [(text, None)]

    max_len = max(len(w) for w in lexicon)
    out: list[tuple[str, str | None]] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        hit: tuple[str, str] | None = None
        for n in range(min(max_len, len(text) - i), 0, -1):
            cand = text[i : i + n]
            if cand in lexicon:
                hit = (cand, lexicon[cand])
                break
        if hit is None:
            buf.append(text[i])
            i += 1
            continue
        if buf:
            out.append(("".join(buf), None))
            buf = []
        out.append(hit)
        i += len(hit[0])
    if buf:
        out.append(("".join(buf), None))
    return out


def to_pinyin(text: str, lexicon: dict[str, str] | None = None) -> str:
    """整段 → 空格分隔的带调拼音（数字调）。

    标点与非汉字不产生音节 —— 供 Task 9 的 whisper-audit 回验做拼音层比对。
    """
    lex = load_lexicon() if lexicon is None else lexicon
    parts: list[str] = []
    for frag, pinyin in segment(text, lex):
        if pinyin is not None:
            parts.append(pinyin)
            continue
        han = "".join(ch for ch in frag if _is_han(ch))
        if han:
            parts.extend(
                lazy_pinyin(han, style=Style.TONE3, neutral_tone_with_five=True)
            )
    return " ".join(parts)


def _split_tone(syllable: str) -> tuple[str, str]:
    """``"bo1"`` → ``("bo", "1")``。无调尾按轻声（5）处理。"""
    if syllable and syllable[-1] in "12345":
        return syllable[:-1], syllable[-1]
    return syllable, "5"


def to_ssml(text: str, voice: str, lexicon: dict[str, str] | None = None) -> str:
    """整段 → Azure SSML。词典命中处逐字包 <phoneme>，其余交给厂商前端。

    ⚠️ 格式由微软官方文档核定（speech-ssml-phonetic-sets）：zh-CN 的 sapi 字母表
    用**拼音 + 空格 + 声调数字**，且**一个 <phoneme> 只包一个汉字**：
        <phoneme alphabet="sapi" ph="zu 3">组</phoneme>
    不是 ph="zu3"，也不能一个标签包整个词。词典内部仍存紧凑形（"bo1 re3"）便于
    人工审读，只在生成 SSML 时展开。

    只包命中片段（而非全文逐字包）：全包会让 TTS 失去词组韵律，读起来像报菜名。
    """
    lex = load_lexicon() if lexicon is None else lexicon
    body: list[str] = []
    for frag, pinyin in segment(text, lex):
        if pinyin is None:
            body.append(_escape(frag))
            continue
        syllables = pinyin.split()
        # 逐字映射的前提是「一字一音节」，对不上就整体放行 —— 错位标注比不标注更糟
        if len(frag) != len(syllables) or not all(_is_han(ch) for ch in frag):
            body.append(_escape(frag))
            continue
        for ch, syl in zip(frag, syllables, strict=True):
            base, tone = _split_tone(syl)
            body.append(
                f'<phoneme alphabet="sapi" ph="{base} {tone}">{_escape(ch)}</phoneme>'
            )
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="zh-CN">'
        f'<voice name="{_escape(voice)}">{"".join(body)}</voice>'
        "</speak>"
    )
```

- [ ] **Step 6: 跑测试，确认全绿**

```bash
cd backend && pytest tests/test_audio_g2p.py -q
```

预期：`35 passed`（29 个 parametrize case + 6 个独立用例）。

- [ ] **Step 7: 变异检验 —— 确认测试不是恒真**

临时把 `lexicon.tsv` 里 `佛	fo2` 一行的拼音改成 `fu2`，重跑：

```bash
cd backend && pytest tests/test_audio_g2p.py -q 2>&1 | tail -3
```

预期：至少 3 条 FAIL（`佛`、`佛告須菩提`、`爾時佛`）。**确认变红后改回 `fo2`**，再跑一次确认恢复全绿。

> 本仓有过一天内三次写出恒真断言的记录 —— 这一步不可跳过。

- [ ] **Step 8: 提交**

```bash
git add backend/scripts/audio/lexicon.tsv backend/scripts/audio/g2p.py \
        backend/scripts/audio/requirements.txt backend/tests/test_audio_g2p.py
git commit -m "feat(audio): 佛教读音层 —— 词典优先的 G2P，钉住 118 处「佛」错读"
```

---

## Task 2: 读音覆盖度审计

**Files:**
- Create: `backend/scripts/audio/audit_pronunciation.py`

**Interfaces:**
- Consumes: `scripts.audio.g2p.load_lexicon`, `scripts.audio.g2p.segment`
- Produces: CLI `python -m scripts.audio.audit_pronunciation --text-id 10036 --juan 1`，输出「词典未覆盖的高频汉字」表

**为什么需要它：** Task 1 的 golden 测试只证明「已知的错已修」，证明不了「还有多少未知的错」。合成前必须知道残余风险面 —— 否则就是 ¥150 换 70 小时无法验收的音频。

- [ ] **Step 1: 实现审计脚本**

```python
"""扫描一卷经文，列出词典未覆盖的汉字，按频次排序。

用途：合成前评估残余读音风险。词典覆盖不了的字会走 pypinyin 默认读音，
其中高频的那些就是下一批该人工审定的候选。

用法：
    cd backend
    python -m scripts.audio.audit_pronunciation --text-id 10036 --juan 1
    python -m scripts.audio.audit_pronunciation --file /path/to/juan.txt --top 40
"""

from __future__ import annotations

import argparse
import collections
import sys
import urllib.request
import json

from pypinyin import Style, lazy_pinyin

from scripts.audio.g2p import _is_han, load_lexicon, segment

DEFAULT_API = "https://fojin.app/api"


# ⚠️ 必须带 User-Agent：Cloudflare 对 urllib 的默认 UA（Python-urllib/3.x）
#    直接回 403，且报错信息里看不出是被 CF 挡的。已实测：裸 urllib → 403，
#    带任意自定义 UA → 200。
_UA = {"User-Agent": "fojin-audio-pipeline/1.0"}


def fetch_juan(api_base: str, text_id: int, juan: int) -> str:
    req = urllib.request.Request(
        f"{api_base}/texts/{text_id}/juans/{juan}", headers=_UA
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("content") or ""


def audit(text: str, top: int) -> int:
    lexicon = load_lexicon()
    uncovered: collections.Counter[str] = collections.Counter()
    covered_chars = 0
    total_han = sum(1 for ch in text if _is_han(ch))

    for frag, pinyin in segment(text, lexicon):
        if pinyin is not None:
            covered_chars += sum(1 for ch in frag if _is_han(ch))
            continue
        uncovered.update(ch for ch in frag if _is_han(ch))

    print(f"汉字总数           : {total_han}")
    print(f"词典覆盖           : {covered_chars} ({covered_chars / max(total_han, 1) * 100:.1f}%)")
    print(f"未覆盖不同字数     : {len(uncovered)}")
    print()
    print(f"未覆盖字 TOP {top}（这些走 pypinyin 默认读音，是残余风险面）：")
    print(f"{'字':<4}{'频次':>6}  pypinyin 默认")
    for ch, n in uncovered.most_common(top):
        default = lazy_pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True)
        print(f"{ch:<4}{n:>6}  {default[0] if default else '?'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="读音覆盖度审计")
    parser.add_argument("--text-id", type=int, help="经号（走线上 API 取正文）")
    parser.add_argument("--juan", type=int, default=1)
    parser.add_argument("--file", help="改为读本地纯文本文件")
    parser.add_argument("--api-base", default=DEFAULT_API)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args(argv)

    if args.file:
        from pathlib import Path

        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text_id:
        text = fetch_juan(args.api_base, args.text_id, args.juan)
    else:
        parser.error("需要 --text-id 或 --file 之一")
    if not text:
        print("未取到正文", file=sys.stderr)
        return 1
    return audit(text, args.top)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 在真实经文上跑一次，留下基线**

```bash
cd backend && python -m scripts.audio.audit_pronunciation --text-id 10036 --juan 1 --top 30
```

预期输出形如「汉字总数 6212 / 词典覆盖 xx%」加一张未覆盖字频次表。

**人工动作：** 看 TOP 30 里有没有明显该收进词典的（例如某个高频专名）。有就补进 `lexicon.tsv` 并回到 Task 1 Step 6 重跑测试。

- [ ] **Step 3: 提交**

```bash
git add backend/scripts/audio/audit_pronunciation.py backend/scripts/audio/lexicon.tsv
git commit -m "feat(audio): 读音覆盖度审计脚本 —— 合成前量化残余风险面"
```

---

# Phase B — 🚦 音色定夺（KILL GATE）

> ## ⛔ 阻塞闸门
>
> **Task 3 完成后必须停下，由用户试听并给出裁决。未通过则整个功能终止，Task 4 及之后一律不执行。**
>
> 判据：**放给一位法师听，他会不会皱眉。**
>
> 这不是走过场 —— 云 TTS 的中文音色均为新闻播音/客服腔，念「如是我聞，一時佛在舍衛國」有真实的出戏风险。宁可不做，也不要往佛典平台上放一个念经像播新闻的东西。
>
> **本任务需要用户提供 TTS 凭证**（`AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION`），实施者无法自行获取。

## Task 3: 音色试听样本

**Files:**
- Create: `backend/scripts/audio/tts_azure.py`
- Create: `backend/scripts/audio/sample_voices.py`

**Interfaces:**
- Consumes: `scripts.audio.g2p.to_ssml`
- Produces:
  - `synthesize(ssml: str, out_path: Path, key: str, region: str) -> list[tuple[int, int]]` — 合成 mp3，返回 `[(text_offset_chars, audio_offset_ms), ...]` 词边界列表
  - CLI `python -m scripts.audio.sample_voices`

- [ ] **Step 1: 实现 Azure 适配器**

创建 `backend/scripts/audio/tts_azure.py`：

```python
"""Azure Speech TTS 适配器：SSML → mp3 + 词边界时间戳。

选 Azure 的唯一理由是 word boundary 事件 —— 它让「播到哪高亮到哪」不需要
另做强制对齐。若第 0 步试听后改用其他厂商，只需另写一个同签名的适配器，
build_audio.py 不用动。

⚠️ <phoneme alphabet="sapi"> 对 zh-CN 的支持度是本方案的未验证前提。
   若合成结果里「佛」仍读 fú，说明 phoneme 未生效，须改走 Custom Lexicon
   (PLS) 或换厂商 —— 这是第 0 步必须验通的事。
"""

from __future__ import annotations

import os
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk


class TtsError(RuntimeError):
    pass


def synthesize(
    ssml: str,
    out_path: Path,
    key: str | None = None,
    region: str | None = None,
) -> list[tuple[int, int]]:
    """把 SSML 合成为 mp3，返回词边界 [(文本字符偏移, 音频毫秒), ...]。

    文本偏移是 Azure 相对**纯文本**（SSML 标签剥离后）的偏移，不是 SSML 串偏移。
    """
    key = key or os.environ.get("AZURE_SPEECH_KEY")
    region = region or os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        raise TtsError("需要环境变量 AZURE_SPEECH_KEY 与 AZURE_SPEECH_REGION")

    cfg = speechsdk.SpeechConfig(subscription=key, region=region)
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_cfg = speechsdk.audio.AudioOutputConfig(filename=str(out_path))
    synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=audio_cfg)

    boundaries: list[tuple[int, int]] = []

    def _on_boundary(evt: speechsdk.SessionEventArgs) -> None:
        # audio_offset 单位是 100 纳秒 tick，转毫秒
        boundaries.append((evt.text_offset, evt.audio_offset // 10_000))

    synth.synthesis_word_boundary.connect(_on_boundary)

    result = synth.speak_ssml_async(ssml).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        detail = ""
        if result.reason == speechsdk.ResultReason.Canceled:
            c = speechsdk.SpeechSynthesisCancellationDetails(result)
            detail = f" reason={c.reason} error={c.error_details}"
        raise TtsError(f"合成失败: {result.reason}{detail}")

    boundaries.sort(key=lambda b: b[1])
    return boundaries
```

- [ ] **Step 2: 实现试听样本脚本**

创建 `backend/scripts/audio/sample_voices.py`：

```python
"""生成音色试听样本 —— 「在线读诵」功能的 KILL GATE。

产出 samples/ 下若干 mp3，由人试听决定这个功能做不做。
同时验证 <phoneme alphabet="sapi"> 是否真的生效（听「佛」是 fó 还是 fú）。

用法：
    cd backend
    export AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=eastasia
    python -m scripts.audio.sample_voices
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.audio.g2p import to_ssml
from scripts.audio.tts_azure import synthesize

# 金剛般若波羅蜜經 開經段 —— 刻意选含「佛」「舍衛」「比丘」「須菩提」的一段，
# 这几个词正是词典在纠正的，听一遍就能判断 phoneme 有没有生效。
SAMPLE_TEXT = (
    "如是我聞：一時，佛在舍衛國祇樹給孤獨園，與大比丘眾千二百五十人俱。"
    "爾時，世尊食時，著衣持鉢，入舍衛大城乞食。"
    "於其城中，次第乞已，還至本處。飯食訖，收衣鉢，洗足已，敷座而坐。"
    "時，長老須菩提在大眾中即從座起，偏袒右肩，右膝著地，合掌恭敬而白佛言："
    "「希有！世尊！如來善護念諸菩薩，善付囑諸菩薩。」"
)

# 候选音色。男声优先 —— 读诵场景女声播音腔出戏更明显。
VOICES = [
    "zh-CN-YunzeNeural",     # 成熟男声，偏沉稳
    "zh-CN-YunjianNeural",   # 男声，偏叙事
    "zh-CN-YunxiNeural",     # 男声，偏年轻
    "zh-CN-XiaoxuanNeural",  # 女声，对照用
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="音色试听样本生成")
    parser.add_argument("--out", default="samples", help="输出目录")
    parser.add_argument("--voices", nargs="*", default=VOICES)
    parser.add_argument(
        "--no-lexicon",
        action="store_true",
        help="不用词典直接念原文 —— 用于 A/B 对照，听出词典有没有生效",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    for voice in args.voices:
        for use_lex in ([False] if args.no_lexicon else [True, False]):
            tag = "lex" if use_lex else "raw"
            ssml = (
                to_ssml(SAMPLE_TEXT, voice)
                if use_lex
                else to_ssml(SAMPLE_TEXT, voice, lexicon={})
            )
            path = out_dir / f"{voice}-{tag}.mp3"
            boundaries = synthesize(ssml, path)
            print(f"✓ {path}  词边界 {len(boundaries)} 个")

    print()
    print("=" * 60)
    print("请试听。判据：放给一位法师听，他会不会皱眉。")
    print()
    print("同时确认 <phoneme> 是否生效 —— 对比 *-lex.mp3 与 *-raw.mp3：")
    print("  「佛在舍衛國」 lex 应读 fó zài shè wèi guó，raw 会读 fú zài shě wèi guó")
    print("  「大比丘眾」   lex 应读 bǐ qiū，raw 亦可能正确")
    print("  「祇樹給孤獨園」 lex 应读 qí shù jǐ gū dú yuán，raw 会读 …gěi gū dú…")
    print()
    print("若 lex 与 raw 听感一致 → phoneme 未生效 → 改走 Custom Lexicon 或换厂商")
    print("若音色整体出戏 → 功能终止，不要继续 Task 4")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 装依赖并生成样本**

```bash
cd backend
source .venv/bin/activate
pip install -r scripts/audio/requirements.txt
export AZURE_SPEECH_KEY='<用户提供>'
export AZURE_SPEECH_REGION='eastasia'
python -m scripts.audio.sample_voices --out /tmp/fojin-voice-samples
```

预期：`/tmp/fojin-voice-samples/` 下 8 个 mp3（4 音色 × lex/raw），每个约 1 分钟。

- [ ] **Step 4: 提交脚本（不提交 mp3）**

```bash
git add backend/scripts/audio/tts_azure.py backend/scripts/audio/sample_voices.py
git commit -m "feat(audio): 音色试听样本脚本 —— 合成前的 kill gate"
```

- [ ] **Step 5: 🚦 交付用户裁决 —— 在此停止**

把 8 个 mp3 交给用户试听，报告两件事：
1. **phoneme 是否生效**（lex vs raw 在「佛」「給孤獨」上是否听得出差别）
2. **音色是否可接受**

**只有用户明确说「继续」才执行 Task 4。** 若 phoneme 未生效但音色可接受，先解决 phoneme（Custom Lexicon / 换厂商），再回到本步骤。

---

# Phase C — 数据层

## Task 4: 音频数据模型与迁移

**Files:**
- Create: `backend/app/models/audio.py`
- Create: `backend/alembic/versions/0176_add_text_audio.py`
- Modify: `backend/app/models/__init__.py`

**Interfaces:**
- Consumes: 无
- Produces: ORM 类 `TextAudio`、`TextAudioCue`（字段见下）

⚠️ 建表前先确认真实表名不冲突（本仓有 model 类名 ≠ 表名的历史，如 `BuddhistSource` → `data_sources`）：

```bash
cd backend && grep -rn "__tablename__" app/models/ | grep -i "audio"
```
预期：无输出（无冲突）。

- [ ] **Step 1: 写模型 `backend/app/models/audio.py`**

```python
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TextAudio(Base):
    """一卷经文的一份合成读诵音频。

    「一份」的粒度是 (经, 卷, 语言, 音色) —— 同一卷换个音色是另一行，
    便于将来并存多个音色（或将来真人录音，engine 另取值即可）。
    """

    __tablename__ = "text_audio"
    __table_args__ = (
        UniqueConstraint(
            "text_id", "juan_num", "lang", "voice_id",
            name="uq_text_audio_text_juan_lang_voice",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("buddhist_texts.id"), index=True, nullable=False
    )
    juan_num: Mapped[int] = mapped_column(Integer, nullable=False)
    lang: Mapped[str] = mapped_column(String(10), server_default="zh")
    # 音色标识，如 "zh-CN-YunzeNeural"
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # 合成引擎 —— 预留可插拔："azure" / "aliyun" / "local-cosyvoice" / "human"
    engine: Mapped[str] = mapped_column(String(40), nullable=False)
    # 相对 /audio/ 的路径，文件名含 content_hash 前 8 位（见下）
    audio_path: Mapped[str] = mapped_column(String(300), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_format: Mapped[str] = mapped_column(String(10), server_default="mp3")
    char_count: Mapped[int] = mapped_column(Integer, server_default="0")
    # ⭐ 合成时所依据的 text_contents.content 的 sha256。
    # 经文被修订后音频即过期 —— 没有它，文本改了音频还在念旧的，
    # 那是「听觉上的错误信息」，违反项目最高准则。
    # 同时它的前 8 位进文件名：Cloudflare 边缘缓存会跨部署存活，
    # 重生成音频后旧 URL 会持续命中旧缓存；带 hash 即「重生成 = 新 URL」，
    # 永不需要 purge。
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cues: Mapped[list["TextAudioCue"]] = relationship(
        back_populates="audio", cascade="all, delete-orphan"
    )


class TextAudioCue(Base):
    """句级时间戳：音频播到 time_ms 时，正文读到 [char_start, char_end)。

    ⭐ char_start/char_end 是 text_contents.content 的 **code-point** 偏移，
    与 text_apparatus.char_start / text_line_anchors.char_offset 同一坐标系 ——
    前端已有的 cpToU16Map() 可直接复用，对齐层零成本。
    """

    __tablename__ = "text_audio_cues"
    __table_args__ = (
        # 前端按 currentTime 二分查找当前 cue，须按时间有序整卷取出
        Index("ix_text_audio_cues_audio_time", "audio_id", "time_ms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("text_audio.id", ondelete="CASCADE"), nullable=False
    )
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    time_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    audio: Mapped["TextAudio"] = relationship(back_populates="cues")
```

- [ ] **Step 2: 注册模型 —— 修改 `backend/app/models/__init__.py`**

在 `from app.models.audit import AdminAuditLog` 之后插入（isort 要求按字母序，`audio` 在 `audit` 之前）：

```python
from app.models.audio import TextAudio, TextAudioCue
```

⚠️ 正确位置：`from app.models.annotation import ...` 与 `from app.models.answer_review import ...` 之后、`from app.models.audit import ...` 之前 —— isort 按模块名排序，`app.models.audio` < `app.models.audit`。

并在 `__all__` 列表中按字母序加入 `"TextAudio",` 与 `"TextAudioCue",`。

- [ ] **Step 3: 写迁移 `backend/alembic/versions/0176_add_text_audio.py`**

⚠️ 当前 head 已核实为 `0175`（`0175_add_daily_metric_counts.py`）。

```python
"""在线读诵：音频与句级时间戳

Revision ID: 0176
Revises: 0175
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0176"
down_revision: str | None = "0175"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "text_audio",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_id", sa.Integer(), nullable=False),
        sa.Column("juan_num", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(length=10), server_default="zh", nullable=False),
        sa.Column("voice_id", sa.String(length=100), nullable=False),
        sa.Column("engine", sa.String(length=40), nullable=False),
        sa.Column("audio_path", sa.String(length=300), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("audio_format", sa.String(length=10), server_default="mp3", nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["text_id"], ["buddhist_texts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "text_id", "juan_num", "lang", "voice_id",
            name="uq_text_audio_text_juan_lang_voice",
        ),
    )
    op.create_index("ix_text_audio_text_id", "text_audio", ["text_id"])

    op.create_table(
        "text_audio_cues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audio_id", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["audio_id"], ["text_audio.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_text_audio_cues_audio_time", "text_audio_cues", ["audio_id", "time_ms"]
    )


def downgrade() -> None:
    op.drop_index("ix_text_audio_cues_audio_time", table_name="text_audio_cues")
    op.drop_table("text_audio_cues")
    op.drop_index("ix_text_audio_text_id", table_name="text_audio")
    op.drop_table("text_audio")
```

- [ ] **Step 4: 验证迁移链完整 —— 上下各跑一次**

CI 的 `alembic-dry-run.yml` 会跑 `upgrade head` 再 `downgrade -1`。本地先自验：

```bash
cd backend && python - <<'EOF'
import os, re
d = "alembic/versions"
revs, downs = {}, {}
for f in os.listdir(d):
    if not f.endswith(".py"):
        continue
    s = open(os.path.join(d, f), encoding="utf-8").read()
    r = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)', s, re.M)
    dn = re.search(r'^down_revision(?::\s*[^=]+)?\s*=\s*["\']([^"\']+)', s, re.M)
    if r:
        revs[r.group(1)] = f
        downs[r.group(1)] = dn.group(1) if dn else None
heads = [r for r in revs if r not in set(downs.values())]
dupes = [v for v in set(downs.values()) if list(downs.values()).count(v) > 1 and v]
print("HEAD:", heads)
print("重复 down_revision（必须为空）:", dupes)
EOF
```

预期：`HEAD: ['0176']`，`重复 down_revision（必须为空）: []`。

> 一个碰撞的 `down_revision` 会让整个服务起不来 —— 这一步不可跳过。

- [ ] **Step 5: 确认模型能被导入（`__init__.py` 改对了）**

```bash
cd backend && JWT_SECRET_KEY=x_test_secret_key_at_least_32_chars_long \
  python -c "from app.models import TextAudio, TextAudioCue; print(TextAudio.__tablename__, TextAudioCue.__tablename__)"
```

预期：`text_audio text_audio_cues`

- [ ] **Step 6: 跑 ruff**

```bash
cd backend && ruff check app/
```

预期：`All checks passed!`

- [ ] **Step 7: 提交**

```bash
git add backend/app/models/audio.py backend/app/models/__init__.py \
        backend/alembic/versions/0176_add_text_audio.py
git commit -m "feat(audio): text_audio / text_audio_cues 两表 —— content_hash 判音频过期"
```

---

## Task 5: 音频读取 API

**Files:**
- Create: `backend/app/services/audio.py`
- Modify: `backend/app/api/texts.py`（在第 242 行 `read_juan_line_anchors` 之后新增端点；schema 按本仓惯例内联在同文件，参见 `texts.py:121`）
- Test: `backend/tests/test_audio_api.py`

**Interfaces:**
- Consumes: `app.models.audio.TextAudio`、`TextAudioCue`
- Produces:
  - `get_juan_audio(session, text_id, juan_num, lang="zh") -> dict | None`，返回 `{"voice_id", "engine", "audio_path", "duration_ms", "cues": [{"char_start", "char_end", "time_ms"}]}`
  - `GET /api/texts/{text_id}/juans/{juan_num}/audio` → `TextAudioResponse`

- [ ] **Step 1: 写下会红的测试 `backend/tests/test_audio_api.py`**

```python
"""在线读诵音频 API。

本仓测试不连真库，故这里覆盖两件不需要 DB 的事：
* 无音频时端点返回 404（而不是 200 + 空对象 —— 前端据此决定不渲染读诵按钮）
* service 把 ORM 行拼成响应字典的形状正确，尤其 cues 必须按 time_ms 升序
  （前端二分查找依赖有序，乱序会让高亮跳到别处）
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.audio import build_audio_payload


def _cue(char_start: int, char_end: int, time_ms: int) -> MagicMock:
    m = MagicMock()
    m.char_start, m.char_end, m.time_ms = char_start, char_end, time_ms
    return m


def _audio(cues: list[MagicMock]) -> MagicMock:
    m = MagicMock()
    m.voice_id = "zh-CN-YunzeNeural"
    m.engine = "azure"
    m.audio_path = "10036/1-a1b2c3d4.mp3"
    m.duration_ms = 2_100_000
    m.content_hash = "a1b2c3d4" + "0" * 56
    m.cues = cues
    return m


def test_payload_sorts_cues_by_time() -> None:
    """cue 必须按时间升序 —— 前端 findCueIndex 是二分查找。"""
    audio = _audio([_cue(20, 30, 5000), _cue(0, 10, 0), _cue(10, 20, 2500)])
    payload = build_audio_payload(audio)
    assert [c["time_ms"] for c in payload["cues"]] == [0, 2500, 5000]
    assert [c["char_start"] for c in payload["cues"]] == [0, 10, 20]


def test_payload_url_is_rooted_at_audio() -> None:
    """URL 必须是 /audio/ 下的绝对路径 —— 由宿主机 nginx 直出，不经后端。"""
    payload = build_audio_payload(_audio([]))
    assert payload["url"] == "/audio/10036/1-a1b2c3d4.mp3"


def test_payload_carries_engine_for_frontend_labelling() -> None:
    """前端据 engine 决定是否标「AI 合成朗读」——真人录音将来用 engine='human'。"""
    payload = build_audio_payload(_audio([]))
    assert payload["engine"] == "azure"
    assert payload["voice_id"] == "zh-CN-YunzeNeural"


async def test_endpoint_404_when_no_audio(client) -> None:
    """没有音频的卷必须 404，前端据此不渲染读诵按钮。"""
    from app.api import texts as texts_api

    original = texts_api.get_juan_audio
    texts_api.get_juan_audio = AsyncMock(return_value=None)
    try:
        resp = await client.get("/api/texts/999999/juans/1/audio")
        assert resp.status_code == 404
    finally:
        texts_api.get_juan_audio = original
```

⚠️ fixture 名是 `client`（不是 `async_client`），定义在 `backend/tests/conftest.py:64`。它已全局把 `get_db` 覆盖成 `yield None`（第 81 行），所以只要 `get_juan_audio` 被 mock 掉、不碰 DB，本用例即可跑通。`pytest.ini` 设了 `asyncio_mode = auto`，**不需要** `@pytest.mark.anyio` 装饰器。

- [ ] **Step 2: 跑测试，确认它是红的**

```bash
cd backend && pytest tests/test_audio_api.py -q
```

预期：`ModuleNotFoundError: No module named 'app.services.audio'` —— 全部 FAIL。

- [ ] **Step 3: 实现 service `backend/app/services/audio.py`**

```python
"""在线读诵音频的读取逻辑。

音频文件本身不经后端 —— 由宿主机 nginx 从静态目录直出（一卷约 17 MB，
走 FastAPI 是纯浪费）。后端只回「有没有、在哪、什么时候读到哪」。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audio import TextAudio


def build_audio_payload(audio: TextAudio) -> dict:
    """ORM 行 → API 响应字典。

    cues 按 time_ms 升序 —— 前端 findCueIndex 是二分查找，乱序会让高亮跳位。
    """
    cues = sorted(audio.cues, key=lambda c: c.time_ms)
    return {
        "url": f"/audio/{audio.audio_path}",
        "voice_id": audio.voice_id,
        "engine": audio.engine,
        "duration_ms": audio.duration_ms,
        "cues": [
            {"char_start": c.char_start, "char_end": c.char_end, "time_ms": c.time_ms}
            for c in cues
        ],
    }


async def get_juan_audio(
    session: AsyncSession, text_id: int, juan_num: int, lang: str = "zh"
) -> dict | None:
    """取某一卷的音频。同卷多音色时取最新创建的一条。"""
    stmt = (
        select(TextAudio)
        .where(
            TextAudio.text_id == text_id,
            TextAudio.juan_num == juan_num,
            TextAudio.lang == lang,
        )
        .options(selectinload(TextAudio.cues))
        .order_by(TextAudio.created_at.desc())
        .limit(1)
    )
    audio = (await session.execute(stmt)).scalar_one_or_none()
    return build_audio_payload(audio) if audio else None
```

- [ ] **Step 4: 加端点 —— 修改 `backend/app/api/texts.py`**

在文件顶部 import 区加入：

```python
from app.services.audio import get_juan_audio
```

在 `JuanLineAnchorsResponse` 类（第 121 行附近）之后加入 schema：

```python
class AudioCueItem(BaseModel):
    char_start: int
    char_end: int
    time_ms: int


class TextAudioResponse(BaseModel):
    text_id: int
    juan_num: int
    url: str
    voice_id: str
    engine: str
    duration_ms: int
    cues: list[AudioCueItem]
```

在 `read_juan_line_anchors`（第 242 行结束）之后加入端点：

```python
@router.get("/texts/{text_id}/juans/{juan_num}/audio", response_model=TextAudioResponse)
async def read_juan_audio(
    text_id: int,
    juan_num: int,
    lang: str = Query("zh", description="正文语言"),
    db: AsyncSession = Depends(get_db),
):
    """某一卷的合成读诵音频与句级时间戳。

    获取某一卷的在线读诵音频。音频文件本身由静态目录直出，此处只回地址与
    时间戳；没有音频的卷返回 404，前端据此不渲染「读诵」按钮。"""
    payload = await get_juan_audio(db, text_id, juan_num, lang)
    if payload is None:
        raise HTTPException(status_code=404, detail="该卷暂无读诵音频")
    return TextAudioResponse(text_id=text_id, juan_num=juan_num, **payload)
```

⚠️ 确认 `HTTPException` 与 `Query` 已在该文件 import（本仓 `texts.py` 已用到二者；若缺则补 `from fastapi import HTTPException, Query`）。

⚠️ `texts.router` 已在 `backend/app/main.py:465` 注册，**无需改 main.py**。

- [ ] **Step 5: 跑测试，确认全绿**

```bash
cd backend && pytest tests/test_audio_api.py -q
```

预期：`4 passed`

- [ ] **Step 6: 变异检验**

把 `build_audio_payload` 里的 `sorted(audio.cues, key=lambda c: c.time_ms)` 改成 `list(audio.cues)`，重跑：

预期 `test_payload_sorts_cues_by_time` FAIL。确认变红后改回。

- [ ] **Step 7: 全量回归 + lint**

```bash
cd backend && pytest tests/ -q && ruff check app/
```

预期：全部 PASS，`All checks passed!`

- [ ] **Step 8: 提交**

```bash
git add backend/app/services/audio.py backend/app/api/texts.py backend/tests/test_audio_api.py
git commit -m "feat(audio): 卷级读诵音频只读端点，无音频返回 404"
```

---

# Phase D — 合成流水线

## Task 6: 按 CBETA 标点分句

**Files:**
- Create: `backend/scripts/audio/segment.py`
- Test: `backend/tests/test_audio_segment.py`

**Interfaces:**
- Consumes: 无
- Produces: `split_sentences(content: str) -> list[Sentence]`，`Sentence` 是 `NamedTuple(text: str, char_start: int, char_end: int)`，偏移为 **code-point** 偏移

**为什么不需要断句模型：** CBETA 正文标点齐全 —— 实测 `金剛般若波羅蜜經` 卷 1 含 245 个句号、469 个逗号、189 个叹号、135 个问号。分句是纯规则问题。

- [ ] **Step 1: 写下会红的测试 `backend/tests/test_audio_segment.py`**

```python
"""按 CBETA 标点分句 —— cue 坐标的产生处。

char_start/char_end 是 text_contents.content 的 code-point 偏移，与
text_apparatus.char_start / text_line_anchors.char_offset 同一坐标系。
坐标一错，高亮就整体跳位，且不会有任何报错 —— 故此处逐条钉死。
"""

from scripts.audio.segment import split_sentences


def test_splits_on_full_stop() -> None:
    sents = split_sentences("如是我聞。一時佛在舍衛國。")
    assert [s.text for s in sents] == ["如是我聞。", "一時佛在舍衛國。"]


def test_offsets_index_back_into_source() -> None:
    """最重要的一条：偏移必须能原样切回原文。"""
    src = "如是我聞。一時佛在舍衛國。與大比丘眾千二百五十人俱。"
    for s in split_sentences(src):
        assert src[s.char_start : s.char_end] == s.text


def test_offsets_are_contiguous_and_cover_everything() -> None:
    """句与句之间不能有洞 —— 有洞就意味着有正文永远不会被高亮。"""
    src = "爾時，世尊食時，著衣持鉢。入舍衛大城乞食！於其城中？次第乞已。"
    sents = split_sentences(src)
    assert sents[0].char_start == 0
    assert sents[-1].char_end == len(src)
    # 不要加 strict=True —— sents 与 sents[1:] 长度本就差 1，strict 会直接抛 ValueError
    for a, b in zip(sents, sents[1:]):
        assert a.char_end == b.char_start


def test_closing_quote_stays_with_its_sentence() -> None:
    """「」『』：收尾引号必须跟着句号走，不能自己成一句。"""
    sents = split_sentences("佛言：「善哉，善哉！」須菩提白佛言。")
    assert sents[0].text == "佛言：「善哉，善哉！」"
    assert sents[1].text == "須菩提白佛言。"


def test_long_clause_splits_on_comma() -> None:
    """超长句按逗号二次切分 —— 一个 cue 覆盖太长会让高亮失去意义。"""
    src = "爾時，" + "諸比丘眾皆大歡喜信受奉行，" * 12 + "作禮而去。"
    sents = split_sentences(src, max_chars=40)
    assert all(len(s.text) <= 60 for s in sents)
    assert "".join(s.text for s in sents) == src


def test_newlines_do_not_create_empty_sentences() -> None:
    """CBETA 正文含换行；空句会产出 duration 为 0 的 cue，污染时间轴。"""
    sents = split_sentences("如是我聞。\n\n一時佛在舍衛國。\n")
    assert all(s.text.strip() for s in sents)
    assert "".join(s.text for s in sents).replace("\n", "") == "如是我聞。一時佛在舍衛國。"
```

- [ ] **Step 2: 跑测试，确认它是红的**

```bash
cd backend && pytest tests/test_audio_segment.py -q
```

预期：`ModuleNotFoundError` —— 全部 FAIL。

- [ ] **Step 3: 实现 `backend/scripts/audio/segment.py`**

```python
"""按 CBETA 标点把一卷正文切成句 —— cue 坐标的产生处。

不需要断句模型：CBETA 正文标点齐全（实测 T236a 卷1：句号 245、逗号 469、
叹号 189、问号 135）。这是纯规则问题。

⚠️ char_start/char_end 是 **code-point** 偏移，与 text_apparatus.char_start /
   text_line_anchors.char_offset 同一坐标系，前端 cpToU16Map() 可直接复用。
   Python 字符串索引天然是 code-point 偏移，不需要额外转换 —— 但**不要**
   在这里做任何 UTF-16 换算，那是前端的事。
"""

from __future__ import annotations

from typing import NamedTuple

# 句末标点：这些之后断句
_TERMINALS = "。！？；"
# 收尾符号：紧跟句末标点时并入本句，不另起一句
_TRAILERS = "」』）〕】》”’"
# 次级断点：超长句在此二次切分
_SECONDARY = "，、："


class Sentence(NamedTuple):
    text: str
    char_start: int
    char_end: int


def _flush(src: str, start: int, end: int, out: list[Sentence]) -> None:
    """把 [start, end) 收成一句 —— 全是空白就丢掉，避免零时长 cue。"""
    if end > start and src[start:end].strip():
        out.append(Sentence(src[start:end], start, end))


def _split_long(src: str, start: int, end: int, max_chars: int) -> list[Sentence]:
    """超长句按次级标点二次切分。一个 cue 覆盖太长，高亮就失去意义。"""
    if end - start <= max_chars:
        return [Sentence(src[start:end], start, end)]
    out: list[Sentence] = []
    seg_start = start
    for i in range(start, end):
        if src[i] in _SECONDARY and i - seg_start >= max_chars:
            _flush(src, seg_start, i + 1, out)
            seg_start = i + 1
    _flush(src, seg_start, end, out)
    # 全段无次级标点时上面会退化成一句，原样返回即可
    return out or [Sentence(src[start:end], start, end)]


def split_sentences(content: str, max_chars: int = 38) -> list[Sentence]:
    """切句。返回的 (char_start, char_end) 必须满足 content[start:end] == text。

    ⚠️ ``max_chars`` 默认 38，刻意压在 IndexTTS ``low_vram`` 的内部分段阈值
    （40 字，见 infer_v2_5.py ``split_text_by_punctuation(text, max_chars=40)``）
    **之下**。一旦触发内部分段，段间会插 ``interval_silence``（默认 200ms）的静音 ——
    实测该静音就是合成音里那 3 处不自然停顿的来源（人声连贯朗读时是 0 处）。
    而把 interval_silence 设为 0 会引入拼接不连续，谐噪比从 3.89 掉到 2.54，
    更糟。正解是**根本不触发分段**。

    金剛經全卷 570 句实测：平均 14.3 字、中位 10 字，仅 5.1% 超过 40 字 ——
    压到 38 后全部句子都在阈值内。

    相邻句首尾相接、无空洞 —— 有空洞就意味着有正文永远不会被高亮。
    句间的纯空白（换行）并入前一句的尾部，不单独成句。
    """
    out: list[Sentence] = []
    start = 0
    i = 0
    n = len(content)
    while i < n:
        if content[i] in _TERMINALS:
            end = i + 1
            # 收尾引号跟着句号走
            while end < n and content[end] in _TRAILERS:
                end += 1
            # 句后的空白并入本句，保证首尾相接
            while end < n and content[end].isspace():
                end += 1
            out.extend(_split_long(content, start, end, max_chars))
            start = end
            i = end
            continue
        i += 1
    _flush(content, start, n, out)
    return out
```

- [ ] **Step 4: 跑测试，确认全绿**

```bash
cd backend && pytest tests/test_audio_segment.py -q
```

预期：`6 passed`

- [ ] **Step 5: 变异检验**

把 `_flush` 中的 `if end > start and src[start:end].strip():` 改成 `if end > start:`，重跑：

预期 `test_newlines_do_not_create_empty_sentences` FAIL。确认后改回。

再把 `while end < n and content[end].isspace(): end += 1` 整段删掉，重跑：

预期 `test_offsets_are_contiguous_and_cover_everything` FAIL。确认后改回。

- [ ] **Step 6: 在真实经文上自验坐标**

```bash
cd backend && python - <<'EOF'
import json, urllib.request
from scripts.audio.segment import split_sentences

req = urllib.request.Request(
    "https://fojin.app/api/texts/10036/juans/1",
    headers={"User-Agent": "fojin-audio-pipeline/1.0"},  # 不带 UA 会被 CF 挡成 403
)
with urllib.request.urlopen(req, timeout=30) as r:
    content = json.load(r)["content"]

sents = split_sentences(content)
assert sents[0].char_start == 0, "首句未从 0 开始"
assert sents[-1].char_end == len(content), "末句未覆盖到结尾"
for a, b in zip(sents, sents[1:]):
    assert a.char_end == b.char_start, f"空洞: {a.char_end} != {b.char_start}"
for s in sents:
    assert content[s.char_start:s.char_end] == s.text, "偏移切不回原文"
print(f"✓ {len(sents)} 句，坐标全部可切回原文，无空洞")
print("前 3 句:", [s.text for s in sents[:3]])
EOF
```

预期（已实测）：`✓ 574 句，坐标全部可切回原文，无空洞`，最长句 66 字、最短 2 字。

> 574 这个数字是本计划撰写时用同一份实现实跑得到的 —— 若实施后数字差很多，说明分句逻辑被改动过，回头核对。

- [ ] **Step 7: 提交**

```bash
git add backend/scripts/audio/segment.py backend/tests/test_audio_segment.py
git commit -m "feat(audio): CBETA 标点分句 —— cue 坐标与校勘/行锚同坐标系"
```

---

## Task 7: 合成编排

**Files:**
- Create: `backend/scripts/audio/build_audio.py`
- Create: `backend/scripts/audio/manifest.yml`

**Interfaces:**
- Consumes: `scripts.audio.g2p.to_ssml`、`scripts.audio.segment.split_sentences`、`scripts.audio.tts_azure.synthesize`
- Produces: 产出 `out/{text_id}/{juan}-{hash8}.mp3` 与同名 `.cues.json`（供 Task 8 入库）

**cue 时间戳怎么来的：** 逐句合成，每句一次 TTS 调用，句的起始时间 = 之前所有句的时长累计。这比「整卷一次合成 + 靠 word boundary 反推句边界」可靠得多 —— word boundary 的 `text_offset` 是相对 SSML 剥标签后的纯文本，含 `<phoneme>` 时映射容易错位。代价是句间会有极短的拼接痕迹，用 `pydub` 拼接时不加静音即可。

- [ ] **Step 1: 建清单 `backend/scripts/audio/manifest.yml`**

```yaml
# 待合成清单。「听经」需求高度集中，不追求覆盖 10,531 部。
#
# ⚠️ 第一期只做一部（金剛經），走通全链路并验收音色后再扩。
voice: zh-CN-YunzeNeural
engine: azure
lang: zh

texts:
  - text_id: 7
    title: 金剛般若波羅蜜經
    cbeta: T0235
    translator: 姚秦 鳩摩羅什
    chars: 6505          # ≈ 27 分钟音频 / ≈ 13 MB / 合成费约 ¥2
    juans: [1]

# 第二期候选：⛔ 不预设清单，上线后按**真实播放数据**排序决定。
```

⭐ **选本理由（2026-08-11 修订，原写 text_id 10036 是错的）**：念诵传统、流通本、
早晚课用的都是 **T0235 鳩摩羅什譯**（「一時，佛在舍衛國祇樹給孤獨園」）；
T0236a 菩提流支譯（「一時婆伽婆，在舍婆提城…」）是研究对读用的，没人会照它念。

⚠️ **不要按阅读排行定清单。** Umami 实测（30 天）菩提流支本 42 访客 / 羅什本 15 访客 ——
这个与念诵传统完全倒挂的结果，恰恰证明**阅读数据是听经需求的弱代理**。同理，阅读
TOP15 里瑜伽師地論排第 2、出三藏記集第 7、俱舍論頌疏記第 9，这些研究型文本没人会听
（阅读页用户中研究型约占四成）。真实听经需求只能靠上线后的播放数据来测。

- [ ] **Step 2: 实现 `backend/scripts/audio/build_audio.py`**

```python
"""合成编排：正文 → 分句 → SSML → TTS → mp3 + cues.json。

逐句合成而非整卷一次合成：cue 的时间戳直接由「前面各句时长累计」得到，
不依赖 word boundary 的 text_offset 反推 —— 后者是相对 SSML 剥标签后的
纯文本偏移，正文里插了 <phoneme> 之后极易错位，且错位不会报错。

⚠️ 音频文件绝不进 git：一卷约 17 MB，而 .pre-commit-config.yaml 设了
   check-added-large-files --maxkb=500。产物落在 out/（已 gitignore）。

用法：
    cd backend
    export AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=eastasia
    python -m scripts.audio.build_audio --manifest scripts/audio/manifest.yml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

from scripts.audio.g2p import to_ssml
from scripts.audio.segment import split_sentences
from scripts.audio.tts_azure import synthesize

DEFAULT_API = "https://fojin.app/api"


# ⚠️ 必须带 User-Agent：Cloudflare 对 urllib 的默认 UA（Python-urllib/3.x）
#    直接回 403，且报错信息里看不出是被 CF 挡的。已实测：裸 urllib → 403，
#    带任意自定义 UA → 200。
_UA = {"User-Agent": "fojin-audio-pipeline/1.0"}


def fetch_juan(api_base: str, text_id: int, juan: int) -> str:
    req = urllib.request.Request(
        f"{api_base}/texts/{text_id}/juans/{juan}", headers=_UA
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("content") or ""


def mp3_duration_ms(path: Path) -> int:
    """用 ffprobe 读真实时长。不信任 TTS 返回值 —— 拼接后只有文件本身作数。"""
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return int(float(out.stdout.strip()) * 1000)


def concat_mp3(parts: list[Path], out_path: Path) -> None:
    """用 ffmpeg concat demuxer 无损拼接（不重编码，不插静音）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        for p in parts:
            fh.write(f"file '{p.resolve()}'\n")
        list_path = fh.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
             "-c", "copy", str(out_path)],
            capture_output=True, check=True,
        )
    finally:
        Path(list_path).unlink(missing_ok=True)


def build_juan(
    api_base: str, text_id: int, juan: int, voice: str, engine: str, out_root: Path
) -> dict:
    content = fetch_juan(api_base, text_id, juan)
    if not content:
        raise RuntimeError(f"text_id={text_id} juan={juan} 无正文")

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    hash8 = content_hash[:8]
    sentences = split_sentences(content)
    print(f"[{text_id}/{juan}] {len(content)} 字 → {len(sentences)} 句  hash={hash8}")

    work_dir = out_root / str(text_id) / f"{juan}-{hash8}.parts"
    work_dir.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    cues: list[dict] = []
    elapsed_ms = 0
    for idx, sent in enumerate(sentences):
        part_path = work_dir / f"{idx:05d}.mp3"
        if not part_path.exists():  # 断点续传：重跑不重复付费
            synthesize(to_ssml(sent.text, voice), part_path)
        cues.append(
            {
                "char_start": sent.char_start,
                "char_end": sent.char_end,
                "time_ms": elapsed_ms,
            }
        )
        elapsed_ms += mp3_duration_ms(part_path)
        parts.append(part_path)
        if (idx + 1) % 25 == 0:
            print(f"  …{idx + 1}/{len(sentences)} 句，累计 {elapsed_ms / 1000:.0f}s")

    audio_path = out_root / str(text_id) / f"{juan}-{hash8}.mp3"
    concat_mp3(parts, audio_path)
    duration_ms = mp3_duration_ms(audio_path)

    meta = {
        "text_id": text_id,
        "juan_num": juan,
        "lang": "zh",
        "voice_id": voice,
        "engine": engine,
        "audio_path": f"{text_id}/{juan}-{hash8}.mp3",
        "duration_ms": duration_ms,
        "byte_size": audio_path.stat().st_size,
        "audio_format": "mp3",
        "char_count": len(content),
        "content_hash": content_hash,
        "cues": cues,
    }
    meta_path = out_root / str(text_id) / f"{juan}-{hash8}.cues.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ {audio_path}  {duration_ms / 60000:.1f} 分钟  {meta['byte_size'] / 1e6:.1f} MB")
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合成读诵音频")
    parser.add_argument("--manifest", default="scripts/audio/manifest.yml")
    parser.add_argument("--out", default="out/audio")
    parser.add_argument("--api-base", default=DEFAULT_API)
    args = parser.parse_args(argv)

    cfg = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
    out_root = Path(args.out)
    total = 0
    for entry in cfg["texts"]:
        for juan in entry["juans"]:
            try:
                build_juan(
                    args.api_base, entry["text_id"], juan,
                    cfg["voice"], cfg["engine"], out_root,
                )
                total += 1
            except Exception as exc:  # noqa: BLE001
                print(f"✗ text_id={entry['text_id']} juan={juan}: {exc}", file=sys.stderr)
    print(f"\n完成 {total} 卷 → {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 把产物目录加进 gitignore**

在 `backend/.gitignore`（若无则在仓库根 `.gitignore`）追加：

```
# 读诵音频产物 —— 一卷约 17 MB，绝不入库
backend/out/audio/
```

- [ ] **Step 4: 跑一卷，验证产物**

```bash
cd backend
export AZURE_SPEECH_KEY='<用户提供>' AZURE_SPEECH_REGION='eastasia'
python -m scripts.audio.build_audio
ls -la out/audio/10036/
```

预期：一个约 17 MB 的 `1-<hash8>.mp3` 与一个 `1-<hash8>.cues.json`。

- [ ] **Step 5: 自验 cue 时间轴单调且不超时长**

```bash
cd backend && python - <<'EOF'
import json, glob
p = glob.glob("out/audio/10036/*.cues.json")[0]
m = json.load(open(p, encoding="utf-8"))
cues = m["cues"]
assert cues[0]["time_ms"] == 0, "首 cue 不在 0"
for a, b in zip(cues, cues[1:]):
    assert b["time_ms"] >= a["time_ms"], "时间轴非单调"
    assert a["char_end"] == b["char_start"], "字符坐标有空洞"
assert cues[-1]["time_ms"] < m["duration_ms"], "末 cue 超出音频时长"
print(f"✓ {len(cues)} 个 cue，时间轴单调，坐标连续，总时长 {m['duration_ms']/60000:.1f} 分钟")
EOF
```

- [ ] **Step 6: 提交（只提交脚本，不提交 mp3）**

```bash
git status --short   # 确认 out/audio/ 未出现在待提交列表
git add backend/scripts/audio/build_audio.py backend/scripts/audio/manifest.yml .gitignore
git commit -m "feat(audio): 逐句合成编排 —— cue 由句时长累计，不依赖 word boundary 反推"
```

---

## Task 8: 音频入库

**Files:**
- Create: `backend/scripts/audio/import_audio.py`

**Interfaces:**
- Consumes: Task 7 产出的 `*.cues.json`；`app.models.audio.TextAudio`、`TextAudioCue`
- Produces: CLI `python -m scripts.audio.import_audio --dir out/audio`

- [ ] **Step 1: 实现导入脚本**

```python
"""把 build_audio.py 的产物写进库。

幂等：同 (text_id, juan_num, lang, voice_id) 已存在则整条替换（连带 cue），
以便重生成后重导入。

⚠️ 只写数据库。mp3 文件的上传是另一件事（Task 14），刻意分开 ——
   数据库写在开发机执行，文件上传走 rsync 到生产宿主机。

用法：
    cd backend && python -m scripts.audio.import_audio --dir out/audio
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.audio import TextAudio, TextAudioCue


async def import_one(meta: dict) -> str:
    async with async_session_maker() as session:
        existing = (
            await session.execute(
                select(TextAudio).where(
                    TextAudio.text_id == meta["text_id"],
                    TextAudio.juan_num == meta["juan_num"],
                    TextAudio.lang == meta["lang"],
                    TextAudio.voice_id == meta["voice_id"],
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            await session.execute(
                delete(TextAudioCue).where(TextAudioCue.audio_id == existing.id)
            )
            await session.delete(existing)
            await session.flush()

        audio = TextAudio(
            text_id=meta["text_id"],
            juan_num=meta["juan_num"],
            lang=meta["lang"],
            voice_id=meta["voice_id"],
            engine=meta["engine"],
            audio_path=meta["audio_path"],
            duration_ms=meta["duration_ms"],
            byte_size=meta["byte_size"],
            audio_format=meta["audio_format"],
            char_count=meta["char_count"],
            content_hash=meta["content_hash"],
        )
        session.add(audio)
        await session.flush()

        session.add_all(
            [
                TextAudioCue(
                    audio_id=audio.id,
                    char_start=c["char_start"],
                    char_end=c["char_end"],
                    time_ms=c["time_ms"],
                )
                for c in meta["cues"]
            ]
        )
        await session.commit()
        action = "替换" if existing is not None else "新增"
        return f"{action} text_id={meta['text_id']} juan={meta['juan_num']} cue={len(meta['cues'])}"


async def run(directory: Path) -> int:
    metas = sorted(directory.rglob("*.cues.json"))
    if not metas:
        print(f"{directory} 下没有 *.cues.json")
        return 1
    for path in metas:
        meta = json.loads(path.read_text(encoding="utf-8"))
        print("✓", await import_one(meta))
    print(f"\n共导入 {len(metas)} 卷")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="音频元数据入库")
    parser.add_argument("--dir", default="out/audio")
    args = parser.parse_args(argv)
    return asyncio.run(run(Path(args.dir)))


if __name__ == "__main__":
    raise SystemExit(main())
```

⚠️ 确认 `async_session_maker` 的真实名字：

```bash
cd backend && grep -n "async_session_maker\|sessionmaker\|^async_session" app/database.py | head -5
```
若名字不同（例如 `AsyncSessionLocal`），按实际改。

- [ ] **Step 2: 导入并核验**

```bash
cd backend && python -m scripts.audio.import_audio --dir out/audio
```

预期：`✓ 新增 text_id=10036 juan=1 cue=574`

- [ ] **Step 3: 端到端验 API**

```bash
cd backend && uvicorn app.main:app --port 8001 &
sleep 5
curl -s localhost:8001/api/texts/10036/juans/1/audio | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('url:', d['url'])
print('engine:', d['engine'], '/ voice:', d['voice_id'])
print('时长:', d['duration_ms']/60000, '分钟')
print('cue 数:', len(d['cues']))
print('前 3 个 cue:', d['cues'][:3])
assert d['url'].startswith('/audio/'), 'URL 不是 /audio/ 开头'
assert d['cues'] == sorted(d['cues'], key=lambda c: c['time_ms']), 'cue 未按时间排序'
print('✓ 通过')
"
kill %1
```

- [ ] **Step 4: 提交**

```bash
git add backend/scripts/audio/import_audio.py
git commit -m "feat(audio): 音频元数据入库脚本，幂等替换"
```

---

## Task 9: whisper-audit 读音回验

**Files:**
- Create: `backend/scripts/audio/verify_audio.py`

**Interfaces:**
- Consumes: `scripts.audio.g2p.to_pinyin`；外部 `whisper-audit`（`github.com/xr843/whisper-audit`）
- Produces: CLI `python -m scripts.audio.verify_audio --meta out/audio/10036/1-*.cues.json --transcript <whisper-audit 输出>`，产出可疑句列表

**为什么必须有这一关：** ¥150 合成出 70 小时音频，人不可能自己听完。whisper-audit 在干净语音上 FunASR 2.06% CER、RTX 4060 Laptop 24.5x 实时（turbo 62x），70 小时约 3 小时（turbo 约 1 小时）跑完。

**为什么比对拼音而不是比对字：** 已在经论跟读项目验证 —— ASR 把「阿賴耶識」认成「阿来耶是」，转拼音同为 `a lai ye shi`。**即使 whisper 认错字，拼音比对照样成立**，而此处要检测的正是读音而非字形。

⚠️ 与法堂那次 ASR 失败（sherpa-onnx 唱诵文言音节错误率 74.1%）的区别：那次是**声学条件**（大殿混响 + 众声嘈杂）；TTS 输出是干净语音，正是 FunASR 的主场。

- [ ] **Step 1: 实现回验脚本**

```python
"""用 whisper-audit 的转录结果回验合成音频的读音。

流程：
    1) whisper-audit 转录 mp3，导出带时间戳的 JSON
    2) 本脚本按 cue 时间窗切出每句的转录文本
    3) 期望文本与转录文本各转拼音，逐音节比对
    4) 输出音节不一致率超阈值的句子，供人工试听

用法：
    # 先用 whisper-audit 转录（在其仓库内）
    #   python -m whisper_audit transcribe <mp3> --engine funasr --out transcript.json
    cd backend
    python -m scripts.audio.verify_audio \
        --meta out/audio/10036/1-a1b2c3d4.cues.json \
        --transcript /path/to/transcript.json \
        --content-api https://fojin.app/api
"""

from __future__ import annotations

import argparse
import difflib
import json
import urllib.request
from pathlib import Path

from scripts.audio.g2p import to_pinyin

# 音节不一致率超过这个比例就挑出来人工听。
# ASR 本身有 ~2% CER，阈值定太低会淹没在噪声里。
SUSPECT_THRESHOLD = 0.15


def load_transcript_segments(path: Path) -> list[tuple[int, int, str]]:
    """whisper-audit 转录 → [(start_ms, end_ms, text), ...]。

    兼容两种常见形状：顶层 list，或 {"segments": [...]}。
    时间字段秒/毫秒都接受。
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    segs = raw.get("segments", raw) if isinstance(raw, dict) else raw
    out: list[tuple[int, int, str]] = []
    for s in segs:
        start = s.get("start_ms", s.get("start", 0))
        end = s.get("end_ms", s.get("end", 0))
        if isinstance(start, float) or (isinstance(start, int | float) and end < 10_000 and end > 0 and isinstance(end, float)):
            start, end = int(start * 1000), int(end * 1000)
        out.append((int(start), int(end), s.get("text", "")))
    return out


def text_in_window(segs: list[tuple[int, int, str]], start_ms: int, end_ms: int) -> str:
    """取与 [start_ms, end_ms) 有重叠的转录片段，拼成一段。"""
    return "".join(t for s, e, t in segs if e > start_ms and s < end_ms)


def syllable_mismatch(expected: str, actual: str) -> float:
    """两串拼音的音节层不一致率。空转录记满分（1.0），即漏读。"""
    exp = expected.split()
    act = actual.split()
    if not exp:
        return 0.0
    if not act:
        return 1.0
    matcher = difflib.SequenceMatcher(None, exp, act, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return 1.0 - matched / len(exp)


def fetch_content(api_base: str, text_id: int, juan: int) -> str:
    # ⚠️ 带 UA，否则 Cloudflare 回 403（见 build_audio.py 同处注释）
    req = urllib.request.Request(
        f"{api_base}/texts/{text_id}/juans/{juan}",
        headers={"User-Agent": "fojin-audio-pipeline/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("content") or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合成音频读音回验")
    parser.add_argument("--meta", required=True, help="build_audio 产出的 *.cues.json")
    parser.add_argument("--transcript", required=True, help="whisper-audit 转录 JSON")
    parser.add_argument("--content-api", default="https://fojin.app/api")
    parser.add_argument("--threshold", type=float, default=SUSPECT_THRESHOLD)
    args = parser.parse_args(argv)

    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    content = fetch_content(args.content_api, meta["text_id"], meta["juan_num"])
    segs = load_transcript_segments(Path(args.transcript))
    cues = meta["cues"]

    suspects: list[tuple[float, int, str, str, str]] = []
    for i, cue in enumerate(cues):
        end_ms = cues[i + 1]["time_ms"] if i + 1 < len(cues) else meta["duration_ms"]
        expected_text = content[cue["char_start"] : cue["char_end"]]
        expected_py = to_pinyin(expected_text)
        actual_py = to_pinyin(text_in_window(segs, cue["time_ms"], end_ms))
        rate = syllable_mismatch(expected_py, actual_py)
        if rate > args.threshold:
            suspects.append((rate, cue["time_ms"], expected_text, expected_py, actual_py))

    suspects.sort(reverse=True)
    print(f"总句数 {len(cues)}，可疑 {len(suspects)} 句（阈值 {args.threshold:.0%}）")
    print(f"整体可疑率 {len(suspects) / max(len(cues), 1):.1%}\n")
    for rate, t_ms, text, exp, act in suspects[:40]:
        mm, ss = divmod(t_ms // 1000, 60)
        print(f"[{mm:02d}:{ss:02d}] 不一致 {rate:.0%}")
        print(f"  原文 {text}")
        print(f"  期望 {exp}")
        print(f"  实听 {act}\n")
    if len(suspects) > 40:
        print(f"（另有 {len(suspects) - 40} 句未列出，用 --threshold 收紧后再看）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 用 whisper-audit 转录并回验**

```bash
# 在 whisper-audit 仓库内转录（干净语音用 funasr 引擎，CER 2.06%）
cd ~/projects/whisper-audit
python -m whisper_audit transcribe \
    ~/projects/fojin/backend/out/audio/10036/1-*.mp3 \
    --engine funasr --out /tmp/jingang-transcript.json

# 回到 fojin 回验
cd ~/projects/fojin/backend
python -m scripts.audio.verify_audio \
    --meta out/audio/10036/1-*.cues.json \
    --transcript /tmp/jingang-transcript.json
```

⚠️ whisper-audit 的实际 CLI 子命令名以其 README 为准，若不同请按实调整；`load_transcript_segments` 已兼容 `list` 与 `{"segments": [...]}` 两种形状与秒/毫秒两种时间单位。

- [ ] **Step 3: 人工判读**

按可疑率高低试听 TOP 条目。三类结果分别处理：

| 现象 | 判断 | 处理 |
|---|---|---|
| 原文含词典未收的专名，实听读音明显不对 | **真错读** | 补进 `lexicon.tsv`，回 Task 1 Step 6 重跑测试，重新合成该句 |
| 期望与实听拼音差异集中在轻声/儿化/连读 | ASR 噪声 | 忽略 |
| 实听为空 | 漏读或拼接错位 | 查该句的 part mp3 是否为 0 字节，重合成 |

**验收线：真错读为 0 才进 Task 10。**

- [ ] **Step 4: 提交**

```bash
git add backend/scripts/audio/verify_audio.py backend/scripts/audio/lexicon.tsv
git commit -m "feat(audio): whisper-audit 拼音层回验 —— 认错字不影响读音判定"
```

---

# Phase E — 前端

## Task 10: API 客户端

**Files:**
- Modify: `frontend/src/api/client.ts`（在第 647 行 `getJuanLineAnchors` 之后）

**Interfaces:**
- Consumes: `GET /api/texts/{id}/juans/{juan}/audio`
- Produces:
  - `export interface AudioCue { char_start: number; char_end: number; time_ms: number }`
  - `export interface TextAudioResponse { text_id: number; juan_num: number; url: string; voice_id: string; engine: string; duration_ms: number; cues: AudioCue[] }`
  - `export async function getJuanAudio(textId: number, juanNum: number): Promise<TextAudioResponse>`

- [ ] **Step 1: 加类型与函数**

在 `frontend/src/api/client.ts` 的 `getJuanLineAnchors` 函数之后插入：

```typescript
export interface AudioCue {
  char_start: number;
  char_end: number;
  time_ms: number;
}

export interface TextAudioResponse {
  text_id: number;
  juan_num: number;
  /** 静态路径，由宿主机 nginx 直出，不经后端 */
  url: string;
  voice_id: string;
  /** "azure" | "aliyun" | "local-cosyvoice" | "human" —— 前端据此决定是否标「AI 合成朗读」 */
  engine: string;
  duration_ms: number;
  cues: AudioCue[];
}

/** 某卷的读诵音频。无音频的卷后端返回 404，调用方应容忍失败并隐藏读诵入口。 */
export async function getJuanAudio(textId: number, juanNum: number): Promise<TextAudioResponse> {
  const { data } = await api.get<TextAudioResponse>(`/texts/${textId}/juans/${juanNum}/audio`);
  return data;
}
```

- [ ] **Step 2: 类型检查**

```bash
cd frontend && npx tsc -b --noEmit
```

预期：无输出（通过）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(audio): 前端读诵音频 API 客户端"
```

---

## Task 11: cue 查找纯函数

**Files:**
- Create: `frontend/src/audio/cues.ts`
- Test: `frontend/src/audio/cues.test.ts`

**Interfaces:**
- Consumes: `AudioCue`（Task 10）
- Produces: `findCueIndex(cues: AudioCue[], timeMs: number): number` —— 返回当前时间所处的 cue 下标，早于首个 cue 或空数组返回 `-1`

**为什么单独成文件：** 这是纯函数，能脱离 React 与 DOM 测试。播放期间它每秒被调用数次，正确性由二分保证；混在组件里既难测也难看出复杂度。

- [ ] **Step 1: 写下会红的测试 `frontend/src/audio/cues.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { findCueIndex } from "./cues";
import type { AudioCue } from "../api/client";

const cue = (time_ms: number, char_start: number, char_end: number): AudioCue => ({
  time_ms,
  char_start,
  char_end,
});

// 三句：0-2.5s / 2.5-5s / 5s-末尾
const CUES: AudioCue[] = [cue(0, 0, 10), cue(2500, 10, 20), cue(5000, 20, 30)];

describe("findCueIndex", () => {
  it("空数组返回 -1", () => {
    expect(findCueIndex([], 1000)).toBe(-1);
  });

  it("时间落在第一句区间内", () => {
    expect(findCueIndex(CUES, 0)).toBe(0);
    expect(findCueIndex(CUES, 1200)).toBe(0);
  });

  it("边界值归属后一句，不是前一句", () => {
    // 2500 正好是第二句起点 —— 归 1，否则高亮会慢半拍
    expect(findCueIndex(CUES, 2500)).toBe(1);
    expect(findCueIndex(CUES, 5000)).toBe(2);
  });

  it("超出末句时间仍停在末句", () => {
    expect(findCueIndex(CUES, 999999)).toBe(2);
  });

  it("负时间返回 -1", () => {
    expect(findCueIndex(CUES, -1)).toBe(-1);
  });

  it("大数组上结果与线性扫描一致", () => {
    // 二分实现最容易在中间某处偏一位，用线性扫描做交叉验证
    const many: AudioCue[] = Array.from({ length: 500 }, (_, i) => cue(i * 1000, i * 10, i * 10 + 10));
    const linear = (t: number) => {
      let hit = -1;
      for (let i = 0; i < many.length; i += 1) if (many[i].time_ms <= t) hit = i;
      return hit;
    };
    for (const t of [0, 1, 999, 1000, 250_500, 499_000, 499_999, 1_000_000]) {
      expect(findCueIndex(many, t)).toBe(linear(t));
    }
  });
});
```

- [ ] **Step 2: 跑测试，确认它是红的**

```bash
cd frontend && npx vitest run src/audio/cues.test.ts
```

预期：`Failed to resolve import "./cues"` —— 全部 FAIL。

- [ ] **Step 3: 实现 `frontend/src/audio/cues.ts`**

```typescript
import type { AudioCue } from "../api/client";

/**
 * 当前播放时间落在第几个 cue。早于首个 cue（含负数）与空数组返回 -1。
 *
 * 二分查找：一卷约 300 个 cue，播放中每秒调用数次，线性扫描也够快 ——
 * 但 timeupdate 在部分浏览器可达 60Hz，且将来长卷可能上千 cue，
 * 二分是稳妥的默认。
 *
 * 边界语义：time_ms 恰等于某 cue 起点时归该 cue（而非前一个），
 * 否则高亮会比声音慢一拍。
 */
export function findCueIndex(cues: AudioCue[], timeMs: number): number {
  let lo = 0;
  let hi = cues.length - 1;
  let hit = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (cues[mid].time_ms <= timeMs) {
      hit = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return hit;
}
```

- [ ] **Step 4: 跑测试，确认全绿**

```bash
cd frontend && npx vitest run src/audio/cues.test.ts
```

预期：`6 passed`

- [ ] **Step 5: 变异检验**

把 `if (cues[mid].time_ms <= timeMs)` 的 `<=` 改成 `<`，重跑：

预期 `边界值归属后一句` FAIL。确认后改回。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/audio/cues.ts frontend/src/audio/cues.test.ts
git commit -m "feat(audio): cue 二分查找，边界归后一句"
```

---

## Task 12: 播放器 Provider（layout 层）

**Files:**
- Create: `frontend/src/audio/AudioPlayerProvider.tsx`
- Create: `frontend/src/audio/useAudioPlayback.ts`
- Modify: `frontend/src/components/Layout.tsx`（第 383 行 `<Outlet />` 处）

**Interfaces:**
- Consumes: `findCueIndex`（Task 11）、`getJuanAudio` / `TextAudioResponse`（Task 10）
- Produces:
  - `<AudioPlayerProvider>{children}</AudioPlayerProvider>`
  - `useAudioPlayer(): AudioPlayerState`，其中
    ```typescript
    interface AudioPlayerState {
      track: { textId: number; juanNum: number; title: string; audio: TextAudioResponse } | null;
      playing: boolean;
      cueIndex: number;
      rate: number;
      play(t: { textId: number; juanNum: number; title: string; audio: TextAudioResponse }): void;
      toggle(): void;
      seek(ms: number): void;
      setRate(r: number): void;
      stop(): void;
    }
    ```

**为什么必须在 layout 层：** 跨卷连续播放是「听经」场景的刚需，而切卷会重挂载 `TextReaderPage`。`<audio>` 住在页面组件里，一切卷就断。

- [ ] **Step 1: 实现 hook 契约 `frontend/src/audio/useAudioPlayback.ts`**

```typescript
import { createContext, useContext } from "react";
import type { TextAudioResponse } from "../api/client";

export interface AudioTrack {
  textId: number;
  juanNum: number;
  /** 经名 + 卷次，用于锁屏 MediaSession 与播放条标题 */
  title: string;
  audio: TextAudioResponse;
}

export interface AudioPlayerState {
  track: AudioTrack | null;
  playing: boolean;
  /** 当前 cue 下标，-1 表示尚未进入任何句子 */
  cueIndex: number;
  rate: number;
  play(track: AudioTrack): void;
  toggle(): void;
  seek(ms: number): void;
  setRate(rate: number): void;
  stop(): void;
}

export const AudioPlayerContext = createContext<AudioPlayerState | null>(null);

/**
 * 读诵播放器状态。Provider 挂在 Layout 层（不在阅读页），故切卷不中断播放。
 * 未包在 Provider 内时返回一个惰性空态，调用方无需判空。
 */
export function useAudioPlayer(): AudioPlayerState {
  const ctx = useContext(AudioPlayerContext);
  if (ctx) return ctx;
  return {
    track: null,
    playing: false,
    cueIndex: -1,
    rate: 1,
    play: () => {},
    toggle: () => {},
    seek: () => {},
    setRate: () => {},
    stop: () => {},
  };
}
```

- [ ] **Step 2: 实现 Provider `frontend/src/audio/AudioPlayerProvider.tsx`**

```tsx
import { useState, useRef, useEffect, useCallback, useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { findCueIndex } from "./cues";
import { AudioPlayerContext, type AudioPlayerState, type AudioTrack } from "./useAudioPlayback";

/**
 * 读诵播放器。挂在 Layout 层，持有全站唯一的 <audio>。
 *
 * ⚠️ 不要把它下放到阅读页：切卷会重挂载页面组件，跨卷连续播放会断 ——
 *    而连续播放正是「听经」场景的刚需。
 *
 * 刻意不在这里渲染 PlayerBar —— Provider 只管状态，UI 由 Layout 并列挂载，
 * 两者互不 import，各自可独立测试。
 */
export default function AudioPlayerProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [track, setTrack] = useState<AudioTrack | null>(null);
  const [playing, setPlaying] = useState(false);
  const [cueIndex, setCueIndex] = useState(-1);
  const [rate, setRateState] = useState(1);

  if (audioRef.current === null && typeof Audio !== "undefined") {
    audioRef.current = new Audio();
  }

  const play = useCallback((next: AudioTrack) => {
    const el = audioRef.current;
    if (!el) return;
    const sameTrack = el.dataset.src === next.audio.url;
    if (!sameTrack) {
      el.src = next.audio.url;
      el.dataset.src = next.audio.url;
      setCueIndex(-1);
    }
    setTrack(next);
    // iOS 要求播放必须由用户手势同步触发 —— 本函数只在按钮 onClick 里调用。
    void el.play().catch(() => setPlaying(false));
  }, []);

  const toggle = useCallback(() => {
    const el = audioRef.current;
    if (!el || !track) return;
    if (el.paused) void el.play().catch(() => setPlaying(false));
    else el.pause();
  }, [track]);

  const seek = useCallback((ms: number) => {
    const el = audioRef.current;
    if (el) el.currentTime = ms / 1000;
  }, []);

  const setRate = useCallback((r: number) => {
    const el = audioRef.current;
    if (el) el.playbackRate = r;
    setRateState(r);
  }, []);

  const stop = useCallback(() => {
    const el = audioRef.current;
    if (el) {
      el.pause();
      el.removeAttribute("src");
      delete el.dataset.src;
      el.load();
    }
    setTrack(null);
    setPlaying(false);
    setCueIndex(-1);
  }, []);

  // 播放状态与 cue 跟随
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onTime = () => {
      if (!track) return;
      const idx = findCueIndex(track.audio.cues, Math.round(el.currentTime * 1000));
      setCueIndex((prev) => (prev === idx ? prev : idx));
    };
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("timeupdate", onTime);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("timeupdate", onTime);
    };
  }, [track]);

  // 锁屏 / 通知栏控制。artist 固定标注为「AI 合成朗读」——
  // 锁屏也是面向用户的位置，同样不得让人以为是法师读诵。
  useEffect(() => {
    if (!("mediaSession" in navigator) || !track) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: t("reader.audio.synthetic_label"),
      album: t("reader.audio.album"),
    });
    navigator.mediaSession.setActionHandler("play", () => toggle());
    navigator.mediaSession.setActionHandler("pause", () => toggle());
    return () => {
      navigator.mediaSession.setActionHandler("play", null);
      navigator.mediaSession.setActionHandler("pause", null);
    };
  }, [track, toggle, t]);

  const value = useMemo<AudioPlayerState>(
    () => ({ track, playing, cueIndex, rate, play, toggle, seek, setRate, stop }),
    [track, playing, cueIndex, rate, play, toggle, seek, setRate, stop],
  );

  return <AudioPlayerContext.Provider value={value}>{children}</AudioPlayerContext.Provider>;
}
```

- [ ] **Step 3: 挂到 Layout —— 修改 `frontend/src/components/Layout.tsx`**

顶部 import 区加入：

```typescript
import AudioPlayerProvider from "../audio/AudioPlayerProvider";
```

把第 383 行的 `<Outlet />` 改成：

```tsx
<AudioPlayerProvider>
  <Outlet />
</AudioPlayerProvider>
```

- [ ] **Step 4: 类型检查 + lint**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm test
```

预期：均无输出/无 warning，既有测试全绿。

> 本任务自成闭环 —— Provider 不 import `PlayerBar`，所以不依赖尚未创建的 Task 13。此时读诵功能尚无 UI 入口，属正常中间态。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/audio/AudioPlayerProvider.tsx frontend/src/audio/useAudioPlayback.ts \
        frontend/src/components/Layout.tsx
git commit -m "feat(audio): 播放器 Provider 挂到 Layout 层，跨卷切换不中断"
```

---

## Task 13: 播放条 UI 与文案

**Files:**
- Create: `frontend/src/audio/PlayerBar.tsx`
- Test: `frontend/src/audio/PlayerBar.test.tsx`
- Modify: `frontend/src/styles/reader.css`
- Modify: `frontend/src/components/Layout.tsx`（把 `<PlayerBar />` 并列挂进 Provider）
- Modify: `frontend/public/locales/zh/translation.json`
- Modify: `frontend/public/locales/zh-Hant/translation.json`
- Modify: `frontend/public/locales/en/translation.json`

**Interfaces:**
- Consumes: `useAudioPlayer()`（Task 12）
- Produces: `<PlayerBar />` 默认导出

- [x] **Step 1: 加三份 locale 文案** —— ✅ 已完成（commit 见下）

⚠️ **本仓 i18n 用扁平点号键，不是嵌套对象**（实测：1,525 个键，100% 含点号，
零嵌套对象）。所以是加 `"reader.audio.button": "读诵"`，**不是**在 `reader`
对象里加 `"audio": {...}` —— 后者会生成 `reader.audio` 这个 i18next 取不到的形状。

三份 locale 各加 10 条 `reader.audio.*`：`button` / `tooltip` / `unavailable` /
`synthetic_label` / `album` / `play` / `pause` / `close` / `speed` /
`model_disclaimer`。插入位置在最后一条 `reader.parallel.*` 之后（本文件按功能
分组、非字母序，不要重排）。

⚠️ 其中 `reader.audio.model_disclaimer` 是**许可证义务**，不是可选文案 ——
见 §「许可证义务」与 `backend/scripts/audio/README.md`。

⚠️ 插值占位符用 `{{n}}` 一类短名，**不要**用 `{{count}}`（i18next 会把它当复数控制键）。

- [ ] **Step 2: 写下会红的测试 `frontend/src/audio/PlayerBar.test.tsx`**

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import PlayerBar from "./PlayerBar";
import { AudioPlayerContext, type AudioPlayerState } from "./useAudioPlayback";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars?.title ? `${key}:${vars.title}` : key,
  }),
}));

function renderWith(overrides: Partial<AudioPlayerState> = {}) {
  const state: AudioPlayerState = {
    track: {
      textId: 10036,
      juanNum: 1,
      title: "金剛般若波羅蜜經 第1卷",
      audio: {
        text_id: 10036,
        juan_num: 1,
        url: "/audio/10036/1-a1b2c3d4.mp3",
        voice_id: "zh-CN-YunzeNeural",
        engine: "azure",
        duration_ms: 2_100_000,
        cues: [],
      },
    },
    playing: false,
    cueIndex: -1,
    rate: 1,
    play: vi.fn(),
    toggle: vi.fn(),
    seek: vi.fn(),
    setRate: vi.fn(),
    stop: vi.fn(),
    ...overrides,
  };
  render(
    <AudioPlayerContext.Provider value={state}>
      <PlayerBar />
    </AudioPlayerContext.Provider>,
  );
  return state;
}

describe("PlayerBar", () => {
  it("必须显示「AI 合成朗读」标注", () => {
    // 诚信约束：不得让用户以为是法师读诵。这条不是样式偏好，是产品底线。
    renderWith();
    expect(screen.getByText("reader.audio.synthetic_label")).toBeTruthy();
  });

  it("必须渲染模型许可证声明", () => {
    // ⚖️ bilibili 模型使用许可协议 4.1 a) 要求发布页面作此声明。
    // 这不是文案偏好 —— 删掉它等于违约，所以用测试钉死。
    renderWith();
    expect(
      screen.getByLabelText("reader.audio.model_disclaimer"),
    ).toBeTruthy();
  });

  it("显示当前曲目标题", () => {
    renderWith();
    expect(screen.getByText(/金剛般若波羅蜜經 第1卷/)).toBeTruthy();
  });

  it("无 track 时不渲染", () => {
    const { container } = render(
      <AudioPlayerContext.Provider
        value={{
          track: null,
          playing: false,
          cueIndex: -1,
          rate: 1,
          play: vi.fn(),
          toggle: vi.fn(),
          seek: vi.fn(),
          setRate: vi.fn(),
          stop: vi.fn(),
        }}
      >
        <PlayerBar />
      </AudioPlayerContext.Provider>,
    );
    expect(container.textContent).toBe("");
  });
});
```

- [ ] **Step 3: 跑测试，确认它是红的**

```bash
cd frontend && npx vitest run src/audio/PlayerBar.test.tsx
```

预期：`Failed to resolve import "./PlayerBar"` —— FAIL。

- [ ] **Step 4: 实现 `frontend/src/audio/PlayerBar.tsx`**

```tsx
import { Button, Select, Slider, Tooltip } from "antd";
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  CloseOutlined,
  SoundOutlined,
} from "@ant-design/icons";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";

import { useAudioPlayer } from "./useAudioPlayback";

const RATES = [0.75, 1, 1.25, 1.5];

function fmt(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 底部读诵播放条。只在有曲目时渲染；由 AudioPlayerProvider 挂载。 */
export default function PlayerBar() {
  const { t } = useTranslation();
  const { track, playing, rate, toggle, seek, setRate, stop } = useAudioPlayer();
  const [pos, setPos] = useState(0);

  // 进度条自走。不订阅 timeupdate 是为了不让整条 bar 跟着 60Hz 重渲染。
  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setPos((p) => p + 1000 * rate), 1000);
    return () => window.clearInterval(id);
  }, [playing, rate]);

  if (!track) return null;

  return (
    <div className="reader-audio-bar" role="region" aria-label={t("reader.audio.button")}>
      <Button
        type="text"
        icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
        onClick={toggle}
        aria-label={playing ? t("reader.audio.pause") : t("reader.audio.play")}
      />
      <div className="reader-audio-meta">
        <div className="reader-audio-title">{track.title}</div>
        <div className="reader-audio-note">
          {/* 诚信标注：不得让用户以为是法师读诵 */}
          <SoundOutlined /> {t("reader.audio.synthetic_label")}
          {/* ⚖️ 许可证义务 4.1 a) —— 必须真实渲染，不是可选文案。
              用 Tooltip 承载全文以免占满播放条；aria-label 让文案进 DOM，
              测试可断言其存在。 */}
          <Tooltip title={t("reader.audio.model_disclaimer")}>
            <span
              className="reader-audio-license"
              aria-label={t("reader.audio.model_disclaimer")}
            >
              ⓘ
            </span>
          </Tooltip>
        </div>
      </div>
      <Slider
        className="reader-audio-progress"
        min={0}
        max={track.audio.duration_ms}
        value={Math.min(pos, track.audio.duration_ms)}
        tooltip={{ formatter: (v) => fmt(Number(v ?? 0)) }}
        onChange={(v) => {
          setPos(v);
          seek(v);
        }}
      />
      <Tooltip title={t("reader.audio.speed")}>
        <Select
          size="small"
          value={rate}
          onChange={setRate}
          options={RATES.map((r) => ({ value: r, label: `${r}×` }))}
          style={{ width: 76 }}
        />
      </Tooltip>
      <Button
        type="text"
        icon={<CloseOutlined />}
        onClick={stop}
        aria-label={t("reader.audio.close")}
      />
    </div>
  );
}
```

- [ ] **Step 5: 加样式**

追加到 **`frontend/src/styles/reader.css`** 末尾（`.cbeta-line-flash` 已在该文件第 800 行，新样式紧挨它的家族）：

```css
/* ── 读诵播放条 ─────────────────────────────────────────── */
.reader-audio-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 900;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--fj-card-bg);
  border-top: 1px solid var(--fj-border);
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.06);
}
.reader-audio-meta { min-width: 0; flex: 0 1 260px; }
.reader-audio-title {
  font-size: 13px;
  color: var(--fj-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.reader-audio-note {
  font-size: 11px;
  color: var(--fj-ink-muted, #999);
}
/* 许可证声明入口（bilibili 模型协议 4.1 a) 要求）—— 低调但必须存在 */
.reader-audio-license {
  margin-left: 6px;
  cursor: help;
  opacity: 0.7;
}
.reader-audio-progress { flex: 1 1 auto; margin: 0 8px; }

/* 正在读诵的那一行 —— 与 .cbeta-line-flash 同色系（reader.css:804），
   区别只在 flash 是 2.2s 动画后归零，这里是持续态。 */
.cbeta-line-playing {
  background: rgba(184, 134, 11, 0.18);
  border-radius: 3px;
  transition: background 240ms ease;
}

@media (max-width: 640px) {
  .reader-audio-progress, .reader-audio-meta { display: none; }
}
```

⚠️ 本仓 CSS 变量前缀是 **`--fj-`**（不是 `--fojin-`）：`--fj-card-bg` / `--fj-border` / `--fj-ink` / `--fj-ink-muted` / `--fj-accent`。高亮色刻意复用 `.cbeta-line-flash` 的 `rgba(184, 134, 11, 0.18)`，**不要新造硬编码色值**（仓库里已有 71 处硬编码 `#9a8e7a` 的历史包袱，别再添）。

- [ ] **Step 6: 跑测试，确认全绿**

```bash
cd frontend && npx vitest run src/audio/PlayerBar.test.tsx
```

预期：`3 passed`

- [ ] **Step 7: 变异检验**

把 `PlayerBar.tsx` 里 `{t("reader.audio.synthetic_label")}` 那一行整块删掉，重跑：

预期 `必须显示「AI 合成朗读」标注` FAIL。确认后改回。

- [ ] **Step 7b: 挂进 Layout**

修改 `frontend/src/components/Layout.tsx` —— Task 12 已把 `<Outlet />` 包进 Provider，这里在其内并列加上播放条：

```tsx
<AudioPlayerProvider>
  <Outlet />
  <PlayerBar />
</AudioPlayerProvider>
```

顶部 import 加：

```typescript
import PlayerBar from "../audio/PlayerBar";
```

`PlayerBar` 在无曲目时自身返回 `null`，所以无条件挂载是安全的。

- [ ] **Step 8: 全套前端门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test
```

预期：全部通过，i18n ratchet 无新增硬编码中文。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/audio/PlayerBar.tsx frontend/src/audio/PlayerBar.test.tsx \
        frontend/src/styles/reader.css frontend/src/components/Layout.tsx \
        frontend/public/locales
git commit -m "feat(audio): 底部播放条，「AI 合成朗读」标注有测试兜底"
```

---

## Task 14: 阅读页接入

**Files:**
- Modify: `frontend/src/pages/TextReaderPage.tsx`（顶栏第 838 行附近 + 高亮订阅）

**Interfaces:**
- Consumes: `getJuanAudio`（Task 10）、`useAudioPlayer`（Task 12）
- Produces: 无（终端消费者）

⚠️ 本文件已 1,092 行，**只允许新增下述两处**，不做其他改动。

- [ ] **Step 1: 拉音频（有才显示按钮）**

在既有的 `useQuery` 群组之后（`juanLineAnchors` 那段，约第 645 行）加入：

```typescript
  // 读诵音频：只有预生成过的卷才有，404 是正常态（不重试、不报错）。
  const { data: audioData } = useQuery({
    queryKey: ["juanAudio", textId, juanNum],
    queryFn: () => getJuanAudio(Number(textId), juanNum),
    enabled: !!textId,
    staleTime: 3600000,
    retry: false,
  });
```

并在文件顶部的 `from "../api/client"` import 中加入 `getJuanAudio`。

- [ ] **Step 2: 顶栏加「读诵」按钮**

在第 838 行「跨藏对照」的 `<Tooltip>` 之后插入：

```tsx
          {audioData && (
            <Tooltip title={t("reader.audio.tooltip")}>
              <Button
                size="small"
                type={audioPlayer.track?.textId === Number(textId)
                  && audioPlayer.track?.juanNum === juanNum ? "primary" : "default"}
                icon={<SoundOutlined />}
                onClick={() =>
                  audioPlayer.play({
                    textId: Number(textId),
                    juanNum,
                    title: t("reader.seo.title", {
                      title: content?.title_zh ?? "",
                      n: juanNum,
                    }),
                    audio: audioData,
                  })
                }
              >
                {t("reader.audio.button")}
              </Button>
            </Tooltip>
          )}
```

顶部 import 加：

```typescript
import { SoundOutlined } from "@ant-design/icons";
import { useAudioPlayer } from "../audio/useAudioPlayback";
```

并在组件内取用：

```typescript
  const audioPlayer = useAudioPlayer();
```

- [ ] **Step 3: 高亮跟随 + 自动滚屏**

在既有的 URN 深链 `useEffect`（约第 665 行）之后加入：

```typescript
  // 播到哪，高亮到哪。复用 URN 深链已有的 .cbeta-line 定位机制 ——
  // 那里是瞬时 flash，这里是持续态。
  //
  // ⚠️ 自动滚屏必须在真机验收：behavior:"smooth" 在 CDP 驱动的浏览器里
  //    完全不推进（疑 rAF 节流），CDP 下看不到问题不代表生产没问题。
  useEffect(() => {
    const player = audioPlayer;
    if (!audioData || player.cueIndex < 0) return;
    if (player.track?.textId !== Number(textId) || player.track?.juanNum !== juanNum) return;

    const cue = audioData.cues[player.cueIndex];
    if (!cue) return;

    const root = readerContentRef.current;
    if (!root) return;

    // cue 的 char_start 是 code-point 偏移，与 lineAnchors 同坐标系；
    // 取「不晚于 cue 起点」的最后一个行锚，即该句所在的 CBETA 行。
    const raw = content?.content;
    if (!raw) return;
    const m = cpToU16Map(raw);
    const startU16 = cue.char_start < m.length ? m[cue.char_start] : m[m.length - 1];
    let target: LineAnchorConv | null = null;
    for (const a of lineAnchors) {
      if (a.off <= startU16) target = a;
      else break;
    }
    if (!target) return;

    const prev = root.querySelectorAll<HTMLElement>(".cbeta-line-playing");
    prev.forEach((el) => el.classList.remove("cbeta-line-playing"));

    const el = root.querySelector<HTMLElement>(
      `.cbeta-line[data-ref="${CSS.escape(target.ref)}"]`,
    );
    if (!el) return;
    const line = el.closest("p") ?? el;
    line.classList.add("cbeta-line-playing");
    line.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [audioPlayer, audioData, content, lineAnchors, textId, juanNum]);
```

⚠️ `cpToU16Map` 与 `LineAnchorConv` 已在本文件内定义（`LineAnchorConv` 见第 57 行），无需新增 import。

- [ ] **Step 4: 全套前端门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test
```

预期：全部通过。

> ⚠️ 若 `npm test` 全绿但退出码非 0，检查是否有测试文件缺 mock 导致整支 exit 1 —— 本仓 `ChatPage.test` 有过此坑。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/TextReaderPage.tsx
git commit -m "feat(audio): 阅读页读诵入口与逐句高亮跟随"
```

---

# Phase F — 部署与验收

## Task 15: 静态直出与真机验收

**Files:**
- Modify: `deploy/host-nginx/fojin.conf`
- Create: `docs/superpowers/plans/2026-08-11-reader-audio-acceptance.md`（验收记录）

**Interfaces:**
- Consumes: Task 7 的 mp3 产物、Task 8 已入库的元数据
- Produces: 生产可访问的 `/audio/**`

**为什么走宿主机 nginx 而不是前端容器：** 前端容器的静态内容在构建时烤进镜像，没有卷挂载；而音频既不能进 git（`--maxkb=500`）也不该进镜像（一部经就十几 MB）。宿主机目录 + host nginx 直出是唯一干净的路。

- [ ] **Step 1: 加 nginx location**

在 `deploy/host-nginx/fojin.conf` 的主站 server 块内、`location / { proxy_pass http://127.0.0.1:3000; }` **之前**加入：

```nginx
    # 读诵音频 —— 宿主机静态目录直出，不经容器也不经后端。
    # 文件名带 content_hash 前 8 位，重生成即新 URL，故可长缓存且永不需要 purge。
    location /audio/ {
        alias /srv/fojin/audio/;
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        add_header Accept-Ranges bytes always;
        access_log off;
        try_files $uri =404;
    }
```

⚠️ 位置很重要：`location /audio/` 是前缀匹配，必须在 `location /` 之前出现才能优先命中（nginx 前缀匹配取最长，故其实顺序不影响匹配，但放前面便于阅读）。

⚠️ **不要**给它加 `try_files $uri $uri/ /index.html` 之类的 SPA 回退 —— 那会让缺失的音频返回 200 + HTML，前端 `<audio>` 会静默不播且无报错。`=404` 是刻意的。

- [ ] **Step 2: 本机用同版本 nginx 做 A/B（不动生产）**

```bash
docker run --rm -v "$PWD/deploy/host-nginx:/etc/nginx/conf.d:ro" nginx:alpine nginx -t
```

预期：`syntax is ok` / `test is successful`。

> 若本机 Docker 不可用，退回用生产宿主机跑一次性容器做同样的 `nginx -t`，**不要**直接 reload 未验证的配置。

- [ ] **Step 3: 上传音频到生产宿主机**

```bash
ssh -o KexAlgorithms=curve25519-sha256 admin@100.67.232.7 'mkdir -p /srv/fojin/audio'
rsync -av -e 'ssh -o KexAlgorithms=curve25519-sha256' \
    backend/out/audio/10036/ admin@100.67.232.7:/srv/fojin/audio/10036/
```

⚠️ 只传 `*.mp3`，不必传 `.cues.json`（那是入库用的，已在 Task 8 写进数据库）。也**不要**传 `*.parts/` 目录（逐句分片，几百个小文件）：

```bash
rsync -av --include='*/' --include='*.mp3' --exclude='*' --prune-empty-dirs \
    -e 'ssh -o KexAlgorithms=curve25519-sha256' \
    backend/out/audio/ admin@100.67.232.7:/srv/fojin/audio/
```

⚠️ **不要**把音频放进 `/home/admin/fojin/` —— 那是生产仓库工作区，是 bind mount 进容器的，写进去会弄坏下次 `git pull` 部署。

- [ ] **Step 4: reload nginx 并验证**

```bash
ssh -o KexAlgorithms=curve25519-sha256 admin@100.67.232.7 \
    'sudo nginx -t && sudo systemctl reload nginx'

curl -sI https://fojin.app/audio/10036/1-<hash8>.mp3 | head -8
```

预期：`HTTP/2 200`、`content-type: audio/mpeg`、`accept-ranges: bytes`、`cache-control: public, max-age=31536000, immutable`。

再验一个不存在的路径必须 404 而不是 HTML：

```bash
curl -sI https://fojin.app/audio/nope.mp3 | head -3
```
预期：`HTTP/2 404`。

- [ ] **Step 5: 真机验收清单**

以下五条**必须在真实浏览器/真机完成**，CDP 与桌面模拟都验不出：

| # | 项目 | 怎么验 | 为什么 CDP 验不出 |
|---|---|---|---|
| 1 | iOS 锁屏播放 | iPhone Safari 打开 `/texts/10036/read?juan=1` → 点「读诵」→ 按电源键锁屏 → 确认继续播放 | `<audio>` 在 iOS 的后台行为特殊，需用户手势启动 |
| 2 | iOS 锁屏控制条 | 锁屏界面应显示标题与**「AI 合成朗读」**，播放/暂停可用 | MediaSession 只在真机锁屏可见 |
| 3 | 切后台不断 | 播放中切到别的 App 一分钟，切回确认仍在播且进度前进 | 同上 |
| 4 | 自动滚屏 | 播放中确认页面跟着高亮行滚动 | `behavior:"smooth"` 在 CDP 里完全不推进（疑 rAF 节流） |
| 5 | PWA 旧壳 | 部署后首访若「没生效」，先强制刷新/清 Service Worker 再判 | 首访拿到的是旧 SW 壳 |

把结果写进 `docs/superpowers/plans/2026-08-11-reader-audio-acceptance.md`，逐条记「通过 / 不通过 + 现象」。

- [ ] **Step 6: 提交**

```bash
git add deploy/host-nginx/fojin.conf docs/superpowers/plans/2026-08-11-reader-audio-acceptance.md
git commit -m "feat(audio): 宿主机 nginx 静态直出 /audio/，附真机验收记录"
```

---

## Task 16: 下游用户约束条款（许可证义务 3.4 a）

**Files:**
- Create: `frontend/src/pages/TermsPage.tsx`
- Modify: `frontend/src/App.tsx`（加 `/terms` 路由）
- Modify: `frontend/src/components/Layout.tsx`（页脚加链接）
- Modify: `frontend/public/locales/{zh,zh-Hant,en}/translation.json`
- Modify: `frontend/src/seo/staticPages.json`
- Modify: `deploy/host-nginx/fojin.conf`

**Interfaces:**
- Consumes: 无
- Produces: `/terms` 路由

**为什么需要**：bilibili 模型使用许可协议 **3.4 a)** 要求「确保下游用户……同样遵守本协议，并通过合适的协议或条款对下游用户进行约束。**若下游用户违反本协议规定，您需承担相应责任**」。合成音频按协议 1.5 属衍生品，站点访客即下游用户。**本仓当前完全没有条款页**（实测：`frontend/src/pages/` 无 terms/legal/privacy，`App.tsx` 无相关路由）。

⚠️ **本任务只搭骨架 + 写模型许可条款那一节**。使用条款的其余内容（免责、隐私、
知识产权等）是法律文书，应由站点所有者撰写，实施者**不要代写**，留 TODO 注释即可。

- [ ] **Step 1: 加三份 locale 文案**

扁平点号键，插在 `footer.` 相关键附近：

```json
"terms.title": "使用条款",
"terms.model_license.heading": "合成音频与模型许可",
"terms.model_license.body": "本站「在线读诵」功能的音频由 bilibili IndexTTS-2.5 模型合成。该音频属该模型的衍生品，受《bilibili 模型使用许可协议》约束。您收听、下载或以其他方式使用本站合成音频，即表示您同意遵守该协议。协议全文见模型发布页 https://github.com/index-tts/index-tts 。本站对该模型的使用及所作改动与原模型权利人无关，原始权利人对此不背书、不担保、不承担责任。",
"footer.terms": "使用条款"
```

（繁体与英文版同步，文意一致即可。）

- [ ] **Step 2: 建页面 `frontend/src/pages/TermsPage.tsx`**

```tsx
import { Typography } from "antd";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";

const { Title, Paragraph } = Typography;

/**
 * 使用条款。
 *
 * ⚖️ 当前只有「合成音频与模型许可」一节 —— 它是 bilibili 模型使用许可协议
 * 3.4 a) 的硬性要求（须以条款约束下游用户，否则违约责任在本站）。
 *
 * TODO(站点所有者)：其余条款（服务免责、隐私、知识产权、账号规则等）
 * 属法律文书，需由所有者撰写，不应由实施者代拟。
 */
export default function TermsPage() {
  const { t } = useTranslation();
  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "24px 16px" }}>
      <Helmet>
        <title>{t("terms.title")}</title>
      </Helmet>
      <Title level={2}>{t("terms.title")}</Title>
      <Title level={4}>{t("terms.model_license.heading")}</Title>
      <Paragraph>{t("terms.model_license.body")}</Paragraph>
    </div>
  );
}
```

- [ ] **Step 3: 加路由（`frontend/src/App.tsx`）**

在 `<Route element={<Layout />}>` 内加：

```tsx
<Route path="/terms" element={<TermsPage />} />
```

并在顶部 import。

- [ ] **Step 4: 页脚加链接（`frontend/src/components/Layout.tsx`）**

在 `{t("footer.copyright")}` 之后加：

```tsx
{" · "}
<Link to="/terms">{t("footer.terms")}</Link>
```

（`Link` 从 `react-router` import；页脚已有的 `Footer` 块见第 385 行附近。）

- [ ] **Step 5: SEO 静态页 + nginx location**

⚠️ 本仓有个反复踩的坑：**每加一条 SEO shell 就要给该路由加一次 nginx 显式
`location`**，否则 `try_files` 撞上真实目录会产生 301。在 `staticPages.json`
加 `/terms` 条目的同时，必须在 `deploy/host-nginx/fojin.conf` 加：

```nginx
    location = /terms { proxy_pass http://127.0.0.1:3000; }
```

- [ ] **Step 6: 全套前端门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test
```

- [ ] **Step 7: 提交**

```bash
git add frontend/src/pages/TermsPage.tsx frontend/src/App.tsx \
        frontend/src/components/Layout.tsx frontend/public/locales \
        frontend/src/seo/staticPages.json deploy/host-nginx/fojin.conf
git commit -m "feat(legal): 使用条款页 —— 满足模型许可证的下游约束义务"
```

---


## 收尾

- [ ] 全量门禁：`cd backend && ruff check app/ && pytest tests/ -q`；`cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test`
- [ ] 开 PR 到 `master`，标题 `feat(reader): 在线读诵 —— 听经模式（离线预生成）`
- [ ] PR 描述中附上：音色试听结论、whisper-audit 回验的真错读数（应为 0）、真机验收五条的结果
- [ ] 合并后确认 CD 自动部署完成，再跑一次 `curl -sI https://fojin.app/audio/...` 确认线上可取

---

## 未决事项（不阻塞实施，但应在扩量前解决）

1. **阅读页真实使用量未知。** 板块使用排名中 chat 715 / dict 428 / kg 219 / parallel 17，阅读页不在该统计内。**扩到 50 部之前查一次 Umami**，若阅读页月活极低，这个功能是在给空房间装音响。
2. **公开流通授权的真人读诵未核实。** 一部真人读诵的金剛經价值大于五十部合成音；`engine` 字段与整套表结构对真人录音同样适用，拿到即可替换而不必重构。
3. **Azure `<phoneme alphabet="sapi">` 对 zh-CN 的支持度** —— Task 3 Step 5 必须验通，否则整个读音方案不成立。
4. **清单具体篇目未定**（~50 部常诵经典的确切列表），扩量前需人工敲定。
5. **`lexicon.tsv` 全部条目为 `seed` 状态**，需人工（最好请法师）审定后逐条改 `confirmed`。其中「南無」的 ná/nā 之别已在词典备注中标出。
