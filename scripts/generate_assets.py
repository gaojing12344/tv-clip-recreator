#!/usr/bin/env python3
"""占位素材生成器 — 一键生成合规格式的中性占位素材三件套。

仓库不附带任何剧集品牌素材（版权问题）。首次使用时运行本脚本，
生成符合合成规范的占位素材，再按你自己的账号风格替换：

  python3 scripts/generate_assets.py --out assets [--title "你的频道名"]

产物（尺寸即规范，替换时保持尺寸不变）：
  background.png   1080x1920  主背景（画布底层）
  banner.png       1080x50    顶部信息条（叠加在 y=450 单词视频轨上沿）
  endcard.jpg      1080x1920  结尾定格图（末帧定格 3 秒）

替换建议：
  - background：纯色系或剧集主题色渐变，顶部留标题区
  - banner：纯色条 + 频道名/栏目名，配色与背景协调
  - endcard：关注引导版式（如「下期再见 / 感谢观看」），可用稿定设计/PS 制作
"""
import argparse
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("缺少 Pillow，请先运行：pip install -r requirements.txt")


def load_font(size):
    for fp in ("/System/Library/Fonts/PingFang.ttc",
               "/System/Library/Fonts/STHeiti Medium.ttc",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def gen_background(path, title):
    img = Image.new("RGB", (1080, 1920), (245, 245, 242))  # 暖白
    d = ImageDraw.Draw(img)
    d.text((540, 300), title, font=load_font(72), fill=(30, 30, 30), anchor="mm")
    d.text((540, 400), "背景占位图 · 请替换为你自己的设计", font=load_font(32),
           fill=(150, 150, 150), anchor="mm")
    img.save(path)
    print(f"✅ {path}  1080x1920")


def gen_banner(path, title):
    img = Image.new("RGB", (1080, 50), (254, 188, 52))  # 暖黄
    d = ImageDraw.Draw(img)
    d.text((540, 25), title, font=load_font(30), fill=(255, 255, 255), anchor="mm")
    img.save(path)
    print(f"✅ {path}  1080x50")


def gen_endcard(path, title):
    img = Image.new("RGB", (1080, 1920), (18, 18, 18))  # 深底
    d = ImageDraw.Draw(img)
    d.text((540, 1100), "下期再见", font=load_font(96), fill=(255, 255, 255), anchor="mm")
    d.text((540, 1300), f"感谢观看 · {title}", font=load_font(44), fill=(200, 200, 200), anchor="mm")
    d.text((540, 1700), "结尾图占位 · 请替换为你自己的设计", font=load_font(28),
           fill=(120, 120, 120), anchor="mm")
    img.save(path, quality=92)
    print(f"✅ {path}  1080x1920")


def main():
    ap = argparse.ArgumentParser(description="生成占位素材三件套（背景/横幅/结尾图）")
    ap.add_argument("--out", default="assets", help="输出目录（默认 assets/）")
    ap.add_argument("--title", default="MY CHANNEL", help="占位标题/频道名")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    gen_background(os.path.join(a.out, "background.png"), a.title)
    gen_banner(os.path.join(a.out, "banner.png"), a.title)
    gen_endcard(os.path.join(a.out, "endcard.jpg"), a.title)
    print("\n完成。请按 references/step6-渲染合成.md 的素材规范替换为你自己的设计。")


if __name__ == "__main__":
    main()
