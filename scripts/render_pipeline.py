#!/usr/bin/env python3
"""
渲染流水线：词汇匹配 + 字幕嵌入 + 9:16 合成（单集多段通用版）

用法:
    python3 render_pipeline.py --episode S01E12 --cuts 7 \
        --video-dir <切割片段目录> --outroot <输出根目录> \
        --excel <词汇xlsx> --bg <assets/background.png> \
        [--ffmpeg /usr/local/bin/ffmpeg] [--font <字体路径>]

流程（每段自动跳过已有有效输出）:
1. 读 Excel（A=word, B=pos+meaning）
2. ffmpeg 抽音频 → faster-whisper 词级转录（结果缓存为 json）
3. 五层匹配: exact → morph → alt_spelling → substring → edit_distance（高频词排除）
   多词目标走滑动窗口 phrase 匹配
4. Pillow 渲染黑字透明 PNG 字幕（字号50，底部三轨堆叠，单条3s）
5. 一步 ffmpeg 合成: background + 居中主视频 + 定时字幕叠加
6. 输出匹配报告 txt / csv / edl

依赖: openpyxl, Pillow, faster-whisper, ffmpeg, ffprobe
"""
import os, sys, json, subprocess, csv, re, argparse
from collections import defaultdict

COMMON_EXCLUDE = {
    'have', 'has', 'had', 'was', 'were', 'is', 'are', 'am', 'do', 'does', 'did',
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'of', 'for',
    'with', 'by', 'from', 'up', 'down', 'out', 'off', 'over', 'under', 'again',
    'started', 'starts', 'start', 'starting', 'like', 'just', 'know', 'think',
    'said', 'say', 'says', 'get', 'got', 'go', 'going', 'one', 'two', 'three',
    'what', 'that', 'this', 'these', 'those', 'who', 'how', 'why', 'when', 'where',
    'there', 'here', 'now', 'then', 'so', 'if', 'as', 'it', 'he', 'she', 'we',
    'they', 'you', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its',
    'our', 'their', 'not', 'no', 'yes', 'all', 'some', 'any', 'can', 'will',
    'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'let', 'more',
    'most', 'much', 'many', 'few', 'little', 'less', 'least', 'very', 'too',
    'also', 'only', 'even', 'still', 'back', 'well', 'right', 'left', 'good',
    'new', 'old', 'big', 'small', 'great', 'long', 'short', 'high', 'low',
    'i', 'oh', 'yeah', 'hey', 'uh', 'um', 'ok', 'okay', 'gonna', 'wanna',
}

ALT_FORMS = {
    'racket': ['racquet'], 'racquet': ['racket'],
    'gray': ['grey'], 'grey': ['gray'],
    'judgment': ['judgement'], 'judgement': ['judgment'],
    'center': ['centre'], 'centre': ['center'],
}

IRREG = {
    'fling': ['flung', 'flinging', 'flings'],
    'swing': ['swung', 'swinging', 'swings'],
    'ring': ['rang', 'rung', 'ringing', 'rings'],
    'sing': ['sang', 'sung', 'singing', 'sings'],
    'spring': ['sprang', 'sprung', 'springing', 'springs'],
    'stick': ['stuck', 'sticking', 'sticks'],
    'strike': ['struck', 'striking', 'strikes', 'stricken'],
    'slide': ['slid', 'sliding', 'slides'],
    'hide': ['hid', 'hidden', 'hiding', 'hides'],
    'bite': ['bit', 'bitten', 'biting', 'bites'],
    'fight': ['fought', 'fighting', 'fights'],
    'catch': ['caught', 'catching', 'catches'],
    'teach': ['taught', 'teaching', 'teaches'],
    'bring': ['brought', 'bringing', 'brings'],
    'think': ['thought', 'thinking', 'thinks'],
    'buy': ['bought', 'buying', 'buys'],
    'seek': ['sought', 'seeking', 'seeks'],
    'break': ['broke', 'broken', 'breaking', 'breaks'],
    'speak': ['spoke', 'spoken', 'speaking', 'speaks'],
}

def morph_forms(word):
    forms = set()
    forms.add(word)
    forms.add(word + 's'); forms.add(word + 'es'); forms.add(word + 'ed')
    forms.add(word + 'ing'); forms.add(word + 'd'); forms.add(word + 'er')
    forms.add(word + 'est'); forms.add(word + 'ly')
    if word.endswith('y') and len(word) > 2:
        stem = word[:-1]
        forms.update([stem + 'ies', stem + 'ied', stem + 'ier', stem + 'iest', stem + 'ying'])
    if word.endswith('e') and len(word) > 2:
        stem = word[:-1]
        forms.update([stem + 'ed', word + 'd', stem + 'ing', stem + 'er'])
    if len(word) >= 3 and word[-1] not in 'aeiou' and word[-2] in 'aeiou' and word[-3] not in 'aeiou':
        forms.add(word + word[-1] + 'ed')
        forms.add(word + word[-1] + 'ing')
    if word in IRREG:
        forms.update(IRREG[word])
    for base, irregs in IRREG.items():
        if word in irregs:
            forms.add(base)
            forms.update(irregs)
    return forms

def edit_dist(a, b):
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i-1] == b[j-1] else 1 + min(dp[j], dp[j-1], prev)
            prev = temp
    return dp[n]

def clean_word(w):
    return re.sub(r'[^a-z]', '', w.lower())

def match_word(target, transcribed_words):
    target = target.lower().strip()
    results = []
    if ' ' in target:
        return phrase_match(target, transcribed_words)
    target_clean = clean_word(target)
    if not target_clean or len(target_clean) < 2:
        return results
    all_forms = morph_forms(target)
    alt_spellings = ALT_FORMS.get(target, [])
    seen_indices = set()
    for i, tw in enumerate(transcribed_words):
        tw_clean = clean_word(tw["word"])
        if not tw_clean or i in seen_indices:
            continue
        match_type = None
        if tw_clean == target_clean:
            match_type = "exact"
        elif tw_clean in all_forms:
            match_type = "morph"
        elif tw_clean in [clean_word(a) for a in alt_spellings]:
            match_type = "alt_spelling"
        elif len(target_clean) >= 3 and target_clean in tw_clean and len(tw_clean) <= len(target_clean) + 4:
            match_type = "substring"
        elif (tw_clean[0] == target_clean[0]
              and tw_clean not in COMMON_EXCLUDE
              and target_clean not in COMMON_EXCLUDE
              and edit_dist(target_clean, tw_clean) <= 2
              and len(target_clean) >= 3):
            match_type = "edit_dist"
        if match_type:
            results.append({"index": i, "start": tw["start"], "end": tw["end"],
                            "matched": tw["word"], "type": match_type})
            seen_indices.add(i)
    return results

def phrase_match(target, transcribed_words):
    target_words = [clean_word(w) for w in target.split()]
    n_target = len(target_words)
    results = []
    for i in range(len(transcribed_words) - n_target + 1):
        window = transcribed_words[i:i + n_target]
        window_clean = [clean_word(w["word"]) for w in window]
        all_match = True
        for j, tw_clean in enumerate(window_clean):
            tgt = target_words[j]
            forms = morph_forms(tgt)
            if tw_clean != tgt and tw_clean not in forms:
                if (tw_clean and tgt and tw_clean[0] == tgt[0]
                    and edit_dist(tgt, tw_clean) <= 2 and len(tgt) >= 3):
                    continue
                all_match = False
                break
        if all_match and all(window_clean):
            if window[-1]["end"] - window[0]["start"] <= 3.0:
                results.append({"index": i, "start": window[0]["start"],
                                "end": window[-1]["end"],
                                "matched": " ".join(w["word"] for w in window),
                                "type": "phrase"})
    return results

def render_subtitle_png(text, out_path, font_path, font_size):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(font_path, font_size)
    tmp = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((0, 0), text, font=font, spacing=2)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 10
    img = Image.new("RGBA", (text_w + pad * 2, text_h + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=(0, 0, 0, 255), spacing=2)
    img.save(out_path)
    return text_w + pad * 2, text_h + pad * 2

def compute_y_positions(matches, canvas_h, bottom_margin, text_h, spacing, duration):
    n = len(matches)
    if n == 0:
        return []
    sorted_matches = sorted(range(n), key=lambda i: matches[i]["start"])
    chain_id = [0] * n
    current_chain = 0
    chain_last_end = 0.0
    for idx in sorted_matches:
        start = matches[idx]["start"]
        if start >= chain_last_end:
            current_chain += 1
        chain_id[idx] = current_chain
        chain_last_end = max(chain_last_end, start + duration)
    chain_members = defaultdict(list)
    for i in range(n):
        chain_members[chain_id[i]].append(i)
    y_positions = [0] * n
    for cid, members in chain_members.items():
        chain_size = len(members)
        for idx, member_i in enumerate(members):
            y = canvas_h - bottom_margin - text_h - (chain_size - 1 - idx) * spacing
            y_positions[member_i] = max(0, y)
    return y_positions

def compose_video(seg, matches, y_positions, cfg):
    n = seg["n"]
    outpath = f"{seg['outdir']}/{seg['outname']}"
    video_path = seg["video"]
    sub_dir = f"{seg['outdir']}/sub_images"
    os.makedirs(sub_dir, exist_ok=True)
    CW, CH = cfg.canvas_w, cfg.canvas_h

    def blank():
        cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error",
               "-i", cfg.bg, "-i", video_path,
               "-filter_complex",
               f"[1:v]scale={CW}:-1[vid];[0:v][vid]overlay=(W-w)/2:(H-h)/2[v]",
               "-map", "[v]", "-map", "1:a?",
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
               "-c:a", "aac", "-b:a", "128k", "-y", outpath]
        subprocess.run(cmd, check=True)

    if not matches:
        print(f"  Cut{n}: No matches, blank 9:16 video")
        blank()
        return outpath

    sub_files = []
    for i, m in enumerate(matches):
        word_en, word_meaning = m["target_en"], m["target_meaning"]
        parts = word_meaning.split(".", 1)
        if len(parts) == 2 and len(parts[0]) <= 4:
            text = f"{word_en}({parts[0]}) | {parts[1]}"
        else:
            text = f"{word_en} | {word_meaning}"
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', word_en.lower())
        png_path = f"{sub_dir}/{safe_name}.png"
        if not os.path.exists(png_path):
            tw, th = render_subtitle_png(text, png_path, cfg.font, cfg.font_size)
        else:
            from PIL import Image
            tw, th = Image.open(png_path).size
        sub_files.append({"path": png_path, "start": m["start"],
                          "end": m["start"] + cfg.display_duration,
                          "y": y_positions[i], "w": tw, "h": th})

    inputs = ["-i", cfg.bg, "-i", video_path]
    for sf in sub_files:
        inputs += ["-i", sf["path"]]

    parts = [f"[1:v]scale={CW}:-1[vid]",
             f"[0:v][vid]overlay=(W-w)/2:(H-h)/2[v0]"]
    for idx, sf in enumerate(sub_files):
        input_idx = idx + 2
        in_label = f"v{idx}"
        out_label = f"v{idx+1}" if idx < len(sub_files) - 1 else "vout"
        parts.append(f"[{in_label}][{input_idx}:v]overlay=(W-w)/2:{sf['y']}"
                     f":enable='between(t,{sf['start']},{sf['end']})'[{out_label}]")

    cmd = [cfg.ffmpeg, "-hide_banner", "-loglevel", "error"] + inputs + [
        "-filter_complex", ";".join(parts),
        "-map", "[vout]", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-y", outpath]
    print(f"  Cut{n}: Composing with {len(sub_files)} subtitles...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:500]}")
        raise RuntimeError(f"ffmpeg compose failed for Cut{n}")
    return outpath

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True, help="如 S01E12")
    ap.add_argument("--cuts", type=int, default=7, help="片段数")
    ap.add_argument("--video-dir", required=True, help="切割片段所在目录")
    ap.add_argument("--outroot", required=True, help="每段输出目录的父目录（其下需有 friendsN 式子目录，或直接用 video-dir）")
    ap.add_argument("--excel", required=True, help="词汇表 xlsx")
    ap.add_argument("--bg", required=True, help="assets/background.png")
    ap.add_argument("--ffmpeg", default="/usr/local/bin/ffmpeg")
    ap.add_argument("--ffprobe", default="/usr/local/bin/ffprobe")
    ap.add_argument("--font", default="/Library/Fonts/Arial Unicode.ttf")
    ap.add_argument("--canvas-w", type=int, default=1080)
    ap.add_argument("--canvas-h", type=int, default=1920)
    ap.add_argument("--font-size", type=int, default=50)
    ap.add_argument("--bottom-margin", type=int, default=80)
    ap.add_argument("--subtitle-spacing", type=int, default=80)
    ap.add_argument("--display-duration", type=float, default=3.0)
    cfg = ap.parse_args()

    import openpyxl
    wb = openpyxl.load_workbook(cfg.excel)
    ws = wb.active
    vocab = [{"en": str(r[0]).strip(), "meaning": str(r[1]).strip()}
             for r in ws.iter_rows(min_row=2, values_only=True) if r[0] and r[1]]
    print(f"Excel: {len(vocab)} words")

    from faster_whisper import WhisperModel
    print("Loading Whisper base model (CPU)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")

    segments = []
    for i in range(1, cfg.cuts + 1):
        outdir = cfg.outroot if cfg.outroot == cfg.video_dir else os.path.join(cfg.outroot, f"ep{cfg.episode}_cut{i}")
        os.makedirs(outdir, exist_ok=True)
        segments.append({
            "n": i,
            "video": os.path.join(cfg.video_dir, f"{cfg.episode}_Cut{i}.mp4"),
            "audio": os.path.join(outdir, f"{cfg.episode}_Cut{i}_audio.wav"),
            "transcript": os.path.join(outdir, f"{cfg.episode}_Cut{i}_transcript.json"),
            "outdir": outdir,
            "outname": f"{cfg.episode}_Cut{i}-1.mp4",
        })

    for seg in segments:
        if not os.path.exists(seg["video"]):
            print(f"  SKIP Cut{seg['n']}: video not found: {seg['video']}")
            continue
        if not os.path.exists(seg["audio"]):
            subprocess.run([cfg.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", seg["video"],
                            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-y", seg["audio"]], check=True)
        if not os.path.exists(seg["transcript"]):
            print(f"  Transcribing Cut{seg['n']}...")
            segs, info = model.transcribe(seg["audio"], word_timestamps=True, vad_filter=False)
            words = [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
                     for s in segs if s.words for w in s.words]
            with open(seg["transcript"], "w") as f:
                json.dump({"duration": info.duration, "words": words}, f, ensure_ascii=False, indent=2)

    print("\nMatching + composing...")
    for seg in segments:
        if not os.path.exists(seg["video"]):
            continue
        n = seg["n"]
        outpath_check = f"{seg['outdir']}/{seg['outname']}"
        probe = subprocess.run([cfg.ffprobe, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", outpath_check],
                               capture_output=True, text=True)
        if probe.returncode == 0 and probe.stdout.strip():
            print(f"  Cut{n}: output exists ({probe.stdout.strip()}s), skip")
            continue

        with open(seg["transcript"]) as f:
            transcript = json.load(f)
        tw = transcript["words"]
        seg["duration"] = transcript["duration"]
        print(f"\n--- Cut{n}: {len(tw)} words, {seg['duration']:.1f}s ---")

        matches = []
        for v in vocab:
            for r in match_word(v["en"], tw):
                matches.append({"target_en": v["en"], "target_meaning": v["meaning"],
                                "start": r["start"], "end": r["end"],
                                "matched_word": r["matched"], "match_type": r["type"]})
        seen, deduped = set(), []
        for m in sorted(matches, key=lambda x: x["start"]):
            key = m["target_en"].lower()
            if key not in seen:
                seen.add(key)
                deduped.append(m)
        matches = deduped
        print(f"  Matched: {len(matches)}/{len(vocab)}")

        y_positions = compute_y_positions(matches, cfg.canvas_h, cfg.bottom_margin,
                                          60, cfg.subtitle_spacing, cfg.display_duration)
        try:
            compose_video(seg, matches, y_positions, cfg)
        except RuntimeError as e:
            print(f"  {e}")
            continue

        base = f"{seg['outdir']}/{cfg.episode}_Cut{n}-1"
        with open(base + "_匹配词汇汇总.txt", "w", encoding="utf-8") as f:
            f.write(f"{cfg.episode} Cut{n} 匹配词汇汇总\n视频时长: {seg['duration']:.1f}s\n匹配词数: {len(matches)}/{len(vocab)}\n" + "="*60 + "\n\n")
            for m in matches:
                f.write(f"{m['start']:.2f}s  {m['target_en']}  {m['target_meaning']}  ({m['match_type']}: {m['matched_word']})\n")
        with open(base + "_匹配词汇.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["时间", "英文单词", "词性&释义", "匹配类型", "匹配文本"])
            for m in matches:
                w.writerow([f"{m['start']:.2f}", m["target_en"], m["target_meaning"], m["match_type"], m["matched_word"]])

    print("\nPIPELINE COMPLETE")

if __name__ == "__main__":
    main()
