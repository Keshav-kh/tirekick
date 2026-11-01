"""analyze_proof_take: Muse Spark reads the seller's proof video. Owner: B.

The model reports facts; build_report (code) decides. Three runs are merged by majority
vote so one flaky read can't fail or pass a car on its own.
"""

from __future__ import annotations

import logging
import re
import shutil
import statistics
import subprocess
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from tirekick.config import env
from tirekick.models import LightName, LightObservation, Listing, ProofChallenge, ProofTakeAnalysis
from tirekick.verify import muse, prompts
from tirekick.verify.challenge import car_label
from tirekick.verify.muse import image_part, muse_json, text_part
from tirekick.verify.vin import normalize_vin, validate_vin

log = logging.getLogger(__name__)

REPORTED_LIGHTS = [
    LightName.CHECK_ENGINE, LightName.AIRBAG, LightName.ABS, LightName.BATTERY,
    LightName.OIL_PRESSURE, LightName.BRAKE, LightName.TPMS,
]


# --------------------------------------------------------------------------- model output schema


class LightOut(BaseModel):
    light: LightName
    lit_at_key_on: bool | None = None
    on_after_start: bool | None = None
    key_on_timestamp_s: float | None = None
    after_start_timestamp_s: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class TakeObservation(BaseModel):
    """Exactly what one Muse Spark run returns (one sample)."""

    duration_s: float | None = None
    code_read: str | None = None
    code_timestamp_s: float | None = None
    continuous_take: bool = False
    cut_timestamps_s: list[float] = Field(default_factory=list)
    screen_replay_suspected: bool = False
    windshield_vin_read: str | None = None
    windshield_vin_timestamp_s: float | None = None
    door_vin_read: str | None = None
    door_vin_timestamp_s: float | None = None
    key_on_timestamp_s: float | None = None
    engine_start_timestamp_s: float | None = None
    lights: list[LightOut] = Field(default_factory=list)
    odometer_read: int | None = None
    odometer_unit: Literal["mi", "km"] | None = None
    odometer_timestamp_s: float | None = None
    engine_cold: bool | None = None
    temp_gauge_timestamp_s: float | None = None
    model_notes: str = ""


# --------------------------------------------------------------------------- video helpers (ffmpeg)

MAX_FRAMES = 48          # Meta documents a practical ceiling of ~50 images per request
MAX_FPS = 2.0
NATIVE_MAX_BYTES = 20 * 1024 * 1024   # above this (or 60 s) the clip is downscaled before upload
NATIVE_MAX_SECONDS = 60.0

_native_broken: set[str] = set()      # native routes that failed this process ("responses", "chat")


def _ffmpeg_ok() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe_duration(video_path: str) -> float | None:
    """Clip length in seconds via ffprobe, or None if the file isn't a readable video."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", video_path],
            capture_output=True, text=True, timeout=30, check=False,
        )
        return round(float(out.stdout.strip()), 2) if out.returncode == 0 and out.stdout.strip() else None
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


def scene_cuts(video_path: str, threshold: float = 0.5) -> list[float]:
    """Timestamps where ffmpeg's scene score exceeds `threshold` (hard cuts score ~0.6-1.0).
    Logged for the eval only; the C2 decision still comes from the model's report."""
    if not shutil.which("ffmpeg"):
        return []
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", video_path, "-an",
             "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    return [round(float(m), 2) for m in re.findall(r"pts_time:([0-9.]+)", out.stderr)]


def extract_frames(video_path: str, out_dir: Path, fps: float = MAX_FPS,
                   max_frames: int = MAX_FRAMES) -> list[tuple[float, Path]]:
    """ffmpeg -> JPEG frames at `fps`. Returns [(timestamp_s, path)]."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH (needed for MUSE_VIDEO_MODE=frames)")
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", video_path,
         "-vf", f"fps={fps},scale=960:-2", "-q:v", "3", str(out_dir / "f_%04d.jpg")],
        check=True, timeout=180,
    )
    frames = sorted(out_dir.glob("f_*.jpg"))[:max_frames]
    if not frames:
        raise RuntimeError("ffmpeg produced no frames")
    return [(round(i / fps, 2), p) for i, p in enumerate(frames)]


def frames_fps(duration_s: float | None, max_frames: int = MAX_FRAMES) -> float:
    """2 fps for short clips; lower for long ones so the whole clip fits in max_frames."""
    if not duration_s or duration_s <= 0:
        return MAX_FPS
    return round(min(MAX_FPS, max_frames / duration_s), 3)


def prepare_native_video(video_path: str, work_dir: Path, duration_s: float | None) -> str:
    """Downscale to 720p / cap at 60 s when the clip is big or long (B doc gate), else use as is."""
    size = Path(video_path).stat().st_size
    if size <= NATIVE_MAX_BYTES and (duration_s or 0) <= NATIVE_MAX_SECONDS:
        return video_path
    if not shutil.which("ffmpeg"):
        return video_path
    out = work_dir / "native_720p.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", video_path, "-t", str(int(NATIVE_MAX_SECONDS)),
         "-vf", "scale=-2:'min(720,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
         "-c:a", "aac", "-b:a", "64k", str(out)],
        check=True, timeout=180,
    )
    return str(out)


# --------------------------------------------------------------------------- one model run


def _prompt(challenge: ProofChallenge, listing: Listing, frames_note: str) -> str:
    return prompts.PROOF_TAKE_USER.format(car=car_label(listing), code=challenge.code, frames_note=frames_note)


def _run_frames(frames: list[tuple[float, Path]], fps: float, challenge: ProofChallenge, listing: Listing,
                temperature: float) -> TakeObservation:
    parts: list[dict] = [text_part(_prompt(challenge, listing, prompts.FRAMES_NOTE.format(fps=fps)))]
    for t, path in frames:
        parts.append(text_part(f"t={t}s"))
        parts.append(image_part(path))
    messages = [{"role": "system", "content": prompts.PROOF_TAKE_SYSTEM}, {"role": "user", "content": parts}]
    return muse_json(messages, TakeObservation, temperature=temperature, tag="proof_take_frames")


def _run_native(video: str, challenge: ProofChallenge, listing: Listing, temperature: float) -> TakeObservation:
    """Whole clip in one call. Tries the Responses `input_video` block, then the Chat
    Completions `video_url` part; a route that fails once is skipped for the rest of the process."""
    text = _prompt(challenge, listing, prompts.NATIVE_NOTE)
    errors: list[str] = []
    if "responses" not in _native_broken:
        try:
            big = Path(video).stat().st_size > muse.INLINE_LIMIT_BYTES * 0.7  # base64 adds ~33%
            vpart = muse.video_part_responses(file_id=muse.upload_file(video)) if big else muse.video_part_responses(video)
            return muse.responses_json([{"type": "input_text", "text": text}, vpart], TakeObservation,
                                       instructions=prompts.PROOF_TAKE_SYSTEM, temperature=temperature,
                                       tag="proof_take_native")
        except muse.MuseError as e:
            if "no valid JSON" not in str(e):
                _native_broken.add("responses")
            errors.append(f"responses: {e}")
    if "chat" not in _native_broken:
        try:
            messages = [{"role": "system", "content": prompts.PROOF_TAKE_SYSTEM},
                        {"role": "user", "content": [text_part(text), muse.video_part_chat(video)]}]
            return muse_json(messages, TakeObservation, temperature=temperature, tag="proof_take_native_chat")
        except muse.MuseError as e:
            if "no valid JSON" not in str(e):
                _native_broken.add("chat")
            errors.append(f"chat: {e}")
    raise muse.MuseError("native video failed: " + " | ".join(errors or ["all native routes disabled"]))


# --------------------------------------------------------------------------- merging runs# --------------------------------------------------------------------------- merging runs


def _majority(values: list):
    """Most common non-None value; None if nothing or a tie for first place."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    counts = Counter(vals).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return None
    return counts[0][0]


def _median(values: list[float | int | None]):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _norm_code(code: str | None) -> str | None:
    return code.strip().upper().replace(" ", "") if code else None


def _best_vin(reads: list[str | None]) -> str | None:
    cands = [normalize_vin(r) for r in reads if r]
    valid = [c for c in cands if validate_vin(c)[0]]
    return _majority(valid) or (valid[0] if valid else None) or _majority(cands) or (cands[0] if cands else None)


def merge_observations(obs: list[TakeObservation], video_path: str, challenge: ProofChallenge) -> ProofTakeAnalysis:
    codes = [_norm_code(o.code_read) for o in obs]
    code_read = challenge.code if challenge.code in codes else _majority(codes)

    lights: list[LightObservation] = []
    agree_pairs = total_pairs = 0
    for name in REPORTED_LIGHTS:
        per_run = [next((l for l in o.lights if l.light == name), None) for o in obs]
        seen = [l for l in per_run if l is not None]
        if not seen:
            continue
        key_on = [l.lit_at_key_on if l else None for l in per_run]
        after = [l.on_after_start if l else None for l in per_run]
        for field_vals in (key_on, after):
            if any(v is not None for v in field_vals):
                total_pairs += 1
                if None not in field_vals and len(set(field_vals)) == 1:
                    agree_pairs += 1
        lights.append(LightObservation(
            light=name,
            lit_at_key_on=_majority(key_on),
            on_after_start=_majority(after),
            key_on_timestamp_s=_median([l.key_on_timestamp_s for l in seen]),
            after_start_timestamp_s=_median([l.after_start_timestamp_s for l in seen]),
            confidence=round(sum(l.confidence for l in seen) / len(seen), 3),
        ))

    odometer = _median([o.odometer_read for o in obs])
    notes = " | ".join(dict.fromkeys(o.model_notes for o in obs if o.model_notes))
    return ProofTakeAnalysis(
        video_path=video_path,
        duration_s=max((o.duration_s for o in obs if o.duration_s is not None), default=None),
        code_read=code_read,
        code_matches=code_read == challenge.code,
        code_timestamp_s=_median([o.code_timestamp_s for o in obs]),
        continuous_take=all(o.continuous_take for o in obs),
        cut_timestamps_s=sorted({t for o in obs for t in o.cut_timestamps_s}),
        screen_replay_suspected=bool(_majority([o.screen_replay_suspected for o in obs])),
        windshield_vin_read=_best_vin([o.windshield_vin_read for o in obs]),
        windshield_vin_timestamp_s=_median([o.windshield_vin_timestamp_s for o in obs]),
        door_vin_read=_best_vin([o.door_vin_read for o in obs]),
        door_vin_timestamp_s=_median([o.door_vin_timestamp_s for o in obs]),
        lights=lights,
        key_on_timestamp_s=_median([o.key_on_timestamp_s for o in obs]),
        engine_start_timestamp_s=_median([o.engine_start_timestamp_s for o in obs]),
        odometer_read=int(odometer) if odometer is not None else None,
        odometer_unit=_majority([o.odometer_unit for o in obs]),
        odometer_timestamp_s=_median([o.odometer_timestamp_s for o in obs]),
        engine_cold=_majority([o.engine_cold for o in obs]),
        temp_gauge_timestamp_s=_median([o.temp_gauge_timestamp_s for o in obs]),
        model_notes=notes,
        runs=len(obs),
        agreement=round(agree_pairs / total_pairs, 3) if total_pairs else 1.0,
        raw_outputs=[o.model_dump(mode="json") for o in obs],
    )


def video_mode() -> str:
    mode = env("MUSE_VIDEO_MODE", "frames").strip().lower()
    return mode if mode in {"native", "frames"} else "frames"


def _empty(video_path: str, duration: float | None, note: str) -> ProofTakeAnalysis:
    return ProofTakeAnalysis(video_path=video_path, duration_s=duration, runs=0, agreement=0.0,
                             model_notes=f"analysis failed: {note}"[:1000])


def analyze_proof_take(video_path: str, challenge: ProofChallenge, listing: Listing, runs: int = 3) -> ProofTakeAnalysis:
    """Never raises on a bad video: failed runs are skipped; if all fail, returns an empty analysis
    (runs=0), which build_report turns into one red "couldn't be analyzed" item."""
    try:
        return _analyze(video_path, challenge, listing, max(1, runs))
    except Exception as e:  # noqa: BLE001 - last line of defence for the contract
        log.exception("analyze_proof_take crashed")
        return _empty(video_path, None, repr(e))


def _analyze(video_path: str, challenge: ProofChallenge, listing: Listing, runs: int) -> ProofTakeAnalysis:
    if not Path(video_path).is_file():
        return _empty(video_path, None, "video file not found")
    duration = probe_duration(video_path)
    if duration is None and _ffmpeg_ok():
        return _empty(video_path, None, "not a readable video (ffprobe failed)")

    mode = video_mode()
    temperature = 0.3 if runs > 1 else 0.2
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="tk_proof_") as tmp:
        work = Path(tmp)
        native_video: str | None = None
        frames: list[tuple[float, Path]] | None = None
        fps = frames_fps(duration)
        if mode == "native":
            try:
                native_video = prepare_native_video(video_path, work, duration)
            except Exception as e:  # noqa: BLE001
                errors.append(f"prepare native: {e}")

        lock = threading.Lock()

        def get_frames() -> list[tuple[float, Path]]:
            nonlocal frames
            with lock:  # parallel runs that fall back from native share one extraction
                if frames is None:
                    frames = extract_frames(video_path, work / "frames", fps=fps)
                return frames

        def one_run(_: int) -> tuple[TakeObservation | None, str]:
            if native_video is not None:
                try:
                    return _run_native(native_video, challenge, listing, temperature), "native"
                except Exception as e:  # noqa: BLE001 - fall back to frames automatically
                    errors.append(f"native: {e}")
            try:
                return _run_frames(get_frames(), fps, challenge, listing, temperature), "frames"
            except Exception as e:  # noqa: BLE001
                errors.append(f"frames: {e}")
                return None, "failed"

        if native_video is None:
            try:
                get_frames()  # extract once, before the parallel runs share them
            except Exception as e:  # noqa: BLE001
                return _empty(video_path, duration, f"frame extraction failed: {e}")
        with ThreadPoolExecutor(max_workers=min(runs, 3)) as pool:
            results = list(pool.map(one_run, range(runs)))

    observations = [o for o, _ in results if o is not None]
    muse.log_run("proof_take_summary", {
        "video": video_path, "duration_s": duration, "mode_requested": mode,
        "modes_used": [m for _, m in results], "fps": fps if frames is not None else None,
        "ffmpeg_scene_cuts_s": scene_cuts(video_path), "errors": errors,
    })
    if not observations:
        return _empty(video_path, duration, "; ".join(errors) or "no runs succeeded")
    analysis = merge_observations(observations, video_path, challenge)
    if duration is not None:
        analysis.duration_s = duration  # ffprobe is a fact; the model's estimate is not
    return analysis
