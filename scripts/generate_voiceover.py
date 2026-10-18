"""Synthesize narration audio — one file per Video_Script.md section.

Uses edge-tts (en-US-ChristopherNeural, rate +15% to fit the 5-8 minute
budget); falls back to offline pyttsx3 if edge-tts fails (no network).
Sections are parsed from presentation/Video_Script.md; MP3s land in
presentation/audio/.

Run:  .venv\\Scripts\\python.exe scripts\\generate_voiceover.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_MD = ROOT / "presentation" / "Video_Script.md"
OUT_DIR = ROOT / "presentation" / "audio"
VOICE = "en-US-ChristopherNeural"
RATE = "+15%"


def parse_sections(md: str) -> list[tuple[str, str]]:
    """Return [(key, text)] — key like 'slide_01' or 'demo'."""
    sections: list[tuple[str, str]] = []
    current: tuple[str, list[str]] | None = None
    for line in md.splitlines():
        if line.startswith("## "):
            if current:
                sections.append((current[0], " ".join(current[1]).strip()))
            title = line[3:].strip()
            m = re.match(r"Slide (\d+)", title)
            key = f"slide_{int(m.group(1)):02d}" if m else "demo"
            current = (key, [])
        elif current is not None and line.strip():
            current[1].append(line.strip())
    if current:
        sections.append((current[0], " ".join(current[1]).strip()))
    return sections


async def tts_edge(text: str, out: Path) -> None:
    import edge_tts

    for attempt in range(3):
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(out))
            if out.stat().st_size > 1000:
                return
        except Exception as exc:  # noqa: BLE001 - retry any network/codec error
            print(f"  edge-tts attempt {attempt + 1} failed: {exc}")
            await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError(f"edge-tts failed for {out.name}")


def tts_pyttsx3(text: str, out: Path) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    engine.save_to_file(text, str(out))
    engine.runAndWait()


def main() -> None:
    sections = parse_sections(SCRIPT_MD.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_words = 0
    for key, text in sections:
        total_words += len(text.split())
        out = OUT_DIR / f"{key}.mp3"
        print(f"{key}: {len(text.split())} words -> {out.name}")
        try:
            asyncio.run(tts_edge(text, out))
            engine = "edge-tts"
        except Exception as exc:  # noqa: BLE001
            print(f"  falling back to pyttsx3 ({exc})")
            out_wav = OUT_DIR / f"{key}.wav"
            tts_pyttsx3(text, out_wav)
            out = out_wav
            engine = "pyttsx3"
        print(f"  ok via {engine}, {out.stat().st_size / 1024:.0f} KB")
    print(f"done: {len(sections)} files, {total_words} words "
          f"(~{total_words / 160:.1f} min at 160 wpm)")


if __name__ == "__main__":
    sys.exit(main())
