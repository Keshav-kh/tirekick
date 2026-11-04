"""SAM 3.1 highlights (B11): wire-format parsing, drawing, and graceful failure. Mocked stream."""

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from tirekick.models import Evidence, EvidenceSource, EvidenceType, Severity
from tirekick.verify import highlight, muse
from tirekick.verify.highlight import concept_for, draw_boxes, highlight_evidence, parse_boxes

# Real SAM 3.1 output shape (from Meta's meta-sam protocol docs), two objects, one with confidence.
SAM_TEXT = ("<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=240;c=0.91|>"
            "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
            ",1<|box;x1=15;y1=20;x2=60;y2=50;w=320;h=240|><|mask;x=0;y=0;data=5,5,!!!!!(QO(0lu8?|>\n")
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def ev(type_, summary, frame=None, source=EvidenceSource.VIDEO):
    return Evidence(id="EV-01", type=type_, severity=Severity.RED, summary=summary, source=source,
                    frame_path=frame)


def test_parse_boxes_reads_fields_by_name_and_ignores_masks():
    boxes = parse_boxes(SAM_TEXT)
    assert [(b.x1, b.y1, b.x2, b.y2, b.w, b.h) for b in boxes] == [(211, 228, 270, 254, 320, 240),
                                                                   (15, 20, 60, 50, 320, 240)]
    assert boxes[0].confidence == 0.91 and boxes[1].confidence is None
    assert parse_boxes("") == [] and parse_boxes("<0f>0<|box;x1=1|>") == []
    assert parse_boxes("<0f>0<|box;y2=4;x2=3;h=8;w=8;y1=1;x1=0;extra=z|>")[0].x2 == 3


def test_concepts():
    assert concept_for(ev(EvidenceType.WARNING_LIGHT_HIDDEN,
                          "The check-engine light didn't come on at key-on (bulb check).")) == \
        "check engine warning light icon"
    assert concept_for(ev(EvidenceType.WARNING_LIGHT_ON, "The ABS light stays on after the engine starts.")) == \
        "ABS warning light icon"
    assert concept_for(ev(EvidenceType.WARNING_LIGHT_HIDDEN,
                          "The key-on bulb check (all warning lights on) wasn't clearly shown.")) is None
    assert concept_for(ev(EvidenceType.VIN_MISMATCH_DOORS, "x")) == "VIN sticker"
    assert concept_for(ev(EvidenceType.VIN_LISTING_MISMATCH, "x", source=EvidenceSource.VIN_DECODE)) is None
    assert concept_for(ev(EvidenceType.RECALL_FOUND, "x")) is None


@pytest.fixture
def frame(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("needs ffmpeg")
    path = tmp_path / "EV-01.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=640x480",
                    "-frames:v", "1", str(path)], check=True)
    return str(path)


@needs_ffmpeg
def test_draw_boxes_scales_to_the_frame(frame, tmp_path):
    out = tmp_path / "EV-01_hl.jpg"
    assert draw_boxes(frame, parse_boxes(SAM_TEXT), out) and out.stat().st_size > 0
    assert not draw_boxes(frame, [], tmp_path / "none.jpg")


def sam_stream(text, via="content_part"):
    events = [SimpleNamespace(type="response.output_text.delta", model_dump=lambda: {"delta": text})]
    if via == "content_part":
        events.append(SimpleNamespace(type="response.content_part.done",
                                      model_dump=lambda: {"part": {"type": "output_text", "text": text}}))
    return iter(events)


@pytest.fixture
def sam(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "test-key")
    calls = []

    def install(make):
        def create(**kw):
            calls.append(kw)
            return make()
        monkeypatch.setattr(muse, "_client", SimpleNamespace(responses=SimpleNamespace(create=create)))
        return calls
    return install


@needs_ffmpeg
def test_highlight_evidence_sets_highlight_path(sam, frame):
    calls = sam(lambda: sam_stream(SAM_TEXT))
    e = ev(EvidenceType.WARNING_LIGHT_HIDDEN, "The check-engine light didn't come on at key-on (bulb check).", frame)
    report = SimpleNamespace(evidence=[e])
    highlight_evidence(report)
    assert e.highlight_path and e.highlight_path.endswith("EV-01_hl.jpg")
    kw = calls[0]
    assert kw["model"] == "sam-3.1" and kw["stream"] is True
    content = kw["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "check engine warning light icon"}
    assert content[1]["type"] == "input_image" and content[1]["image_url"].startswith("data:image/jpeg;base64,")


@needs_ffmpeg
def test_deltas_only_stream_still_parses(sam, frame):
    sam(lambda: sam_stream(SAM_TEXT, via="deltas"))
    e = ev(EvidenceType.VIN_INVALID, "x", frame)
    highlight_evidence(SimpleNamespace(evidence=[e]))
    assert e.highlight_path


@needs_ffmpeg
def test_failures_leave_highlight_none(sam, frame, monkeypatch):
    monkeypatch.setattr(muse, "_sleep", lambda s: None)

    def boom():
        raise muse.MuseError("sam down")
    sam(boom)
    e = ev(EvidenceType.VIN_INVALID, "x", frame)
    highlight_evidence(SimpleNamespace(evidence=[e]))
    assert e.highlight_path is None
    sam(lambda: sam_stream(""))                          # zero matches is a valid empty answer
    highlight_evidence(SimpleNamespace(evidence=[e]))
    assert e.highlight_path is None


def test_skipped_without_key(monkeypatch):
    monkeypatch.setattr(highlight, "segment_boxes", lambda *a: pytest.fail("called without a key"))
    highlight_evidence(SimpleNamespace(evidence=[ev(EvidenceType.VIN_INVALID, "x", "f.jpg")]))
