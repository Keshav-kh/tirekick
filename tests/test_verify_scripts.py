"""scripts/day1_test.py and scripts/verify_clip.py run end to end in fake mode (no key, no network)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(script, *args, tmp_path, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k not in ("META_API_KEY", "MODEL_API_KEY")}
    env.update({"TIREKICK_DATA_DIR": str(tmp_path / "data"), **(env_extra or {})})
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def test_day1_fake_mode_prints_gates(tmp_path):
    r = run("day1_test.py", "--clips", "tests/fixtures/day1_sample.csv", "--runs", "2", "--fake", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "FAKE MODE" in r.stdout and "Lights: GO" in r.stdout and "| cold_honest_01.mp4 |" in r.stdout
    assert list((tmp_path / "data" / "runs").glob("day1_*.json"))


def test_day1_refuses_real_mode_without_key(tmp_path):
    r = run("day1_test.py", "--clips", "tests/fixtures/day1_sample.csv", tmp_path=tmp_path,
            env_extra={"TIREKICK_FAKE_AI": "0"})
    assert r.returncode != 0 and "META_API_KEY" in r.stderr


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_verify_clip_fake_mode_on_synthetic_clip(tmp_path):
    clip = tmp_path / "synthetic_cut.mp4"
    assert run("make_synthetic_clip.py", "--out", str(clip), tmp_path=tmp_path).returncode == 0
    r = run("verify_clip.py", "--video", str(clip), "--code", "K7Q2XM", "--listing", "samples/listing.json",
            "--fake", "--out", str(tmp_path / "report.json"), tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "VERDICT: YELLOW" in r.stdout and "ffmpeg_scene_cuts=[6.0]" in r.stdout
    assert (tmp_path / "report.json").exists()
