"""SAM 3.1 evidence highlights for the report frames (stretch, B11). Owner: B.

For each evidence frame (data/frames/{deal}/{EV-xx}.jpg) we ask SAM 3.1 (Meta Model API, Responses
API, model `sam-3.1`) to segment one short noun phrase, e.g. "VIN plate". The request shape and
the output grammar are Meta's own (meta-models/meta-model-cookbook 07_sam, meta-sam protocol):

  request : responses.create(model="sam-3.1", stream=True, input=[{"type": "message", "role": "user",
            "content": [{"type": "input_text", "text": phrase},
                        {"type": "input_image", "image_url": "data:image/jpeg;base64,..."}]}])
  output  : one output_text lane, one line per frame:
            <0f>0<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..[;c=..]|><|mask;x=0;y=0;data=H,W,~...|>,1<|box;...|>...

We only need the boxes (inclusive x2/y2, source pixels), so we read the box tokens and ignore the
base85 masks; no extra dependency. Boxes are drawn with ffmpeg into {EV-xx}_hl.jpg. Any failure
leaves highlight_path None: the report works without highlights.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from tirekick.config import env
from tirekick.models import Evidence, VerificationReport
from tirekick.verify import muse

log = logging.getLogger(__name__)

CONCEPT_PROMPTS = {
    "vin_unreadable": "VIN plate",
    "vin_invalid": "VIN plate",
    "vin_mismatch_doors": "VIN sticker",
    "vin_listing_mismatch": "VIN plate",
    "warning_light_hidden": "check engine warning light icon",
    "warning_light_on": "illuminated warning light icon",
    "odometer_mismatch": "odometer digits",
    "engine_warm": "temperature gauge needle",
}
LIGHT_PHRASES = {
    "check-engine": "check engine warning light icon", "airbag": "airbag warning light icon",
    "ABS": "ABS warning light icon", "battery": "battery warning light icon",
    "oil-pressure": "oil pressure warning light icon", "brake": "brake warning light icon",
    "tire-pressure": "tire pressure warning light icon", "coolant": "coolant temperature warning light icon",
}
MAX_FRAMES = 6
MAX_BOXES = 3
BOX_TOKEN = re.compile(r"<\|box;([^|]*)\|>")


@dataclass
class Box:
    x1: int
    y1: int
    x2: int          # inclusive, as on the wire
    y2: int
    w: int
    h: int
    confidence: float | None = None


def sam_model() -> str:
    return env("SAM_MODEL", "sam-3.1")


def concept_for(e: Evidence) -> str | None:
    """Noun phrase for this evidence item, or None if it has nothing to highlight."""
    if e.type.value in ("warning_light_hidden", "warning_light_on"):
        if "wasn't clearly shown" in e.summary:
            return None
        for label, phrase in LIGHT_PHRASES.items():
            if f"The {label} light" in e.summary:
                return phrase
    if e.type.value == "vin_listing_mismatch" and e.source.value != "video":
        return None   # decode/listing mismatch: the frame proves nothing more
    return CONCEPT_PROMPTS.get(e.type.value)


def parse_boxes(text: str) -> list[Box]:
    """Box tokens from SAM output text (fields read by name; order and unknown keys don't matter)."""
    boxes: list[Box] = []
    for m in BOX_TOKEN.finditer(text or ""):
        fields: dict[str, str] = {}
        for part in m.group(1).split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k.strip()] = v.strip()
        try:
            c = fields.get("c")
            conf = float(c) if c is not None else None
            if conf is not None and not 0 <= conf <= 1:
                conf = None
            boxes.append(Box(int(fields["x1"]), int(fields["y1"]), int(fields["x2"]), int(fields["y2"]),
                             int(fields["w"]), int(fields["h"]), conf))
        except (KeyError, ValueError):
            continue
    return boxes


def _stream_text(stream) -> str:
    """Collect the output_text lane from streamed Responses events. The live SAM API finalizes the lane
    with response.content_part.done (not response.output_text.done), so read both and the deltas."""
    deltas: list[str] = []
    final: str | None = None
    for event in stream:
        etype = getattr(event, "type", None) or (event.get("type") if isinstance(event, dict) else None)
        data = event.model_dump() if hasattr(event, "model_dump") else (event if isinstance(event, dict) else {})
        if etype == "response.output_text.delta":
            deltas.append(data.get("delta") or "")
        elif etype == "response.output_text.done" and isinstance(data.get("text"), str):
            final = data["text"]
        elif etype == "response.content_part.done":
            part = data.get("part") or {}
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                final = part["text"]
        elif etype in ("response.failed", "error"):
            raise muse.MuseError(f"SAM response failed: {data}")
    return final if final is not None else "".join(deltas)


def segment_boxes(image_path: str | Path, phrase: str) -> list[Box]:
    """One SAM 3.1 request for one noun phrase on one image. Raises on API failure."""
    kwargs = {
        "model": sam_model(), "stream": True, "metadata": {"include_confidence": "true"},
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": phrase},
            {"type": "input_image", "image_url": muse._data_url(image_path, "image/jpeg")},
        ]}],
    }
    t0 = time.time()
    stream = muse._with_retries("sam", kwargs, lambda: muse.client().responses.create(**kwargs))
    text = _stream_text(stream)
    boxes = parse_boxes(text)
    muse.log_run("sam", {"api": "responses(sam)", "request": muse._redact(kwargs),
                         "response": re.sub(r"data=[^|]*", "data=<mask>", text)[:4000],
                         "boxes": [b.__dict__ for b in boxes], "latency_s": round(time.time() - t0, 2)})
    return boxes


def draw_boxes(frame: str | Path, boxes: list[Box], out: str | Path) -> bool:
    """Draw up to MAX_BOXES boxes with ffmpeg, scaling SAM's source coordinates to the frame size."""
    if not boxes or not shutil.which("ffmpeg"):
        return False
    chosen = sorted(boxes, key=lambda b: -(b.confidence if b.confidence is not None else 0.5))[:MAX_BOXES]
    filters = []
    for b in chosen:
        # SAM reports w/h of the image it saw; iw/ih rescale in case the file differs.
        filters.append(
            f"drawbox=x={b.x1}*iw/{b.w}:y={b.y1}*ih/{b.h}:w={b.x2 - b.x1 + 1}*iw/{b.w}:"
            f"h={b.y2 - b.y1 + 1}*ih/{b.h}:color=0xFF2D2D@0.95:t=6")
    result = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(frame), "-vf", ",".join(filters),
                             "-q:v", "3", str(out)], check=False, timeout=60)
    return result.returncode == 0 and Path(out).exists()


def _highlight_one(e: Evidence) -> None:
    phrase = concept_for(e)
    if not phrase or not e.frame_path:
        return
    try:
        boxes = segment_boxes(e.frame_path, phrase)
        out = Path(e.frame_path).with_name(f"{e.id}_hl.jpg")
        if draw_boxes(e.frame_path, boxes, out):
            e.highlight_path = str(out)
    except Exception as ex:  # noqa: BLE001 - highlights are optional
        log.warning("SAM highlight failed for %s: %s", e.id, ex)
        e.highlight_path = None


def highlight_evidence(report: VerificationReport) -> None:
    """Set Evidence.highlight_path where SAM finds the concept. Never raises."""
    if not muse.available() or env("SAM_HIGHLIGHTS", "1") == "0":
        return
    todo = [e for e in report.evidence if e.frame_path and concept_for(e)][:MAX_FRAMES]
    if not todo:
        return
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(_highlight_one, todo))
    except Exception as ex:  # noqa: BLE001
        log.warning("SAM highlights skipped: %s", ex)
