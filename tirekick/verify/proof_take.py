"""analyze_proof_take: Muse Spark reads the seller's proof video. Owner: B.

The model reports facts; build_report (code) decides. Three runs are merged by majority
vote so one flaky read can't fail or pass a car on its own.
"""

from __future__ import annotations

import shutil
import statistics
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from tirekick.config import env
from tirekick.models import LightName, LightObservation, Listing, ProofChallenge, ProofTakeAnalysis
from tirekick.verify import prompts
from tirekick.verify.challenge import car_label
from tirekick.verify.muse import image_part, muse_json, text_part
from tirekick.verify.vin import normalize_vin, validate_vin

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


# --------------------------------------------------------------------------- frames mode


def extract_frames(video_path: str, out_dir: Path, fps: float = 2.0, max_frames: int = 120) -> list[tuple[float, Path]]:
    """ffmpeg -> JPEG frames at `fps`. Returns [(timestamp_s, path)]."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH (needed for MUSE_VIDEO_MODE=frames)")
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", video_path,
         "-vf", f"fps={fps},scale=960:-2", str(out_dir / "f_%04d.jpg")],
        check=True,
    )
    frames = sorted(out_dir.glob("f_*.jpg"))[:max_frames]
    return [(round(i / fps, 2), p) for i, p in enumerate(frames)]


def _messages(video_path: str, challenge: ProofChallenge, listing: Listing, work_dir: Path) -> list[dict]:
    mode = env("MUSE_VIDEO_MODE", "frames")
    if mode == "native":
        # TODO(B, day 1): fill in once Meta's video input format is confirmed
        # (docs/workstream-B-intelligence.md section 2.1), then return a single user message
        # containing the video part plus the prompt text.
        raise NotImplementedError("MUSE_VIDEO_MODE=native not wired yet; use frames")
    fps = 2.0
    frames = extract_frames(video_path, work_dir, fps=fps)
    user_text = prompts.PROOF_TAKE_USER.format(
        car=car_label(listing), code=challenge.code,
        frames_note=prompts.FRAMES_NOTE.format(fps=fps),
    )
    parts: list[dict] = [text_part(user_text)]
    for t, path in frames:
        parts.append(text_part(f"t={t}s"))
        parts.append(image_part(path))
    return [{"role": "system", "content": prompts.PROOF_TAKE_SYSTEM}, {"role": "user", "content": parts}]


def _run_once(video_path: str, challenge: ProofChallenge, listing: Listing, temperature: float) -> TakeObservation:
    with tempfile.TemporaryDirectory(prefix="tk_frames_") as tmp:
        messages = _messages(video_path, challenge, listing, Path(tmp))
        return muse_json(messages, TakeObservation, temperature=temperature, tag="proof_take")


# --------------------------------------------------------------------------- merging runs


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


def analyze_proof_take(video_path: str, challenge: ProofChallenge, listing: Listing, runs: int = 3) -> ProofTakeAnalysis:
    """Never raises on a bad video: failed runs are skipped; if all fail, returns an empty analysis."""
    observations: list[TakeObservation] = []
    errors: list[str] = []
    for _ in range(runs):
        try:
            observations.append(_run_once(video_path, challenge, listing, temperature=0.3))
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
    if not observations:
        return ProofTakeAnalysis(video_path=video_path, runs=0, model_notes="analysis failed: " + "; ".join(errors))
    return merge_observations(observations, video_path, challenge)
