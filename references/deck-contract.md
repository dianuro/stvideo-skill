# stvideo 录制契约（对 AI-Animation 生成物的最小约束）

stvideo 的 HTML 完全由 AI-Animation-Skill 的工作流生成，本脚本只负责在生成好的 HTML 上**事后注入**录制契约。因此，模型不需要手写 `window.deckAPI` 或自定义录制 CSS。

## 生成 HTML 时必须满足的约束

1. 每页是一个 `<div class="slide">`（或 `<section class="slide">`）。可以有额外类名如 `bg-1`、`active`。
2. 每页必须带 `data-narration="该页口播词"`。
3. 每页建议带 `data-duration="秒数"`（缺省时注入脚本默认 8 秒）。
4. 页面切换通过 `.slide` 上的 `.active` 类控制：`.slide` 默认隐藏，`.slide.active` 显示。
5. 动画元素使用 `.anim` / `.an` / `.anim-item` / `.animate-item`；其中 `.anim` 常与 `.show` 配合触发。
6. emoji 必须替换为 Lucide / Font Awesome 图标，并在生成后检查残留 emoji。
7. 全屏幻灯容器通常为 `.slide-container` 或 `.deck`，尺寸占满视口。

## 注入脚本做什么

运行：
```bash
python scripts/inject_deck_api.py presentations/<slug>/index.html --aspect 16:9
```

注入内容：
- `body.stv-record` 录制模式：占满视口、隐藏导航/提示类固定元素、底部字幕安全区。
- `html.stv-font` 录制模式下的根字号（横屏 16px，竖屏 22px，可覆盖）。
- `window.deckAPI`：
  - `go(index, {slideMs})`
  - `playSequence(durationsMs)`
  - `getSlideCount()`
  - `getDurationsSec()`
  - `setRecordMode(bool)`

注入是幂等的：重复运行会替换上一次注入的块。

## 生成后检查清单

- 页数、顺序、口播词与 `narration.txt` 一致。
- 没有未替换的 emoji。
- Lucide 图标正常加载（依赖 `unpkg.com`，录制时必须有网络或已内联 SVG）。
- 预览 `index.html?record=1` 时，底部应留出字幕安全区，正文不会被字幕遮挡。
