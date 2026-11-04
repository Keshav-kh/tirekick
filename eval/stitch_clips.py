"""Stitch the AI-generated proof-take pieces into full test clips. Owner: C.

  pip install imageio-ffmpeg        # bundles an ffmpeg binary, no Homebrew needed
  python eval/stitch_clips.py

Expects these pieces in eval/data/clips/ (downloaded from Higgsfield):
  paper.mp4  sticker.mp4  odometer.mp4  dash_honest.mp4  dash_hidden.mp4  [dash_honest2.mp4]
Writes the aigen_*.mp4 test clips next to them. Every output is AI-generated and stitched,
so it contains cuts by construction; label it that way in RESULTS.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CLIPS = Path(__file__).resolve().parent / "data" / "clips"

RECIPES = {
    "aigen_honest_01.mp4": ["paper", "sticker", "odometer", "dash_honest"],
    "aigen_hidden_01.mp4": ["paper", "sticker", "odometer", "dash_hidden"],
    "aigen_nocode_01.mp4": ["sticker", "odometer", "dash_honest"],
    "aigen_honest_02.mp4": ["paper", "sticker", "odometer", "dash_honest2"],
    "aigen_nocode_02.mp4": ["sticker", "odometer", "dash_hidden"],
}


def ffmpeg() -> str:
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("Run first: pip install imageio-ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


def stitch(out: str, parts: list[str], exe: str) -> None:
    files = [CLIPS / f"{p}.mp4" for p in parts]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        print(f"skip {out}: missing {', '.join(missing)}")
        return
    inputs = sum((["-i", str(f)] for f in files), [])
    # Normalise every piece to 1280x720 @ 30 fps so pieces with different sizes join cleanly.
    norm = "".join(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
                   f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[v{i}];" for i in range(len(files)))
    chain = "".join(f"[v{i}]" for i in range(len(files)))
    cmd = [exe, "-y", "-loglevel", "error", *inputs, "-filter_complex",
           f"{norm}{chain}concat=n={len(files)}:v=1:a=0[out]", "-map", "[out]",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(CLIPS / out)]
    subprocess.run(cmd, check=True)
    print(f"wrote {out}  ({' -> '.join(parts)})")


def main() -> None:
    exe = ffmpeg()
    for out, parts in RECIPES.items():
        stitch(out, parts, exe)


if __name__ == "__main__":
    main()
