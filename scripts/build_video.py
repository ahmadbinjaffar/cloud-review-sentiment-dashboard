"""Assemble presentation/Project_Presentation_Video.mp4 (target 5-8 min, with audio).

Pipeline: every scene (one slide still, or the Playwright dashboard recording for
the "Demo" section) is encoded to an exact frame count matching its narration
length; the per-scene audio segments are padded/trimmed to the same length, so
video and audio cannot drift. Subtitles from Video_Script.md are burned in with
libass. Verifies duration, A/V streams, decodability and audio level.

Run:  .venv\\Scripts\\python.exe scripts\\build_video.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from mutagen.mp3 import MP3

ROOT = Path(__file__).resolve().parents[1]
PRES = ROOT / "presentation"
AUDIO = PRES / "audio"
SLIDES = PRES / "slide_images"
TMP = PRES / "_video_tmp"
DEMO_WEBM = PRES / "dashboard_recording.webm"
SRT = PRES / "subtitles.srt"
OUT = PRES / "Project_Presentation_Video.mp4"

W, H, FPS = 1600, 900, 15
SCENE_ORDER = [f"slide_{i:02d}" for i in range(1, 10)] + ["demo"] + \
              [f"slide_{i:02d}" for i in range(10, 16)]
WINGET_FFMPEG = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"


def find_ffmpeg() -> Path:
    exe = shutil.which("ffmpeg")
    if exe:
        return Path(exe)
    hits = sorted(WINGET_FFMPEG.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
    if hits:
        return hits[-1]
    raise RuntimeError("ffmpeg not found (PATH or WinGet Gyan.FFmpeg)")


FFMPEG = find_ffmpeg()
FFPROBE = FFMPEG.with_name("ffprobe.exe")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        print("ffmpeg failed:", cmd)
        print(proc.stderr[-3000:])
        raise SystemExit(1)
    return proc


def parse_sections(md: str) -> dict[str, str]:
    """key -> narration text; 'Slide N' -> slide_NN, 'Demo' -> demo."""
    out: dict[str, str] = {}
    key: str | None = None
    buf: list[str] = []
    for line in md.splitlines():
        if line.startswith("## "):
            if key:
                out[key] = " ".join(buf).strip()
            m = re.match(r"Slide (\d+)", line[3:])
            key = f"slide_{int(m.group(1)):02d}" if m else "demo"
            buf = []
        elif key and line.strip():
            buf.append(line.strip())
    if key:
        out[key] = " ".join(buf).strip()
    return out


def make_cues(text: str, dur: float) -> list[tuple[float, float, str]]:
    """Split narration into subtitle cues; durations proportional to length."""
    raw = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    sents = [s if s[-1] in ".!?" else s + "." for s in raw]
    groups: list[str] = []
    for s in sents:
        if groups and len(groups[-1]) + len(s) <= 92:
            groups[-1] += " " + s
        else:
            groups.append(s)
    total = sum(len(g) for g in groups)
    cues: list[tuple[float, float, str]] = []
    t = 0.0
    for i, g in enumerate(groups):
        end = dur if i == len(groups) - 1 else t + dur * len(g) / total
        cues.append((t, end, g))
        t = end
    return cues


def srt_time(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir()
    texts = parse_sections((PRES / "Video_Script.md").read_text("utf-8"))
    missing = [k for k in SCENE_ORDER if k not in texts]
    if missing:
        raise SystemExit(f"Video_Script.md missing sections: {missing}")

    # exact frame count per scene (deterministic A/V alignment)
    frames = {k: max(1, round(MP3(AUDIO / f"{k}.mp3").info.length * FPS))
              for k in SCENE_ORDER}
    tsec = {k: frames[k] / FPS for k in SCENE_ORDER}
    print(f"{len(SCENE_ORDER)} scenes, {sum(frames.values())} frames, "
          f"{sum(tsec.values()):.1f}s total")

    # subtitles on the quantized timeline
    cues: list[tuple[float, float, str]] = []
    t0 = 0.0
    for k in SCENE_ORDER:
        cues += [(t0 + a, t0 + b, txt) for a, b, txt in
                 make_cues(texts[k], tsec[k])]
        t0 += tsec[k]
    srt_lines: list[str] = []
    adj = [list(c) for c in cues]
    for i in range(len(adj) - 1):           # short cues borrow time from next
        dur_i = adj[i][1] - adj[i][0]
        if dur_i < 1.1:
            borrow = 1.1 - dur_i
            if adj[i + 1][1] - adj[i + 1][0] - borrow >= 1.0:
                adj[i][1] += borrow
                adj[i + 1][0] += borrow
    for i, (a, b, txt) in enumerate((tuple(c) for c in adj), 1):
        srt_lines += [str(i), f"{srt_time(a)} --> {srt_time(b)}", txt, ""]
    SRT.write_text("\n".join(srt_lines), encoding="utf-8")

    # video part per scene (exact frame count) + audio part (same length)
    vparts, aparts = [], []
    for k in SCENE_ORDER:
        vp, ap = TMP / f"{k}.mp4", TMP / f"{k}.wav"
        if k == "demo":
            if not DEMO_WEBM.exists():
                raise SystemExit("dashboard_recording.webm missing - run "
                                 "scripts/record_dashboard.py")
            vsrc = ["-i", str(DEMO_WEBM)]
            vfilter = f"fps={FPS},scale={W}:{H},format=yuv420p"
        else:
            img = SLIDES / f"slide_{int(k.split('_')[1]):02d}.png"
            if not img.exists():
                raise SystemExit(f"missing slide image {img}")
            vsrc = ["-loop", "1", "-framerate", str(FPS), "-i", str(img)]
            vfilter = f"scale={W}:{H},format=yuv420p"
        run([str(FFMPEG), "-y", *vsrc, "-frames:v", str(frames[k]),
             "-vf", vfilter, "-c:v", "libx264", "-crf", "23",
             "-preset", "medium", "-r", str(FPS), str(vp)])
        run([str(FFMPEG), "-y", "-i", str(AUDIO / f"{k}.mp3"), "-af", "apad",
             "-t", f"{tsec[k]:.4f}", "-ar", "48000", "-ac", "2",
             "-c:a", "pcm_s16le", str(ap)])
        vparts.append(vp)
        aparts.append(ap)

    def write_list(name: str, paths: list[Path]) -> Path:
        lst = TMP / name
        lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in paths),
                       encoding="utf-8")
        return lst

    run([str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i",
         str(write_list("video.txt", vparts)), "-c", "copy",
         str(TMP / "video_only.mp4")])
    run([str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i",
         str(write_list("audio.txt", aparts)), "-c", "copy",
         str(TMP / "full_audio.wav")])

    # final mux: burn subtitles + AAC audio
    style = ("FontName=Segoe UI,FontSize=16,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,"
             "MarginV=18")
    run([str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i",
         str(TMP / "video.txt"), "-i", str(TMP / "full_audio.wav"),
         "-vf", f"subtitles={SRT.name}:force_style='{style}'",
         "-c:v", "libx264", "-crf", "22", "-preset", "medium",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", str(OUT)], cwd=PRES)

    # verification
    probe = json.loads(run([str(FFPROBE), "-v", "error", "-show_streams",
                            "-show_format", "-of", "json",
                            str(OUT)]).stdout)
    dur = float(probe["format"]["duration"])
    streams = {s["codec_type"]: s for s in probe["streams"]}
    dec = subprocess.run([str(FFMPEG), "-v", "error", "-i", str(OUT),
                          "-f", "null", "-"], check=False, capture_output=True,
                         text=True)
    vol = run([str(FFMPEG), "-i", str(OUT), "-af", "volumedetect",
               "-f", "null", "-"]).stderr
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", vol)
    mx = re.search(r"max_volume: (-?[\d.]+) dB", vol)
    ok_dur = 300 <= dur <= 480
    ok_streams = (streams.get("video", {}).get("codec_name") == "h264"
                  and streams.get("audio", {}).get("codec_name") == "aac")
    av_delta = abs(float(streams["video"]["duration"])
                   - float(streams["audio"]["duration"]))
    ok_dec = dec.returncode == 0 and not dec.stderr.strip()
    ok_vol = mean is not None and float(mean.group(1)) > -40

    print(f"video: {OUT.name}  {OUT.stat().st_size / 1e6:.1f} MB")
    print(f"duration: {dur:.1f}s = {dur / 60:.2f} min  "
          f"(target 300-480s: {'OK' if ok_dur else 'FAIL'})")
    print(f"streams: video={streams.get('video', {}).get('codec_name')} "
          f"audio={streams.get('audio', {}).get('codec_name')}  "
          f"{'OK' if ok_streams else 'FAIL'} (A/V delta {av_delta:.3f}s)")
    print(f"decode pass: {'OK' if ok_dec else 'FAIL ' + dec.stderr[:300]}")
    print(f"audio level: mean {mean.group(1) if mean else '?'} dB, "
          f"max {mx.group(1) if mx else '?'} dB  "
          f"{'OK' if ok_vol else 'FAIL'}")
    if not all((ok_dur, ok_streams, ok_dec, ok_vol, av_delta < 0.5)):
        raise SystemExit("verification FAILED")
    print("verification PASSED")
    shutil.rmtree(TMP)


if __name__ == "__main__":
    sys.exit(main())
