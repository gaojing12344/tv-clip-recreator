# 安装 Python 依赖
pip install -r requirements.txt

# 系统依赖
# - ffmpeg / ffprobe（写入 config.md）
# - 字体（写入 config.md，默认 Arial Unicode / 思源黑体）

# 步骤4 · 词汇抽取（PDF 红色字体 → Excel）
python3 scripts/extract_red_words.py <教材.pdf> <输出.xlsx>

# 首次使用 · 生成占位素材三件套（背景/横幅/结尾图，之后按自己账号风格替换）
python3 scripts/generate_assets.py --out assets --title "你的频道名"

# 步骤6 · 渲染合成（词汇匹配 + 字幕 + 9:16 合成，含 whisper 转录缓存）
python3 scripts/render_pipeline.py \
  --episode S01E12 --cuts 7 \
  --video-dir <切割片段目录> \
  --outroot <输出根目录> \
  --excel <词汇.xlsx> \
  --bg assets/background.png

# 步骤6 · 单词视频轨批量合成（主视频 + 单词卡 + banner + 结尾定格）
python3 scripts/compose_word_videos.py \
  --episode S02E11 --folders 1-15 \
  --workroot <friendsN 的父目录> \
  --banner assets/banner.png \
  --background assets/background.png \
  --end-image assets/endcard.jpg \
  --sound assets/task_complete.mp3
