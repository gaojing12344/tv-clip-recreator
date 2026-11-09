#!/usr/bin/env python3
"""
单词视频轨合成：主视频 + 单词卡(图/视频交替) + banner + 结尾定格（单集批量版）

规则: 词汇没有匹配到 karaoke 视频时整词跳过（无图无声效）。
输出命名: <episode>-<n>-done.mp4

用法:
    python3 compose_word_videos.py --episode S02E11 --folders 1-15 \
        --workroot <friendsN 的父目录> \
        --banner assets/1.png --background assets/background.png \
        --end-image assets/2.jpg --sound assets/task_complete.mp3

每段结构: 主视频 → [单词图2s + 单词视频dur] × N → 结尾图3s，最后 concat 封装。
依赖: ffmpeg, ffprobe
"""
import subprocess, os, sys, tempfile, time, glob, argparse

W, H = 1080, 1920
FPS = 30
WORD_IMG_DUR = 2.0
END_DUR = 3.0
BANNER_Y = 450
WORD_IMG_Y = 850
VID_Y = 450
BANNER_W, BANNER_H = 1080, 50

ENC = ["-c:v", "h264_videotoolbox", "-b:v", "8M", "-r", str(FPS),
       "-c:a", "aac", "-ar", "44100", "-ac", "2",
       "-pix_fmt", "yuv420p"]

NAME_MAP = {"statue_of_liberty": "Statue_of_Liberty",
            "can_t_help_but": "cant_help_but"}

def run(cmd, label=""):
    t0 = time.time()
    print(f"  >>> {label}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.time() - t0
    if r.returncode != 0:
        print(f"     FAILED ({dt:.1f}s)\n     STDERR: {r.stderr[-800:]}")
        sys.exit(1)
    print(f"     OK ({dt:.1f}s)")

def get_duration(path, ffprobe):
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())

def discover_words(folder):
    sub_dir = os.path.join(folder, "sub_images")
    images = sorted(glob.glob(os.path.join(sub_dir, "*.png")))
    videos = sorted(glob.glob(os.path.join(folder, "*_karaoke.mp4")))
    video_map = {}
    for v in videos:
        video_map[os.path.basename(v).split("_karaoke")[0]] = v
    words = []
    for img in images:
        img_name = os.path.splitext(os.path.basename(img))[0]
        lookup = NAME_MAP.get(img_name, img_name)
        if lookup in video_map:
            vid_path = video_map[lookup]
            words.append((img_name + ".png", os.path.basename(vid_path), get_duration(vid_path, FFPROBE)))
        else:
            print(f"  SKIP: No video for '{img_name}', omitted entirely")
    return words

def render_folder(folder_num, cfg):
    folder = os.path.join(cfg.workroot, f"friends{folder_num}")
    main_video = os.path.join(folder, f"{cfg.episode}_Cut{folder_num}-1.mp4")
    if not os.path.exists(main_video):
        print(f"\n=== friends{folder_num}: main video not found, skip ===")
        return
    output = os.path.join(folder, f"{cfg.episode}-{folder_num}-done.mp4")

    print(f"\n{'='*60}\n=== Rendering friends{folder_num} ===\n{'='*60}")
    words = discover_words(folder)

    if not words:
        main_dur = get_duration(main_video, FFPROBE)
        print(f"  No word content, passthrough main video ({main_dur:.1f}s)")
        run([FFMPEG, "-y", "-i", main_video,
             "-vf", f"scale={W}:{H},setsar=1,format=yuv420p,fps={FPS}",
             *ENC, output], f"Copy main video ({main_dur:.1f}s)")
        print(f"\n  OUTPUT: {output}  Size: {os.path.getsize(output)/1024/1024:.0f}MB")
        return

    main_dur = get_duration(main_video, FFPROBE)
    print(f"  Main video: {main_dur:.1f}s  Words: {len(words)}")

    TEMP = tempfile.mkdtemp(prefix=f"render_{cfg.episode}_f{folder_num}_")
    segments = []

    out = os.path.join(TEMP, "01_main.mp4")
    run([FFMPEG, "-y", "-i", main_video,
         "-vf", f"scale={W}:{H},setsar=1,format=yuv420p,fps={FPS}",
         *ENC, out], f"Main video ({main_dur:.1f}s)")
    segments.append(out)

    for i, (img_name, vid_name, dur) in enumerate(words):
        img_p = os.path.join(folder, "sub_images", img_name)
        out_i = os.path.join(TEMP, f"{i+2:02d}_img.mp4")
        run([FFMPEG, "-y",
             "-loop", "1", "-t", str(WORD_IMG_DUR), "-i", cfg.background,
             "-loop", "1", "-t", str(WORD_IMG_DUR), "-i", img_p,
             "-loop", "1", "-t", str(WORD_IMG_DUR), "-i", cfg.banner,
             "-i", cfg.sound,
             "-filter_complex",
             f"[0:v]scale={W}:{H},setsar=1,format=yuv420p[bg];"
             f"[1:v]scale=900:-1,setsar=1[wi];"
             f"[2:v]scale={BANNER_W}:{BANNER_H},setsar=1[bn];"
             f"[bg][wi]overlay=x=(W-w)/2:y={WORD_IMG_Y}[t1];"
             f"[t1][bn]overlay=x=(W-w)/2:y={BANNER_Y}[vout];"
             f"[3:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
             f"apad=whole_dur={WORD_IMG_DUR},atrim=0:{WORD_IMG_DUR},asetpts=N/SR/TB[aout]",
             "-map", "[vout]", "-map", "[aout]",
             *ENC, out_i], f"Word {i+1}/{len(words)} image: {img_name}")
        segments.append(out_i)

        vid_p = os.path.join(folder, vid_name)
        out_v = os.path.join(TEMP, f"{i+2:02d}_vid.mp4")
        run([FFMPEG, "-y",
             "-loop", "1", "-t", str(dur), "-i", cfg.background,
             "-i", vid_p,
             "-loop", "1", "-t", str(dur), "-i", cfg.banner,
             "-filter_complex",
             f"[0:v]scale={W}:{H},setsar=1,format=yuv420p[bg];"
             f"[1:v]scale=1080:1080,setsar=1[v];"
             f"[2:v]scale={BANNER_W}:{BANNER_H},setsar=1[bn];"
             f"[bg][v]overlay=x=0:y={VID_Y}[t1];"
             f"[t1][bn]overlay=x=(W-w)/2:y={BANNER_Y}[vout]",
             "-map", "[vout]", "-map", "1:a",
             *ENC, out_v], f"Word {i+1}/{len(words)} video: {vid_name} ({dur:.1f}s)")
        segments.append(out_v)

    out_e = os.path.join(TEMP, "end.mp4")
    run([FFMPEG, "-y",
         "-loop", "1", "-t", str(END_DUR), "-i", cfg.end_image,
         "-filter_complex",
         f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
         f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p[vout];"
         f"anullsrc=channel_layout=stereo:sample_rate=44100:d={END_DUR}[aout]",
         "-map", "[vout]", "-map", "[aout]",
         *ENC, out_e], f"End image ({END_DUR}s)")
    segments.append(out_e)

    concat_list = os.path.join(TEMP, "concat.txt")
    with open(concat_list, "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")

    total_dur = main_dur + sum(WORD_IMG_DUR + d for _, _, d in words) + END_DUR
    print(f"\n  Concatenating {len(segments)} segments, total ~{total_dur:.1f}s")
    r = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
                        "-c", "copy", output], capture_output=True, text=True)
    if r.returncode != 0:
        print("  Stream copy failed, re-encoding...")
        run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat_list, *ENC, output],
            "Concat (re-encode)")
    else:
        print("  Concat OK (stream copy)")
    print(f"\n  OUTPUT: {output}  Size: {os.path.getsize(output)/1024/1024:.0f}MB  Duration: ~{total_dur:.1f}s")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True)
    ap.add_argument("--folders", default="1-15", help="如 1-15 或 1,3,5")
    ap.add_argument("--workroot", required=True, help="friendsN 目录的父目录")
    ap.add_argument("--banner", required=True)
    ap.add_argument("--background", required=True)
    ap.add_argument("--end-image", required=True)
    ap.add_argument("--sound", required=True)
    ap.add_argument("--ffmpeg", default="/usr/local/bin/ffmpeg")
    ap.add_argument("--ffprobe", default="/usr/local/bin/ffprobe")
    cfg = ap.parse_args()
    FFMPEG, FFPROBE = cfg.ffmpeg, cfg.ffprobe
    if "-" in cfg.folders:
        a, b = cfg.folders.split("-")
        folders = range(int(a), int(b) + 1)
    else:
        folders = [int(x) for x in cfg.folders.split(",")]
    for folder_num in folders:
        render_folder(folder_num, cfg)
    print(f"\n{'='*60}\nALL DONE!\n{'='*60}")
