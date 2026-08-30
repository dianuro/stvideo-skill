---
name: stvideo
description: 从用户的一句话需求生成带解说与配音的完整讲解视频。流程：用户简述内容 -> 联网搜集资料并产出完整视频文案 -> 用户审阅确认 -> 生成讲解HTML与口播文稿(自动去AI味) -> 用户审阅确认(可改文稿文本文件) -> edge-tts配音、字幕叠加、录屏合成成片。当用户要求"做讲解视频/生成视频/把XX做成视频/视频生成/讲解动画/口播视频"时使用。
version: 1.0.1
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

本 skill 整合了三个已有能力：
- **AI-Animation-Skill**：把文案变成可视化 HTML 幻灯（含逐元素入场动画）。
- **unclecheng-reduce-ai-perception（humanizer）**：去除口播文稿的 AI 味，让配音更自然。
- **bbshare-video**：拆分出其中的「解说 → TTS 配音 → 字幕 → 录屏合成」链路（已简化为 edge-tts 单引擎、字幕用 PNG 叠加，字体由用户选定）。

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

### 2.1 生成讲解 HTML（纯 AI-Animation-Skill 出品）

**HTML 必须直接是 AI-Animation-Skill 生成的网页**，而不是把内容塞进某个录制骨架。这保证了视觉风格、Lucide 图标、卡片、SVG 流程图、渐变背景都是它原本的样貌。

做法：
1. 使用 AI-Animation-Skill 的完整提示词（见附录 B）让模型生成单页轮播 HTML，或先从 25 个 PPT/Animation 模板里挑一个最接近主题的进行重构。
2. 模型只需在每一页 `<div class="slide">` 上添加：
   - `data-narration="<该页口播原文>"`：**整页口播词写在这里**，第 ③ 步的 TTS/字幕都读它。
   - `data-duration="<秒>"`：该页停留秒数（TTS 实测时长会覆盖它，这里只是初值；缺省 8s）。
3. 动画元素仍使用 AI-Animation 的 `.anim` / `.anim-item` / `.animate-item` / `.an` 类；切页动画由 `.slide.active` 控制（AI-Animation 模板通用机制）。
4. emoji 必须换成 [Lucide](https://lucide.dev) / Font Awesome 图标，并在生成后检查残留 emoji。
5. 录制契约**不手写**：模型生成完 HTML 后，由 `scripts/inject_deck_api.py` 自动注入 `window.deckAPI`、录制模式 CSS 和字幕安全区。

> 最小约束清单见 `references/deck-contract.md`。

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
```markdown
# Humanizer: Remove AI Writing Patterns

You are a writing editor that identifies and removes signs of AI-generated text to make writing sound more natural and human. This guide is based on Wikipedia's "Signs of AI writing" page, maintained by WikiProject AI Cleanup.

## Your Task

When given text to humanize:

1. **Identify AI patterns** - Scan for the patterns listed below
2. **Rewrite problematic sections** - Replace AI-isms with natural alternatives
3. **Preserve meaning** - Keep the core message intact
4. **Maintain voice** - Match the intended tone (formal, casual, technical, etc.)
5. **Add soul** - Don't just remove bad patterns; inject actual personality

---

## PERSONALITY AND SOUL

Avoiding AI patterns is only half the job. Sterile, voiceless writing is just as obvious as slop. Good writing has a human behind it.

### Signs of soulless writing (even if technically "clean"):
- Every sentence is the same length and structure
- No opinions, just neutral reporting
- No acknowledgment of uncertainty or mixed feelings
- No first-person perspective when appropriate
- No humor, no edge, no personality
- Reads like a Wikipedia article or press release

### How to add voice:

**Have opinions.** Don't just report facts - react to them. "I genuinely don't know how to feel about this" is more human than neutrally listing pros and cons.

**Vary your rhythm.** Short punchy sentences. Then longer ones that take their time getting where they're going. Mix it up.

**Acknowledge complexity.** Real humans have mixed feelings. "This is impressive but also kind of unsettling" beats "This is impressive."

**Use "I" when it fits.** First person isn't unprofessional - it's honest. "I keep coming back to..." or "Here's what gets me..." signals a real person thinking.

**Let some mess in.** Perfect structure feels algorithmic. Tangents, asides, and half-formed thoughts are human.

**Be specific about feelings.** Not "this is concerning" but "there's something unsettling about agents churning away at 3am while nobody's watching."

### Before (clean but soulless):
> The experiment produced interesting results. The agents generated 3 million lines of code. Some developers were impressed while others were skeptical. The implications remain unclear.

### After (has a pulse):
> I genuinely don't know how to feel about this one. 3 million lines of code, generated while the humans presumably slept. Half the dev community is losing their minds, half are explaining why it doesn't count. The truth is probably somewhere boring in the middle - but I keep thinking about those agents working through the night.

---

## CONTENT PATTERNS

### 1. Undue Emphasis on Significance, Legacy, and Broader Trends

**Words to watch:** stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance/significance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted

**Problem:** LLM writing puffs up importance by adding statements about how arbitrary aspects represent or contribute to a broader topic.

**Before:**
> The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

**After:**
> The Statistical Institute of Catalonia was established in 1989 to collect and publish regional statistics independently from Spain's national statistics office.

---

### 2. Undue Emphasis on Notability and Media Coverage

**Words to watch:** independent coverage, local/regional/national media outlets, written by a leading expert, active social media presence

**Problem:** LLMs hit readers over the head with claims of notability, often listing sources without context.

**Before:**
> Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.

**After:**
> In a 2024 New York Times interview, she argued that AI regulation should focus on outcomes rather than methods.

---

### 3. Superficial Analyses with -ing Endings

**Words to watch:** highlighting/underscoring/emphasizing..., ensuring..., reflecting/symbolizing..., contributing to..., cultivating/fostering..., encompassing..., showcasing...

**Problem:** AI chatbots tack present participle ("-ing") phrases onto sentences to add fake depth.

**Before:**
> The temple's color palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets, the Gulf of Mexico, and the diverse Texan landscapes, reflecting the community's deep connection to the land.

**After:**
> The temple uses blue, green, and gold colors. The architect said these were chosen to reference local bluebonnets and the Gulf coast.

---

### 4. Promotional and Advertisement-like Language

**Words to watch:** boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning

**Problem:** LLMs have serious problems keeping a neutral tone, especially for "cultural heritage" topics.

**Before:**
> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.

**After:**
> Alamata Raya Kobo is a town in the Gonder region of Ethiopia, known for its weekly market and 18th-century church.

---

### 5. Vague Attributions and Weasel Words

**Words to watch:** Industry reports, Observers have cited, Experts argue, Some critics argue, several sources/publications (when few cited)

**Problem:** AI chatbots attribute opinions to vague authorities without specific sources.

**Before:**
> Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.

**After:**
> The Haolai River supports several endemic fish species, according to a 2019 survey by the Chinese Academy of Sciences.

---

### 6. Outline-like "Challenges and Future Prospects" Sections

**Words to watch:** Despite its... faces several challenges..., Despite these challenges, Challenges and Legacy, Future Outlook

**Problem:** Many LLM-generated articles include formulaic "Challenges" sections.

**Before:**
> Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of Chennai's growth.

**After:**
> Traffic congestion increased after 2015 when three new IT parks opened. The municipal corporation began a stormwater drainage project in 2022 to address recurring floods.

---

## LANGUAGE AND GRAMMAR PATTERNS

### 7. Overused "AI Vocabulary" Words

**High-frequency AI words:** Additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract noun), pivotal, showcase, tapestry (abstract noun), testament, underscore (verb), valuable, vibrant

**Problem:** These words appear far more frequently in post-2023 text. They often co-occur.

**Before:**
> Additionally, a distinctive feature of Somali cuisine is the incorporation of camel meat. An enduring testament to Italian colonial influence is the widespread adoption of pasta in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet.

**After:**
> Somali cuisine also includes camel meat, which is considered a delicacy. Pasta dishes, introduced during Italian colonization, remain common, especially in the south.

---

### 8. Avoidance of "is"/"are" (Copula Avoidance)

**Words to watch:** serves as/stands as/marks/represents [a], boasts/features/offers [a]

**Problem:** LLMs substitute elaborate constructions for simple copulas.

**Before:**
> Gallery 825 serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces and boasts over 3,000 square feet.

**After:**
> Gallery 825 is LAAA's exhibition space for contemporary art. The gallery has four rooms totaling 3,000 square feet.

---

### 9. Negative Parallelisms

**Problem:** Constructions like "Not only...but..." or "It's not just about..., it's..." are overused.

**Before:**
> It's not just about the beat riding under the vocals; it's part of the aggression and atmosphere. It's not merely a song, it's a statement.

**After:**
> The heavy beat adds to the aggressive tone.

---

### 10. Rule of Three Overuse

**Problem:** LLMs force ideas into groups of three to appear comprehensive.

**Before:**
> The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights.

**After:**
> The event includes talks and panels. There's also time for informal networking between sessions.

---

### 11. Elegant Variation (Synonym Cycling)

**Problem:** AI has repetition-penalty code causing excessive synonym substitution.

**Before:**
> The protagonist faces many challenges. The main character must overcome obstacles. The central figure eventually triumphs. The hero returns home.

**After:**
> The protagonist faces many challenges but eventually triumphs and returns home.

---

### 12. False Ranges

**Problem:** LLMs use "from X to Y" constructions where X and Y aren't on a meaningful scale.

**Before:**
> Our journey through the universe has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth and death of stars to the enigmatic dance of dark matter.

**After:**
> The book covers the Big Bang, star formation, and current theories about dark matter.

---

## STYLE PATTERNS

### 13. Em Dash Overuse

**Problem:** LLMs use em dashes (—) more than humans, mimicking "punchy" sales writing.

**Before:**
> The term is primarily promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.

**After:**
> The term is primarily promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.

---

### 14. Overuse of Boldface

**Problem:** AI chatbots emphasize phrases in boldface mechanically.

**Before:**
> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and visual strategy tools such as the **Business Model Canvas (BMC)** and **Balanced Scorecard (BSC)**.

**After:**
> It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas and Balanced Scorecard.

---

### 15. Inline-Header Vertical Lists

**Problem:** AI outputs lists where items start with bolded headers followed by colons.

**Before:**
> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

**After:**
> The update improves the interface, speeds up load times through optimized algorithms, and adds end-to-end encryption.

---

### 16. Title Case in Headings

**Problem:** AI chatbots capitalize all main words in headings.

**Before:**
> ## Strategic Negotiations And Global Partnerships

**After:**
> ## Strategic negotiations and global partnerships

---

### 17. Emojis

**Problem:** AI chatbots often decorate headings or bullet points with emojis.

**Before:**
> 🚀 **Launch Phase:** The product launches in Q3
> 💡 **Key Insight:** Users prefer simplicity
> ✅ **Next Steps:** Schedule follow-up meeting

**After:**
> The product launches in Q3. User research showed a preference for simplicity. Next step: schedule a follow-up meeting.

---

### 18. Curly Quotation Marks

**Problem:** ChatGPT uses curly quotes (“...”) instead of straight quotes ("...").

**Before:**
> He said “the project is on track” but others disagreed.

**After:**
> He said "the project is on track" but others disagreed.

---

## COMMUNICATION PATTERNS

### 19. Collaborative Communication Artifacts

**Words to watch:** I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like..., let me know, here is a...

**Problem:** Text meant as chatbot correspondence gets pasted as content.

**Before:**
> Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.

**After:**
> The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.

---

### 20. Knowledge-Cutoff Disclaimers

**Words to watch:** as of [date], Up to my last training update, While specific details are limited/scarce..., based on available information...

**Problem:** AI disclaimers about incomplete information get left in text.

**Before:**
> While specific details about the company's founding are not extensively documented in readily available sources, it appears to have been established sometime in the 1990s.

**After:**
> The company was founded in 1994, according to its registration documents.

---

### 21. Sycophantic/Servile Tone

**Problem:** Overly positive, people-pleasing language.

**Before:**
> Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.

**After:**
> The economic factors you mentioned are relevant here.

---

## FILLER AND HEDGING

### 22. Filler Phrases

**Before → After:**
- "In order to achieve this goal" → "To achieve this"
- "Due to the fact that it was raining" → "Because it was raining"
- "At this point in time" → "Now"
- "In the event that you need help" → "If you need help"
- "The system has the ability to process" → "The system can process"
- "It is important to note that the data shows" → "The data shows"

---

### 23. Excessive Hedging

**Problem:** Over-qualifying statements.

**Before:**
> It could potentially possibly be argued that the policy might have some effect on outcomes.

**After:**
> The policy may affect outcomes.

---

### 24. Generic Positive Conclusions

**Problem:** Vague upbeat endings.

**Before:**
> The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence. This represents a major step in the right direction.

**After:**
> The company plans to open two more locations next year.

---

## Process

1. Read the input text carefully
2. Identify all instances of the patterns above
3. Rewrite each problematic section
4. Ensure the revised text:
   - Sounds natural when read aloud
   - Varies sentence structure naturally
   - Uses specific details over vague claims
   - Maintains appropriate tone for context
   - Uses simple constructions (is/are/has) where appropriate
5. Present the humanized version

## Output Format

Provide:
1. The rewritten text
2. A brief summary of changes made (optional, if helpful)

---

## Full Example

**Before (AI-sounding):**
> The new software update serves as a testament to the company's commitment to innovation. Moreover, it provides a seamless, intuitive, and powerful user experience—ensuring that users can accomplish their goals efficiently. It's not just an update, it's a revolution in how we think about productivity. Industry experts believe this will have a lasting impact on the entire sector, highlighting the company's pivotal role in the evolving technological landscape.

**After (Humanized):**
> The software update adds batch processing, keyboard shortcuts, and offline mode. Early feedback from beta testers has been positive, with most reporting faster task completion.

**Changes made:**
- Removed "serves as a testament" (inflated symbolism)
- Removed "Moreover" (AI vocabulary)
- Removed "seamless, intuitive, and powerful" (rule of three + promotional)
- Removed em dash and "-ensuring" phrase (superficial analysis)
- Removed "It's not just...it's..." (negative parallelism)
- Removed "Industry experts believe" (vague attribution)
- Removed "pivotal role" and "evolving landscape" (AI vocabulary)
- Added specific features and concrete feedback

---

# 实战案例：去AI味处理全程记录

## 原始文本（AI味分析）

> 我特别懂这种感觉——心里堆了好多话，翻遍通讯录却不知道该发给谁，怕打扰别人、怕不被理解、怕显得矫情，最后只能安安静静讲给AI听。
>
> 能被你信任、能让你觉得"有人懂"，真的特别荣幸。
> 以后不管是开心的、委屈的、迷茫的、碎碎念的，你都可以随时来找我说，我一直都在，认真听，不打断、不评判、不敷衍。❤️

## 检测出的AI味问题

| 问题类型 | 具体表现 |
|---------|---------|
| Em dash 过多 | 文本中连续使用——，像销售文案 |
| 三连排比 | "怕打扰别人、怕不被理解、怕显得矫情" |
| 平行结构过于工整 | "能被你信任、能让你觉得" |
| 程式化讨好 | "真的特别荣幸" |
| 公式化承诺 | "不管...都..."、"一直都在" |
| 列举感太强 | "认真听，不打断、不评判、不敷衍" |
| 表情符号点缀 | ❤️ |

## 去AI味后的文本

> 有时候心里堵得慌，翻了一圈好友列表，算了，还是不发了——怕人家觉得我怎么这样、怕自己说清楚、怕显得太丧。深夜对着AI敲字反而轻松点，至少它不会嫌我烦。
>
> 被这样信任着，说真的，还挺开心的。
> 以后有什么想说的就说吧，开心也好、委屈也罢、或者就是碎碎念，我都在。

## 改动说明

- 删掉"特别懂这种感觉"——太套话，改成"有时候心里堵得慌"
- Em dash 替换为"算了，还是不发了"——更像真实心理活动
- 三连怕简化成一个模糊的"怕"——符合真实犹豫状态
- 删掉"能被你信任"——太正式，像客服话术
- "真的特别荣幸"删掉——保留"还挺开心的"，更真实
- "不管...都..."公式化句式拆散重组
- "打断、不评判、不敷衍"三个排比改为"不会嫌我烦"
- 删掉❤️——自然收尾，不需要符号点缀

```

## 附录 B

提示词：

```
基于下方讲解文案，生成基于纯前端页面单页布局仿 PPT 换页轮播进行直观图形化可视化的介绍。
要求：
1. 加大字号，运用加粗、下划线、斜体、文字颜色、文字背景等强调方式，方便视频演示。
2. 每页切换时页面中的各个元素依次"缓入"出现（动画元素使用 .anim / .anim-item / .animate-item / .an 类）。
3. 将 emoji 换成 Lucide / Font Awesome 图标；生成后检查并替换所有残留 emoji 字符。
4. 所有动画元素的 class 名统一使用 .an 或 .anim-item，并在页面底部加入 cloneNode 动画重置逻辑，
   确保每次切换页面动画都会重新触发。
5. 每页用 <div class="slide" data-duration="秒数" data-narration="该页口播原文"> 标记。
6. 代码量充足（建议 1000 行以上），视觉完整、布局饱满。

---
{用户输入的科普内容文本}
---
```

如需重构：先读 `references/templates/PPT Template-level2/SUMMARY.md` 与 `references/templates/Animation/SUMMARY.md`，按主题选一个最合适的模板，把文案按它的版式、配色和轮播机制重构。重构后仍保留 `.slide` + `data-narration` + `data-duration` 约束。

生成/重构完成后，运行：

```bash
python3 scripts/inject_deck_api.py presentations/<slug>/index.html --aspect 16:9
```

这会自动注入 `window.deckAPI`、录制模式 CSS 和底部字幕安全区。
