"""analyze_proof_take: never raises, frames mode, native mode, automatic native -> frames fallback.

Uses the synthetic clip from scripts/make_synthetic_clip.py (needs ffmpeg) and a mocked model.
"""

import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from _fixtures import challenge

from tirekick.models import LightName, Listing
from tirekick.verify import muse, proof_take
from tirekick.verify.proof_take import LightOut, TakeObservation, analyze_proof_take, frames_fps

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg")
LISTING = Listing(listing_id="L", asking_price=4800, year=2003, make="Honda", model="Accord")
VIN = "1HGCM82633A004352"


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    out = tmp_path_factory.mktemp("clips") / "synthetic_cut.mp4"
    script = Path(__file__).resolve().parents[1] / "scripts" / "make_synthetic_clip.py"
    subprocess.run([sys.executable, str(script), "--out", str(out)], check=True, capture_output=True)
    return str(out)


@pytest.fixture(autouse=True)
def reset_native(monkeypatch):
    monkeypatch.setattr(proof_take, "_native_broken", set())


def obs(**kw):
    base = dict(code_read="K7Q2XM", continuous_take=False, cut_timestamps_s=[6.0], windshield_vin_read=VIN,
                lights=[LightOut(light=LightName.CHECK_ENGINE, lit_at_key_on=None, confidence=0.1)],
                duration_s=99.0)
    base.update(kw)
    return TakeObservation(**base)


def test_missing_file_never_raises():
    a = analyze_proof_take("does/not/exist.mp4", challenge(), LISTING)
    assert a.runs == 0 and "not found" in a.model_notes


@needs_ffmpeg
def test_non_video_file_never_raises(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_text("this is not a video")
    a = analyze_proof_take(str(bad), challenge(), LISTING)
    assert a.runs == 0 and a.model_notes.startswith("analysis failed")


def test_frames_fps_respects_image_budget():
    assert frames_fps(10) == 2.0
    assert frames_fps(60) == pytest.approx(0.8)
    assert frames_fps(None) == 2.0
    assert 60 * frames_fps(60) <= proof_take.MAX_FRAMES


@needs_ffmpeg
def test_scene_cut_probe_finds_the_hard_cut(clip):
    cuts = proof_take.scene_cuts(clip)
    assert len(cuts) == 1 and abs(cuts[0] - 6.0) < 0.2


@needs_ffmpeg
def test_frames_mode_end_to_end_with_mocked_model(clip, monkeypatch):
    monkeypatch.setenv("MUSE_VIDEO_MODE", "frames")
    seen, threads = [], set()

    def fake_json(messages, schema, **kw):
        threads.add(threading.get_ident())
        seen.append(messages)
        return obs()
    monkeypatch.setattr(proof_take, "muse_json", fake_json)
    a = analyze_proof_take(clip, challenge(), LISTING, runs=3)
    assert a.runs == 3 and a.code_matches and a.windshield_vin_read == VIN
    assert a.continuous_take is False and a.cut_timestamps_s == [6.0]
    assert a.duration_s == pytest.approx(10.0, abs=0.1)        # ffprobe, not the model's 99 s
    parts = seen[0][1]["content"]
    stamps = [p["text"] for p in parts if p["type"] == "text" and p["text"].startswith("t=")]
    images = [p for p in parts if p["type"] == "image_url"]
    assert len(images) == len(stamps) == 20 and stamps[:3] == ["t=0.0s", "t=0.5s", "t=1.0s"]
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert seen[0][0]["role"] == "system" and "K7Q2XM" in parts[0]["text"]


@needs_ffmpeg
def test_native_mode_sends_input_video(clip, monkeypatch):
    monkeypatch.setenv("MUSE_VIDEO_MODE", "native")
    sent = []

    def fake_responses(content, schema, **kw):
        sent.append(content)
        return obs()
    monkeypatch.setattr(muse, "responses_json", fake_responses)
    monkeypatch.setattr(proof_take, "muse_json", lambda *a, **k: pytest.fail("frames used"))
    a = analyze_proof_take(clip, challenge(), LISTING, runs=1)
    assert a.runs == 1 and a.code_matches
    video = [p for p in sent[0] if p["type"] == "input_video"][0]
    assert video["video_url"].startswith("data:video/mp4;base64,")


@needs_ffmpeg
def test_native_failure_falls_back_to_frames(clip, monkeypatch):
    monkeypatch.setenv("MUSE_VIDEO_MODE", "native")
    calls = {"responses": 0, "chat_video": 0, "frames": 0}

    def bad_responses(*a, **k):
        calls["responses"] += 1
        raise muse.MuseError("proof_take_native: model call failed: 400 input_video not supported")

    def chat_json(messages, schema, **kw):
        if any(p.get("type") == "video_url" for p in messages[1]["content"]):
            calls["chat_video"] += 1
            raise muse.MuseError("proof_take_native_chat: model call failed: 400 video_url")
        calls["frames"] += 1
        return obs()
    monkeypatch.setattr(muse, "responses_json", bad_responses)
    monkeypatch.setattr(proof_take, "muse_json", chat_json)
    a = analyze_proof_take(clip, challenge(), LISTING, runs=3)
    assert a.runs == 3 and a.code_matches
    assert calls["frames"] == 3
    assert calls["responses"] <= 3 and calls["chat_video"] <= 3       # broken routes are remembered
    assert proof_take._native_broken == {"responses", "chat"}
    a = analyze_proof_take(clip, challenge(), LISTING, runs=1)        # later clips skip native entirely
    assert calls["responses"] <= 3 and a.runs == 1


@needs_ffmpeg
def test_all_runs_failing_returns_empty_analysis(clip, monkeypatch):
    monkeypatch.setenv("MUSE_VIDEO_MODE", "frames")

    def boom(*a, **k):
        raise muse.MuseError("503 after retries")
    monkeypatch.setattr(proof_take, "muse_json", boom)
    a = analyze_proof_take(clip, challenge(), LISTING, runs=2)
    assert a.runs == 0 and "503" in a.model_notes and a.duration_s == pytest.approx(10.0, abs=0.1)


@needs_ffmpeg
def test_one_failed_run_is_skipped(clip, monkeypatch):
    monkeypatch.setenv("MUSE_VIDEO_MODE", "frames")
    n = {"i": 0}
    lock = threading.Lock()

    def flaky(*a, **k):
        with lock:
            n["i"] += 1
            i = n["i"]
        if i == 2:
            raise muse.MuseError("timeout")
        return obs()
    monkeypatch.setattr(proof_take, "muse_json", flaky)
    assert analyze_proof_take(clip, challenge(), LISTING, runs=3).runs == 2
