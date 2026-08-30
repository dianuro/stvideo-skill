# stvideo — 一句话生成讲解视频

从你的“一句话需求”到成片：**自动调研、生成带配音和字幕的讲解视频**。默认横屏 16:9，也支持竖屏 9:16。

## 它能做什么？

- 输入任意主题（如“什么是区块链”“如何做好时间管理”）
- 自动联网搜集资料 → 产出完整视频文案 → 你确认后生成漂亮的 HTML 幻灯（PPT 风格）
- 自动生成口语化解说稿（并去除“AI味”）
- 用 Edge TTS 生成中文配音，自动配字幕
- 录屏 + 字幕叠加 → 输出 MP4 成片

整个过程提供两次人工确认点（文案、HTML + 文稿），确保内容符合预期。

---

## 安装

下载本仓库，交给你的agent, 告诉它“帮我安装这个skill即可”。

## 依赖

- Python 3.8+
- `ffmpeg`、`ffprobe`（系统安装）
- Python 包：`edge-tts`、`playwright`、`pillow`（可选 `fonttools` 用于精确中文检测）
- 中文字体（由用户提供或系统自带）

## 说明

该Skill实际是通过整合，借鉴了其他几个Skill的功能实现的，分别是：

- science-content-ppt - 生成html演示 (https://github.com/Unclecheng-li/AI_Animation)
- humanizer - 减少文案的AI味 (https://www.bilibili.com/video/BV1uQ8E6LE6G)
- bbshare-video - 把一个概念做成一条带旁白的讲解视频 (https://github.com/bbshare/bbshare-skills)

# 效果预览

我自己的效果较好的案例(https://www.bilibili.com/video/BV1A84m6GErs)

<iframe src="//player.bilibili.com/player.html?isOutside=true&aid=117180381272799&bvid=BV1A84m6GErs&cid=41409184926&p=1" scrolling="no" border="0" frameborder="no" framespacing="0" allowfullscreen="true"></iframe>
