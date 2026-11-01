"""Make a ~10 s synthetic proof clip for smoke tests (no car needed). Owner: B.

  python scripts/make_synthetic_clip.py                      # data/clips/synthetic_cut.mp4
  python scripts/make_synthetic_clip.py --no-cut --out data/clips/synthetic_nocut.mp4

Scene 1 (0-6 s): a white "paper card" with the challenge code in large text and a VIN plate
strip below it, drifting slightly like a handheld phone. Scene 2 (6-10 s): one HARD CUT to an
unrelated dark scene with a moving test pattern. With --no-cut the card scene runs the whole time
(a control clip that should come back continuous_take=true).

Expected reads: code_read == K7Q2XM, windshield_vin_read == 1HGCM82633A004352 (valid check
digit), continuous_take == false with a cut near 6 s. Videos never go in git (data/ is ignored).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def find_font(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    return next((f for f in FONT_CANDIDATES if Path(f).exists()), None)


def _esc(path: str) -> str:
    # drawtext option values: escape the characters ffmpeg's filter parser treats specially
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def build_command(out: str, code: str, vin: str, font: str | None, cut_at: float, total: float,
                  cut: bool) -> list[str]:
    fontopt = f"fontfile='{_esc(font)}':" if font else ""
    w, h = 1280, 720
    # Handheld drift: offset text by a few pixels with a slow sine.
    dx, dy = "12*sin(2*PI*t/3)", "8*sin(2*PI*t/2.3)"
    card = (
        f"drawbox=x=140+{dx}:y=90+{dy}:w=1000:h=330:color=white@1:t=fill,"
        f"drawtext={fontopt}text='CODE':fontsize=48:fontcolor=gray:x=180+{dx}:y=110+{dy},"
        f"drawtext={fontopt}text='{code}':fontsize=200:fontcolor=black:x=(w-text_w)/2+{dx}:y=170+{dy},"
        f"drawbox=x=90+{dx}:y=470+{dy}:w=1100:h=150:color=0x2b2b2b@1:t=fill,"
        f"drawtext={fontopt}text='VIN {vin}':fontsize=64:fontcolor=white:x=(w-text_w)/2+{dx}:y=515+{dy}"
    )
    scene1_len = cut_at if cut else total
    inputs = ["-f", "lavfi", "-i", f"color=c=0x6b7b8c:s={w}x{h}:r=30:d={scene1_len}"]
    if cut:
        inputs += ["-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=30:d={total - cut_at}"]
        graph = (
            f"[0:v]{card},format=yuv420p[a];"
            f"[1:v]eq=brightness=-0.35:saturation=0.4,"
            f"drawtext={fontopt}text='DASHBOARD':fontsize=90:fontcolor=white:x=(w-text_w)/2:y=60,"
            f"format=yuv420p[b];[a][b]concat=n=2:v=1:a=0[v]"
        )
    else:
        graph = f"[0:v]{card},format=yuv420p[v]"
    return ["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", out]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/clips/synthetic_cut.mp4")
    ap.add_argument("--code", default="K7Q2XM")
    ap.add_argument("--vin", default="1HGCM82633A004352")
    ap.add_argument("--cut-at", type=float, default=6.0, help="seconds into the clip where the hard cut happens")
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--no-cut", action="store_true", help="one continuous scene (control clip)")
    ap.add_argument("--font", help="path to a .ttf font for drawtext")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH (macOS: brew install ffmpeg; Debian/Ubuntu: apt-get install ffmpeg)")
    if not 0 < args.cut_at < args.duration:
        sys.exit("--cut-at must be inside the clip")
    font = find_font(args.font)
    if font is None:
        print("warning: no font found; ffmpeg will try its default (pass --font if drawtext fails)")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(args.out, args.code.upper(), args.vin.upper(), font, args.cut_at, args.duration,
                        cut=not args.no_cut)
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(f"ffmpeg failed (exit {result.returncode})")
    kind = "continuous (no cut)" if args.no_cut else f"hard cut at {args.cut_at:g}s"
    print(f"wrote {args.out}: {args.duration:g}s, code {args.code.upper()}, VIN {args.vin.upper()}, {kind}")


if __name__ == "__main__":
    main()
