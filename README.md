# stvideo

从一句话需求生成带解说与配音的讲解视频。

视觉完全由 **AI-Animation-Skill** 生成；stvideo 只负责：配音、字幕、把 AI-Animation 网页录制成视频。

## 工作流

1. **需求 + 调研 → 文案**：用户简述主题，skill 联网搜集资料并产出结构化视频文案 `script.md`。
2. **文案 → HTML + 口播稿**：使用 AI-Animation-Skill 的提示词/模板生成 `index.html`，每页 `.slide` 带 `data-narration`；同步产出 `narration.txt`（给用户改）并做**去 AI 味**处理。生成后运行 `inject_deck_api.py` 注入录制契约。
3. **渲染成片**：先问用户用哪款字幕字体（见下）→ edge-tts 配音 → 字幕 → Playwright 录制 AI-Animation HTML → 字幕叠加（白字 + 2px 黑描边）→ 合成 `final/<slug>.mp4`。

## 快速使用

```bash
# 创建项目目录，按 SKILL.md 写 index.html 与 narration.txt
mkdir -p presentations/foo
# ... 写入内容 ...

# 一键渲染（AI-Animation 模板是 PPT/横屏风格，默认 16:9）
bash /path/to/stvideo/scripts/build_video.sh presentations/foo          # 横屏 16:9
bash /path/to/stvideo/scripts/build_video.sh presentations/foo \
  --aspect 9:16                                                         # 竖屏
# 换音色 / 加背景乐
bash /path/to/stvideo/scripts/build_video.sh presentations/foo \
  --voice zh-CN-YunxiNeural --bgm music.mp3
# 指定字幕字体（推荐：先让用户从本机字体里挑一个）
bash /path/to/stvideo/scripts/build_video.sh presentations/foo --font ~/Fonts/My.ttf

# 只想注入录制契约/检查
python3 /path/to/stvideo/scripts/inject_deck_api.py presentations/foo/index.html
```

## 字幕字体：先问用户

skill 不带字体文件（约 18 MB），也**不会在用户不知情时联网下载**。
缺字体时 `build_video.sh` 直接报错退出，由 agent 去问用户。

```bash
python3 scripts/fetch_font.py --list-system
# Noto Sans CJK JP (+9 faces)	/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc	19.5 MB
# Noto Serif CJK SC	/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc	26.3 MB
```

列出的每一项都通过了中文覆盖检测（能真正画出「中文」）。把这列表给用户选：

1. **用系统字体** —— 挑一个，`--font <path>` 传下去（推荐）
2. **用户自备** —— 让用户给路径
3. **下载霞鹜文楷** —— 必须说明是 18.5 MB，用户同意后才加 `--allow-fetch`

其他命令：

```bash
python3 scripts/fetch_font.py --resolve          # 只解析路径，从不联网
python3 scripts/fetch_font.py --list             # 可下载预设
python3 scripts/fetch_font.py --download         # opt-in 下载（需先征得同意）
python3 scripts/fetch_font.py --url https://…/X.ttf
```

## 目录结构

```
stvideo/
  SKILL.md                 # 完整工作流与提示词
  README.md
  assets/fonts/            # 字体缓存（用户同意下载后才会有，不随包分发）
  references/
    deck-contract.md       # AI-Animation HTML 的最小录制契约
    templates/             # AI-Animation 风格参考模板
  scripts/
    build_video.sh         # 总控
    inject_deck_api.py     # 把录制契约注入 AI-Animation HTML
    fetch_font.py          # 字幕字体解析/下载
    tts.py                 # edge-tts 配音
    build_srt.py           # 根据字权生成 SRT
    deck_capture.py        # Playwright 时间轴/录屏
    render_captions.py     # 字幕 PNG 渲染（白字 + 2px 黑描边）
    compose.sh             # 对齐 + 烧字幕 + 混流
    mix_bgm.sh             # 混背景乐
```

## 依赖

- `ffmpeg` + `ffprobe`
- `pip install edge-tts playwright pillow`
- `python -m playwright install chromium`
- 一款中文字体：由用户指定系统已有的、或自备的；脚本不自动下载（见上）

已在 Ubuntu + Python 3.11 上完成端到端验证；成片基于真实 AI-Animation 模板（`PPT Template-level2/3-1.html`）生成。
