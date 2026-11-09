# Step 6 · 渲染合成

## 画布与字幕规范（所有剧集通用）

- 画布：9:16 竖版
- 底部字幕三轨：y = 50 / 120 / 190 px
- 字号：50pt 非粗体，字间距 2px，单条显示 3 秒
- 转录：faster-whisper；词汇匹配：「精确 + 形态模糊」双轨

## 合成模板（自下而上叠加）

1. background.png 背景
2. main video 主视频
3. 字幕图（y=850）
4. 单词视频片段（y=450；剧集档案开启词汇步骤时才有此轨）
5. banner（y=450）
6. 任务完成音效
7. 结尾图定格 3 秒

## 素材规范（背景 / banner / 结尾图）

⚠️ 这三件是**账号品牌素材，仓库不提供**（涉及版权与个人设计）。首次使用时运行占位生成器，再按自己账号风格替换（稿定设计 / PS 均可）：

```bash
python3 scripts/generate_assets.py --out assets --title "你的频道名"
```

| 素材 | 尺寸 | 位置 | 要求 |
|---|---|---|---|
| background.png | 1080x1920 | 画布底层 | 纯色系或主题色渐变，顶部留标题区 |
| banner.png | 1080x50 | y=450（单词视频轨上沿） | 纯色条 + 频道/栏目名，配色协调 |
| endcard.jpg | 1080x1920 | 末帧定格 3 秒 | 关注引导版式（如「下期再见 / 感谢观看」） |

任务完成音效为通用 UI 音效，随仓库提供（`assets/task_complete.mp3`），可自行替换。剧集专属素材从该剧工作目录读取。

## 两个一键脚本

**1. 词汇匹配 + 字幕嵌入 + 9:16 合成**（含 whisper 转录与缓存）：

```bash
python3 scripts/render_pipeline.py \
  --episode S01E12 --cuts 7 \
  --video-dir <切割片段目录> --outroot <输出根目录> \
  --excel <词汇.xlsx> --bg assets/background.png
```

内部流程：抽音频 → faster-whisper 词级转录（json 缓存）→ 五层词汇匹配（exact → morph → alt_spelling → substring → edit_dist，多词走 phrase 滑动窗口）→ Pillow 渲染黑字透明 PNG → 一步 ffmpeg 叠加合成。每段已有有效输出自动跳过，并输出匹配报告（txt / csv）。

**2. 单词视频轨批量合成**（主视频 + 单词卡图/视频交替 + banner + 结尾定格 3s）：

```bash
python3 scripts/compose_word_videos.py \
  --episode S02E11 --folders 1-15 \
  --workroot <friendsN 的父目录> \
  --banner assets/banner.png --background assets/background.png \
  --end-image assets/endcard.jpg --sound assets/task_complete.mp3
```

规则：词汇没有对应 karaoke 视频时整词跳过（无图无声效）。

依赖安装见 scripts/QUICKSTART.md。

## 批量交付

批量渲染完成后输出表格：文件名、大小、时长，以及各目录统计（cut / cover / words / final）。
