# tv-clip-recreator · 剧集剪辑二创引擎

一个 [Agent Skills 开放标准](https://agentskills.io)技能：把任意一部剧集变成短视频二创内容的标准流水线。兼容 WorkBuddy、Codex CLI、Claude Code 等支持该标准的工具。

**引擎与剧集解耦**——流程、规范、方法论全部通用；每部剧只是 `shows/` 目录下一份可插拔的档案文件。已适配《老友记》《绝望主妇》《冰与火之歌》，适配新剧只需回答 5 个问题。

## 六步流水线

| 步 | 内容 | 说明 |
|---|------|------|
| 1 | 视频切割 | ffmpeg 无损快切，编号模板批量下发 |
| 2 | 封面生成 | 思源黑体 + 圆圈数字编号，坐标可微调 |
| 3 | 主题输出 | 1 主旨 + 3-5 衍生主题，表格化 |
| 4 | 词汇抽取 | PDF 红色字体 → Excel（口语学习向可开关） |
| 5 | 素材抓取 | playphrase.me 真实语境片段（可开关） |
| 6 | 渲染合成 | 9:16 竖版 + 三轨字幕 + 单词轨叠加 |

每步带**前置检查**：产物已存在则确认复用，不默认重跑；口语学习向与剧情向剧集自动走不同分支。

## 安装

本 skill 遵循 [Agent Skills 开放标准](https://agentskills.io)，同一份文件可在任何支持该标准的工具中使用：

| 工具 | 安装方式 |
|---|---|
| WorkBuddy | `cp -r tv-clip-recreator ~/.workbuddy/skills/` |
| Codex CLI | `cp -r tv-clip-recreator ~/.codex/skills/`（或放入仓库的 `.codex/skills/`） |
| Claude Code | `cp -r tv-clip-recreator ~/.claude/skills/` |

```bash
pip install -r requirements.txt   # PyMuPDF / openpyxl / Pillow / faster-whisper
```

首次使用时按提示生成 `config.md`（本机环境配置，不进仓库）。系统还需 ffmpeg / ffprobe。

## 仓库自带实战脚本

scripts/ 目录里的三个脚本直接来自真实生产流水线（经过多集实战打磨）：

| 脚本 | 用途 |
|---|---|
| `extract_red_words.py` | PDF 红色字体 → 词汇 Excel（跨行合并 + 词性解析） |
| `render_pipeline.py` | whisper 转录 + 五层词汇匹配 + 字幕渲染 + 9:16 合成 |
| `compose_word_videos.py` | 单词视频轨批量合成（主视频 + 单词卡 + banner + 结尾定格） |
| `generate_assets.py` | 一键生成占位素材三件套（背景/横幅/结尾图），生成后按自己账号风格替换 |

完整命令示例见 `scripts/QUICKSTART.md`。

> **关于品牌素材**：背景图 / banner / 结尾图属于你的账号品牌设计，仓库不提供也不应直接使用他人设计（另有版权原因）。首次使用运行 `generate_assets.py` 生成合规格式的占位版，再用稿定设计 / PS 换成你自己的。

## 使用

```
帮我剪《绝望主妇》S01E03
```

首次提到某部剧时，会引导你回答 5 个问题生成该剧的档案；之后同剧所有集数直接复用。

## 目录结构

```
tv-clip-recreator/
├── SKILL.md              # 总编排：环境检查 → 档案解析 → 六步流水线
├── references/           # 六步分步规范
├── shows/                # 剧集档案（每部剧一份，可插拔）
│   ├── _template.md      # 新剧档案模板
│   ├── friends.md
│   ├── 绝望主妇.md
│   └── 冰与火之歌.md
├── scripts/              # 实战脚本（PDF抽词 / 渲染流水线 / 单词轨合成 / 素材生成）
├── assets/               # 音效随仓库提供；图片素材由 generate_assets.py 生成（不入库）
├── requirements.txt      # Python 依赖
└── config.md.example     # 本机环境配置模板
```

## 贡献

欢迎 PR 你的剧集档案（`shows/<剧名>.md`）——这是本仓库门槛最低的贡献方式。

## License

MIT
