---
name: stvideo
description: 从用户的一句话需求生成带解说与配音的完整讲解视频。流程：用户简述内容 -> 联网搜集资料并产出完整视频文案 -> 用户审阅确认 -> 生成讲解HTML与口播文稿(自动去AI味) -> 用户审阅确认(可改文稿文本文件) -> edge-tts配音、字幕叠加、录屏合成成片。当用户要求"做讲解视频/生成视频/把XX做成视频/视频生成/讲解动画/口播视频"时使用。
version: 1.1.1
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - AskUserQuestion
  - WebSearch
  - WebFetch
  - Glob
  - Grep
---

# stvideo — 讲解视频生成 Skill

把"一句话需求"变成一支带解说、配音、字幕的讲解视频（默认横屏 16:9，可切竖屏 9:16）。HTML 幻灯是唯一的真相来源：画面、口播文案、时间轴都从它和它身上的 `data-narration` 派生。

本 skill 集成了：
- **PPT 风格网页生成**：将文案转化为可视化 HTML 幻灯（仿 PPT 轮播，含逐元素入场动画，支持两种视觉模式：默认 PPT 模板 / 平面 UI 流程图模板）。
- **unclecheng-reduce-ai-perception（humanizer）**：去除口播文稿的 AI 味，让配音更自然。
- **edge-tts 配音与视频合成**：TTS 配音 → 字幕生成 → Playwright 录屏 → 字幕叠加 → 混流成片。

## 总流程

```
需求(一句话) -> ① 联网调研 -> script.md(完整文案) -> 用户确认 -> ② 生成 index.html + narration.{txt,json,md}  (口播文稿自动去AI味) -> 用户确认(可改 narration.txt) -> ③ 渲染：edge-tts 配音 -> build_srt -> 录屏 -> 字幕叠加 -> 混音 -> 成片 final/<slug>.mp4
```

**人工确认点**（必须停下来等用户）：①文案、②HTML+文稿、③渲染参数**与字幕字体**（字体必须问，不能自动下载）。渲染前只允许因为用户改了 `narration.txt` 而重跑，不要偷偷改写已确认口播词。

---

## 第 ① 步 — 需求澄清 + 联网调研，产出完整文案

不要急着写稿。先和用户对齐：主题、目标受众、时长/页数倾向、语气（科普/种草/硬核）。然后**联网搜集资料**：

- 用 `WebSearch` / `WebFetch` 获取该主题的权威、最新信息（定义、关键数据、案例、常见误解）。
- 把事实沉淀成一份结构化的**视频文案** `script.md`，而不是直接写口播。

`script.md` 结构（先写清"讲什么"，第 ② 步再变成"怎么讲"）：

```markdown
# <视频标题>
- 一句话定位：这条视频解决什么问题 / 给观众什么
- 目标受众：
- 时长目标：约 N 秒（建议 8 页 ≈ 90–110s，一页一个点）

## 页面规划
1. 钩子：用反常识/痛点开场
2. 背景：为什么重要
3. 核心机制/方法一
4. 核心机制/方法二
5. 案例/数据
6. 常见误区
7. 对比/总结
8. 收尾 + 行动建议
```

每一页写清**要点与要用的素材**（数据、引用来源），但口播原句留到第 ② 步生成。

**→ 把 `script.md` 交给用户审阅，确认后再进入第 ② 步。**

---

## 第 ② 步 — 文案 → 讲解 HTML + 口播文稿（自动去AI味）

目标：从 `script.md` 产出
| 文件 | 作用 | 下游 |
|---|---|---|
| `presentations/<slug>/index.html` | 讲解幻灯（HTML），含 `data-narration` | 录屏 |
| `narration.txt` | **逐页口播稿，每页一段、空行分隔，顺序与 slide 一致** | TTS + 字幕 |
| `narration.json` | 每页 title / narration / duration_sec | 时间轴 |
| `narration.md` | 人读的脚本 + 页/时间表 | 给用户看 |

### 2.1 生成讲解 HTML（严格遵循 science-content-ppt 流程）

本步骤完全按照内置的 **science-content-ppt** 工作流生成讲解 HTML，确保视觉风格、动画、图标都符合视频演示要求。

#### 2.1.1 选择视觉模板

根据文案内容特点，从内置模板中选择最合适的视觉风格（**无需用户指定时由模型自行判断**）。

- **默认 PPT 轮播模板**：优先从 `references/templates/PPT Template-level2/` 目录选择（共 25 个模板），回退到 `references/templates/PPT/` 目录。
- **平面 UI 流程图模板**：从 `references/templates/Animation/` 目录选择（共 14 个模板），适合流程、架构、机制类内容。

**选模板核心依据**（详细参考 `references/templates/PPT Template-level2/SUMMARY.md` 和 `references/templates/Animation/SUMMARY.md`）：

| 内容类型 | PPT 模板推荐 | 平面 UI 模板推荐 |
|---------|-------------|-----------------|
| 对比/辩论类 | 8-1、8-3、6-2 | — |
| 步骤/流程类 | 3-2、6-1、6-3、6-4 | RNN-3、RNN-4、Comprehension |
| 案例/实验类 | 4-2、4-3 | — |
| 警示/危险类 | 5-4、7-3 | The fatal flaw of DNN |
| 轻量/快速 | 3-3、4-1、9-3 | — |
| 默认 | `PPT Template-level2/` 中综合适配的模板 | `Animation/RNN-3.html` |

#### 2.1.2 生成 HTML

使用以下提示词模板，结合 `script.md` 内容，生成完整的 `index.html`：

```
基于下方讲解文案，生成基于纯前端页面单页布局仿 PPT 换页轮播进行直观图形化可视化的介绍。
要求：
1. 加大字号，运用加粗、下划线、斜体、文字颜色、文字背景等强调方式，方便视频演示。
2. 添加每次切换页面时页面中的各个元素依次"缓入"出现的动画效果(细化到每行文字)。
3. 将emoji图标换成平面ui库的图标（如Font Awesome或Lucide图标库）。添加完成后检查页面中是否还有残留的emoji字符，如有则全部替换为对应的ui图标，请不要使用带有人脸的图标，可能会丑。
4. 所有动画元素的 class 名统一使用 .an 或 .anim-item，并在页面底部加入 cloneNode 动画重置逻辑，确保每次切换页面动画都会重新触发。
5. 每页用 <div class="slide" data-duration="秒数" data-narration="该页口播原文"> 标记。
6. 代码量充足（建议 1000 行以上），视觉完整、布局饱满。
7. 支持方向键左右键切换画面，方便用户预览内容。
---
{script.md 的完整内容}
---
```

**生成后必须执行以下检查：**

- **Emoji 检查**：确保页面中无任何 emoji 字符残留，全部替换为 Font Awesome 或 Lucide 图标。
- **动画重置 JS**：检查页面底部是否包含以下代码；若缺失，手动添加（确保在 `</body>` 前）：

```javascript
(function() {
    document.querySelectorAll('.slide').forEach(function(s) {
        s.querySelectorAll('.an, .anim-item, [style*="animation"]').forEach(function(item) {
            var clone = item.cloneNode(true);
            item.parentNode.replaceChild(clone, item);
        });
    });
})();
```

#### 2.1.3 可选：重构为 PPT 模板风格

如果初次生成的 HTML 视觉风格不够理想，可以按选定模板重构：

```
以页面 {模板相对路径} 为模板重构 {输出路径}。
请将当前 HTML 的内容按照指定模板的布局、样式和轮播机制进行重构，保持科普内容不变，优化视觉效果使其更适合视频演示。
```

重构后仍需保留 `.slide` + `data-narration` + `data-duration` 约束，并检查动画重置 JS。

#### 2.1.4 注入录制契约

生成/重构完成后，运行脚本自动注入 `window.deckAPI`、录制模式 CSS 和字幕安全区：

```bash
python3 scripts/inject_deck_api.py presentations/<slug>/index.html --aspect 16:9
```

### 2.2 生成口播文稿并去 AI 味

为每一页写 `data-narration`：**口语化、短句、一到两句/页**，念出来正好对应 `data-duration`。写完后**必须跑一遍"去AI味"**（附录 A 的规则），尤其口语视频最容易出现的：排比三连、emoji 点缀、破折号堆叠、客服式讨好、公式化结尾。去 AI 味只改文字自然度，**不要改事实与数据**。

然后把口播词同步成四个文件：
- `index.html` 各 slide 的 `data-narration`
- `narration.txt`：按页顺序，**每段一页、空行分隔**（这是第 ③ 步 TTS 与字幕的输入，也是给用户改的文件）
- `narration.json`：`{title, language, total_duration_sec, slides:[{index,id,title,narration,duration_sec}]}`
- `narration.md`：人读版，附页/时间表

> `narration.txt` 的"每段一页、空行分隔"是字幕断句的依据（`build_srt.py` 用它确定页间停顿）。顺序、页数、标点必须与 `index.html` 完全一致。

**→ 把 `index.html`（预览）和 `narration.txt`/`narration.md` 交给用户审阅。用户最常改 `narration.txt`——改完以 `narration.txt` 为准，回写 `index.html` 的 `data-narration` 与 `narration.json`，再进第 ③ 步。**

---

## 第 ③ 步 — 渲染成片（edge-tts 配音 + 字幕 + 录屏合成）

机械步骤，由 `scripts/build_video.sh` 串起来。每个子步骤输出存在就跳过，可单步重试。

```bash
S=<skill根目录>/scripts
bash $S/build_video.sh presentations/<slug>            # 默认 edge-tts，无 BGM，横屏 16:9
bash $S/build_video.sh presentations/<slug> --aspect 16:9            # 横屏 16:9
bash $S/build_video.sh presentations/<slug> --voice zh-CN-YunxiNeural --bgm /path/music.mp3
bash $S/build_video.sh presentations/<slug> --only srt,compose        # 只重做字幕/合成
bash $S/build_video.sh presentations/<slug> --from record             # deck 改了，重录
bash $S/build_video.sh presentations/<slug> --force                    # 全量重跑
bash $S/build_video.sh presentations/<slug> --font /path/My.ttf       # 用户选定的字幕字体
python3 $S/tts.py --list                                # 看中文音色
python3 $S/fetch_font.py --list-system                  # 看本机装了哪些中文字体
```

### 字幕字体（必须问用户，绝不自动下载）

**渲染前先停下来，把字体这件事问清楚。** skill 不带字体文件（约 18 MB），也**不允许
在用户不知情时联网下载**——`build_video.sh`、缺字体时会直接以错误退出，不会自作主张。

流程：

1. 先看看机器上有什么：
   ```bash
   python3 $S/fetch_font.py --list-system
   # Noto Sans CJK JP (+9 faces)	/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc	19.5 MB
   # Noto Serif CJK SC	/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc	26.3 MB
   ```
   列出的每一项都通过了中文覆盖检测（能真正画出"中文"，不是只有字形文件名）。
2. 用 **AskUserQuestion** 问用户，把上面列出的字体名作为选项，外加：
   - **用系统的 XXX**（把列表第一项或用户挑的那个作为推荐项，放第一个并标 `(推荐)`）
   - **我自己提供字体**（让用户给路径，用 `--font /path/to/X.ttf` 传下去）
   - **下载霞鹜文楷 LXGWWenKai-Medium**（**必须先说明是 18.5 MB**，用户同意后才加 `--allow-fetch`）
3. 拿到选择后再渲染。

结果按此优先级生效（全程不联网，除非用户选了下载）：

1. `--font /path/to/font.ttf` 或环境变量 `$STVIDEO_FONT`
2. 之前下载过、缓存在 `assets/fonts/` 里的字体
3. 系统已装的中文字体

如果 `--list-system` 一条都没有，说明机器上没中文字体——这时**只能**让用户提供字体路径，
或者明确告知体积后征得同意再下载。

opt-in 下载（用户已同意才用）：
```bash
S=<skill根目录>/scripts
bash $S/build_video.sh presentations/<slug> --allow-fetch        # 下载默认 lxgw-medium
python3 $S/fetch_font.py --download --font lxgw-light            # 细一档的霞鹜文楷
python3 $S/fetch_font.py --url https://…/X.ttf                   # 任意字体
python3 $S/fetch_font.py --list                                  # 可下载预设
```

分步脚本（按需单独跑）：
- `tts.py` — `narration.txt` → `audio/voice.wav`（edge-tts 中文神经音，默认 `zh-CN-XiaoxiaoNeural`）。
- `build_srt.py` — `narration.txt` + 实测音频时长 → `audio/voice.srt`（按字权分配时序，无需 Whisper）。
- `fetch_font.py --list-system` — 列出本机可用中文字体（带家族名、体积），供用户挑选；`--resolve` 只解析路径、**从不联网**；`--download` 属 opt-in。所有候选都过中文覆盖检测，避免 `fc-match` 的拉丁字体兜底。
- `inject_deck_api.py` — 把 `window.deckAPI`、录制模式 CSS、字幕安全区注入到 AI-Animation HTML 上（幂等）。
- `deck_capture.py timeline|video` — 时间轴缩放到真实音频；Playwright 录制动画为 `record/animated_capture.webm`（默认 16:9 横屏 1920×1080，或 `--aspect 9:16`）。
- `render_captions.py` — `voice.srt` → 透明字幕 PNG（**白字 + 2px 黑描边 + 半透明**，字体由用户选定）+ `record/burn_caps.sh`。
- `mix_bgm.sh` — 配音 + 背景乐 → `audio/voice_with_bgm.wav`（默认不放 BGM）。
- `compose.sh` — 对齐音频、烧字幕、混流 → `final/<slug>.mp4`（30fps，默认 16:9 横屏）。

### 字幕规范（硬性）
- 字体：**先问用户**——系统已有的中文字体、用户自备的字体、或（说明 18.5 MB 后经同意）下载霞鹜文楷。经 `--font` 传入。
- 样式：白色填充（alpha≈235，**半透明**）+ **2px 黑色描边**；不加底框（默认 `--box-alpha 0`）。
- 位置：底部安全区（横屏距底 70px / 竖屏 240px）。
- 如需改样式，调 `build_video.sh` 的 `--cap-*` 参数（字体大小/边距/透明度/描边/底框）。

### 收尾 QA
- `ffprobe final/<slug>.mp4`：视频应从 0 开始，默认 1920×1080 / 30fps（或指定竖屏 1080×1920），音视频时长差 ≤ 1 帧。
- 抽查首帧、封面后第一帧、各页切换处、字幕相对底部安全区（横屏 70px / 竖屏 240px）的位置。
- 用户改过 `narration.txt` 后，必须让 SRT/录屏/字幕/成片全部失效重跑，不能复用旧产物。

---

## 环境准备与依赖

### Python 虚拟环境（.venv）

**所有 Python 依赖必须安装在项目内的 `.venv` 虚拟环境中**，避免污染系统 Python 环境。

创建并激活虚拟环境：

```bash
cd <skill根目录>          # 进入 skill 根目录
python3 -m venv .venv     # 创建虚拟环境
source .venv/bin/activate # 激活（Linux/macOS）
# Windows 使用：.venv\Scripts\activate
```

之后所有 `pip install` 和 `python` 命令都在该虚拟环境下执行。

### 依赖安装

```bash
# 激活虚拟环境后执行
pip install edge-tts playwright pillow
python -m playwright install chromium
# 可选：字体精确检测
pip install fonttools
```

### 国内镜像源（可选，但推荐）

如果在中国大陆，下载 Python 包时建议切换到国内镜像源以加速。常用镜像源：

- 清华：`https://pypi.tuna.tsinghua.edu.cn/simple`
- 阿里云：`https://mirrors.aliyun.com/pypi/simple/`
- 中科大：`https://pypi.mirrors.ustc.edu.cn/simple/`

使用方法（临时指定）：

```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple edge-tts playwright pillow
```

或者永久配置（写入 `~/.pip/pip.conf` 或 `~/.config/pip/pip.conf`）：

```ini
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
```

Playwright 浏览器下载也可以使用镜像：

```bash
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright python -m playwright install chromium
```

**注意**：edge-tts 的 TTS 服务仍需要联网到 Microsoft 端点，镜像只加速 Python 包安装。

---

## 依赖
- `ffmpeg` + `ffprobe`（录屏合成、字幕叠加）。
- 配音：`pip install edge-tts`（免费中文神经音，需联网到 Microsoft TTS 端点）。
- 录屏：`pip install playwright` + `python -m playwright install chromium` + `pillow`。
- 字幕渲染需要 `pillow`（PIL）+ 一款中文字体：**由用户指定或系统提供，脚本不会自动下载**
  （`fetch_font.py --list-system` 列出候选供用户选）。
- 可选 `pip install fonttools`：用于精确的 cmap 中文覆盖检测；缺失时退化为 PIL 启发式。
- 全部在 Linux 验证；macOS 同理（去掉 `--bgm synth` 外的限制）。

## 输出布局
```
presentations/<slug>/
  index.html  narration.{txt,json,md}
  audio/   voice.wav  voice.srt  voice_with_bgm.{wav,mp3}
  record/  timeline.json  capture_meta.json  animated_capture.webm  aligned.mp4
           caps/  caps_meta.json  burn_caps.sh  captioned.mp4
  final/   <slug>.mp4
```

---

## 附录 A — 去 AI 味规则（口播文稿必过）

内容见`references/humanizer.md`